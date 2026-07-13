"""The dinner plan: four standing modes, every member votes (kids' picks are
advisory - only a parent locks in), lock-in via the ordinary meal row."""
import datetime as dt

TODAY = dt.date.today().isoformat()


def vote(client, choice, detail="", recipe_id=None):
    return client.put(
        f"/meals/plan?date={TODAY}",
        json={"choice": choice, "detail": detail, "recipe_id": recipe_id},
    )


def test_adults_pick_change_and_retract(owner, parent):
    res = vote(owner, "go_out", "Chipotle")
    assert res.status_code == 200, res.text
    res = vote(parent, "homemade", "tacos")
    plan = res.json()
    assert [(v["choice"], v["detail"]) for v in plan["votes"]] == [
        ("go_out", "Chipotle"),
        ("homemade", "tacos"),
    ]
    # A change replaces, never duplicates.
    res = vote(owner, "delivery", "Thai Palace")
    choices = [v["choice"] for v in res.json()["votes"]]
    assert choices.count("delivery") == 1 and "go_out" not in choices
    # Retract.
    res = owner.delete(f"/meals/plan?date={TODAY}")
    assert [v["user"]["display_name"] for v in res.json()["votes"]] == ["Second Parent"]


def test_kids_vote_switch_and_retract(owner, child):
    """A kid's vote is a real ballot: cast, change, retract - always only
    their own row. Once they vote they leave the ride-along kids list."""
    res = vote(child, "go_out", "Anywhere")
    assert res.status_code == 200, res.text
    plan = res.json()
    assert [(v["user"]["display_name"], v["choice"]) for v in plan["votes"]] == [
        ("The Kid", "go_out")
    ]
    assert plan["kids"] == []  # voted, so no longer a mere ride-along

    res = vote(child, "homemade", "tacos")
    choices = [v["choice"] for v in res.json()["votes"]]
    assert choices == ["homemade"]  # replaced, never duplicated

    plan = child.delete(f"/meals/plan?date={TODAY}").json()
    assert plan["votes"] == []
    assert [k["display_name"] for k in plan["kids"]] == ["The Kid"]


def test_kids_who_have_not_voted_ride_along(owner, child):
    vote(owner, "self_serve")
    plan = owner.get(f"/meals/plan?date={TODAY}").json()
    assert [k["display_name"] for k in plan["kids"]] == ["The Kid"]


def test_kids_never_lock_set_time_or_unlock(owner, child):
    vote(child, "go_out", "Anywhere")
    assert (
        child.put("/meals", json={"date_for": TODAY, "custom_title": "Go out"}).status_code
        == 403
    )
    assert (
        child.put("/meals/time", json={"date_for": TODAY, "time_of_day": "18:00"}).status_code
        == 403
    )
    vote(owner, "go_out", "Chipotle")
    owner.put("/meals", json={"date_for": TODAY, "custom_title": "Go out"})
    assert child.delete(f"/meals?date={TODAY}").status_code == 403


def test_choice_payload_rules(owner, other):
    assert vote(owner, "self_serve", "nope").status_code == 400
    assert vote(owner, "go_out", recipe_id=1).status_code == 400
    long = "x" * 31
    assert vote(owner, "go_out", long).status_code == 422
    # A recipe on homemade must be the family's own.
    res = other.post(
        "/recipes",
        json={"name": "Their stew", "servings": 2, "steps": "", "ingredients": [
            {"source": "usda", "source_id": "22", "name": "Beef", "brand": "",
             "amount": 100, "unit": "g", "calories": 250.0}
        ]},
    )
    theirs = res.json()["id"]
    assert vote(owner, "homemade", recipe_id=theirs).status_code == 404


def test_homemade_carries_the_recipe_name(owner):
    res = owner.post(
        "/recipes",
        json={"name": "Taco night", "servings": 4, "steps": "", "ingredients": [
            {"source": "usda", "source_id": "33", "name": "Beans", "brand": "",
             "amount": 100, "unit": "g", "calories": 120.0}
        ]},
    )
    rid = res.json()["id"]
    plan = vote(owner, "homemade", recipe_id=rid).json()
    assert plan["votes"][0]["recipe_name"] == "Taco night"


def test_votes_survive_lock_and_unlock(owner):
    vote(owner, "go_out", "Chipotle")
    assert owner.put("/meals", json={"date_for": TODAY, "custom_title": "Go out · Chipotle"}).status_code == 200
    assert owner.delete(f"/meals?date={TODAY}").status_code == 204
    plan = owner.get(f"/meals/plan?date={TODAY}").json()
    assert plan["votes"][0]["detail"] == "Chipotle"


def test_plans_are_family_scoped(owner, other):
    vote(owner, "go_out", "Chipotle")
    assert other.get(f"/meals/plan?date={TODAY}").json()["votes"] == []


def test_votes_stay_quiet_but_the_lock_in_speaks(owner, parent, child, configured, push_outbox):
    parent.put("/push/subscription", json={
        "endpoint": "https://push.example/p1", "keys": {"p256dh": "k", "auth": "a"},
    })
    child.put("/push/subscription", json={
        "endpoint": "https://push.example/k1", "keys": {"p256dh": "k", "auth": "a"},
    })
    vote(owner, "go_out", "Chipotle")
    vote(parent, "homemade")
    assert push_outbox == []  # votes are a standing block, not a conversation

    # Locking dinner IS setting the meal row, and that's the one dinner push.
    res = owner.put("/meals", json={"date_for": TODAY, "slot": "dinner", "custom_title": "Tacos"})
    assert res.status_code == 200, res.text
    endpoints = [ep for ep, _ in push_outbox]
    assert endpoints == ["https://push.example/p1"]  # the other adult, never the kid
    assert push_outbox[0][1]["title"].endswith("locked in dinner")
    assert push_outbox[0][1]["body"] == "Tacos"


def test_week_view_carries_future_preselections(owner, parent):
    friday = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    res = owner.put(f"/meals/plan?date={friday}", json={"choice": "delivery", "detail": "Pizza"})
    assert res.status_code == 200
    start, end = TODAY, (dt.date.today() + dt.timedelta(days=6)).isoformat()
    week = parent.get(f"/meals/plan/week?start={start}&end={end}").json()
    assert [w["date_for"] for w in week] == [friday]
    assert week[0]["votes"][0]["detail"] == "Pizza"
    # And when "that day comes up", the standing block reads the same votes.
    day = parent.get(f"/meals/plan?date={friday}").json()
    assert day["votes"][0]["choice"] == "delivery"
