"""Daily journal: private per-day entries, upsert, history, isolation."""

import datetime as dt

TODAY = dt.date.today().isoformat()


def test_journal_starts_empty(owner):
    assert owner.get(f"/me/journal?date={TODAY}").json() is None
    assert owner.get("/me/journal/history").json() == []


def test_write_read_and_update(owner):
    r = owner.put("/me/journal", json={"date_for": TODAY, "body": "  Good day.  "})
    assert r.status_code == 200
    assert r.json()["body"] == "Good day."  # trimmed

    assert owner.get(f"/me/journal?date={TODAY}").json()["body"] == "Good day."

    # Rewriting the same day updates in place (no second history row).
    owner.put("/me/journal", json={"date_for": TODAY, "body": "Actually a great day."})
    hist = owner.get("/me/journal/history").json()
    assert len(hist) == 1 and hist[0]["body"] == "Actually a great day."


def test_blank_body_clears_the_day(owner):
    owner.put("/me/journal", json={"date_for": TODAY, "body": "something"})
    r = owner.put("/me/journal", json={"date_for": TODAY, "body": "   "})
    assert r.status_code == 200 and r.json()["body"] == ""
    assert owner.get(f"/me/journal?date={TODAY}").json() is None
    assert owner.get("/me/journal/history").json() == []


def test_history_is_most_recent_first(owner):
    d1 = TODAY
    d0 = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    owner.put("/me/journal", json={"date_for": d0, "body": "yesterday"})
    owner.put("/me/journal", json={"date_for": d1, "body": "today"})
    hist = owner.get("/me/journal/history").json()
    assert [h["date_for"] for h in hist] == [d1, d0]


def test_delete_removes_the_entry(owner):
    owner.put("/me/journal", json={"date_for": TODAY, "body": "temp"})
    assert owner.delete(f"/me/journal?date={TODAY}").status_code == 204
    assert owner.get(f"/me/journal?date={TODAY}").json() is None


def test_journal_is_private_between_members(owner, child):
    owner.put("/me/journal", json={"date_for": TODAY, "body": "owner's private thoughts"})
    # A child's own journal is separate and empty; there is no way to read
    # someone else's — /me/journal is always the caller's own.
    assert child.get(f"/me/journal?date={TODAY}").json() is None
    assert child.get("/me/journal/history").json() == []


def test_anon_cannot_touch_journal(anon):
    assert anon.get(f"/me/journal?date={TODAY}").status_code == 401
    assert anon.put("/me/journal", json={"date_for": TODAY, "body": "x"}).status_code == 401


def test_far_date_is_rejected(owner):
    far = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    assert owner.put("/me/journal", json={"date_for": far, "body": "x"}).status_code == 400
