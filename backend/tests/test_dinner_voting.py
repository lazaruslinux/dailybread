"""Dinner voting: a parent posts candidates, everyone (kids included) votes
once per night, the parent reads the tally and crowns the winner."""
import datetime as dt

TODAY = dt.date.today().isoformat()


def open_ballot(client, options=None):
    res = client.put(
        f"/meals/vote?date={TODAY}",
        json={"options": options or [{"title": "Tacos"}, {"title": "Pasta night"}]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_parent_opens_a_ballot_and_everyone_votes(owner, parent, child):
    ballot = open_ballot(owner)
    tacos, pasta = ballot["options"]

    # The kid's one Kitchen write: a vote.
    res = child.post(f"/meals/vote/{tacos['id']}")
    assert res.status_code == 200
    res = parent.post(f"/meals/vote/{pasta['id']}")
    assert res.status_code == 200
    res = owner.post(f"/meals/vote/{tacos['id']}")

    tally = {o["title"]: o for o in res.json()["options"]}
    assert tally["Tacos"]["votes"] == 2
    assert tally["Pasta night"]["votes"] == 1
    assert res.json()["total_votes"] == 3
    assert tally["Tacos"]["my_vote"] is True  # the owner's own view
    assert "The Kid" not in str(tally)  # voters carry first names
    assert "The" in tally["Tacos"]["voters"] or "Owner" in str(tally["Tacos"]["voters"])


def test_one_vote_per_night_changeable(owner, child):
    ballot = open_ballot(owner)
    tacos, pasta = ballot["options"]
    child.post(f"/meals/vote/{tacos['id']}")
    res = child.post(f"/meals/vote/{pasta['id']}")  # changed their mind
    tally = {o["title"]: o["votes"] for o in res.json()["options"]}
    assert tally == {"Tacos": 0, "Pasta night": 1}
    assert res.json()["total_votes"] == 1


def test_only_parents_manage_the_ballot(owner, child):
    assert child.put(
        f"/meals/vote?date={TODAY}", json={"options": [{"title": "A"}, {"title": "B"}]}
    ).status_code == 403
    open_ballot(owner)
    assert child.delete(f"/meals/vote?date={TODAY}").status_code == 403
    assert owner.delete(f"/meals/vote?date={TODAY}").status_code == 204
    assert owner.get(f"/meals/vote?date={TODAY}").json()["options"] == []


def test_replacing_the_ballot_clears_votes(owner, child):
    ballot = open_ballot(owner)
    child.post(f"/meals/vote/{ballot['options'][0]['id']}")
    replaced = open_ballot(owner, [{"title": "Soup"}, {"title": "Salad"}, {"title": "Pizza"}])
    assert replaced["total_votes"] == 0
    assert len(replaced["options"]) == 3


def test_ballots_are_family_scoped(owner, other):
    ballot = open_ballot(owner)
    assert other.post(f"/meals/vote/{ballot['options'][0]['id']}").status_code == 404
    assert other.get(f"/meals/vote?date={TODAY}").json()["options"] == []


def test_ballot_needs_two_to_five_options(owner):
    assert owner.put(
        f"/meals/vote?date={TODAY}", json={"options": [{"title": "Solo"}]}
    ).status_code == 422
    six = [{"title": f"O{i}"} for i in range(6)]
    assert owner.put(f"/meals/vote?date={TODAY}", json={"options": six}).status_code == 422
