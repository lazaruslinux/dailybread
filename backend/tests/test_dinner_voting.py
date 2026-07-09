"""The dinner plan: four standing modes, adult picks with avatars and short
details, kids following the leader, lock-in via the ordinary meal row."""
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


def test_children_never_vote_but_ride_along(owner, child):
    assert vote(child, "go_out", "Anywhere").status_code == 403
    vote(owner, "self_serve")
    plan = owner.get(f"/meals/plan?date={TODAY}").json()
    assert [k["display_name"] for k in plan["kids"]] == ["The Kid"]


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


def test_first_pick_of_the_day_nudges_once(owner, parent, child, configured, outbox):
    parent.put("/push/subscription", json={
        "endpoint": "https://push.example/p1", "keys": {"p256dh": "k", "auth": "a"},
    })
    child.put("/push/subscription", json={
        "endpoint": "https://push.example/k1", "keys": {"p256dh": "k", "auth": "a"},
    })
    vote(owner, "go_out", "Chipotle")
    assert outbox == ["https://push.example/p1"]  # the other adult, never the kid
    vote(owner, "delivery", "Pizza")  # changes stay quiet
    vote(parent, "homemade")  # later picks stay quiet too
    assert outbox == ["https://push.example/p1"]


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
