"""Exercise logging: MET-based burn that raises the day's energy target.

kcal = MET x weight(kg) x hours, reading the member's latest weigh-in.
Running at moderate effort is MET 6.3, which reproduces Cronometer's numbers
exactly (their 220.4 lb / 40 min run = 419.9 kcal); the user calibrated
against Cronometer deliberately. Logged burn is added onto that day's energy
target (and its gram targets), Cronometer's "expenditure above baseline".
"""

import datetime as dt

from tests.conftest import user_id
from tests.test_health import PROFILE, setup_profile

TODAY = dt.date.today().isoformat()


def log_run(client, minutes=40.0, effort="moderate", activity="running", date=TODAY, **extra):
    return client.post(
        "/me/exercise",
        json={
            "date_for": date,
            "activity": activity,
            "effort": effort,
            "minutes": minutes,
            **extra,
        },
    )


# ---- the burn math ---------------------------------------------------------------


def test_running_moderate_matches_cronometer(owner):
    # 100 kg, 40 min at MET 6.3 -> 6.3 * 100 * (40/60) = 420.0 kcal.
    setup_profile(owner, weight_kg=100.0)
    res = log_run(owner, minutes=40)
    assert res.status_code == 201, res.text
    assert res.json()["kcal"] == 420.0


def test_effort_levels_change_the_burn(owner):
    setup_profile(owner, weight_kg=100.0)
    light = log_run(owner, minutes=60, effort="light").json()["kcal"]
    vigorous = log_run(owner, minutes=60, effort="vigorous").json()["kcal"]
    assert light < 630.0 < vigorous  # moderate at 60 min would be 630


def test_walking_uses_walking_mets(owner):
    # Walking moderate is MET 3.5: 3.5 * 100 * 0.5 = 175.
    setup_profile(owner, weight_kg=100.0)
    res = log_run(owner, minutes=30, activity="walking")
    assert res.json()["kcal"] == 175.0


def test_logging_exercise_needs_a_weigh_in(owner):
    owner.put("/me/health/profile", json=PROFILE)  # profile but no weight
    res = log_run(owner)
    assert res.status_code == 400


def test_unknown_activity_or_effort_is_refused(owner):
    setup_profile(owner, weight_kg=100.0)
    assert log_run(owner, activity="swimming").status_code == 422
    assert log_run(owner, effort="heroic").status_code == 422


# ---- the day's target grows by the burn ---------------------------------------------


def test_burn_raises_the_days_energy_target(owner):
    setup_profile(owner, weight_kg=100.0)
    base = owner.get(f"/diary?date={TODAY}").json()["targets"]
    log_run(owner, minutes=40)  # 420 kcal

    day = owner.get(f"/diary?date={TODAY}").json()
    t = day["targets"]
    assert t["exercise_kcal"] == 420.0
    assert t["calories"] == base["calories"] + 420
    # Gram targets scale with the raised budget.
    assert t["protein_g"] == round(t["calories"] * t["protein_pct"] / 100 / 4, 1)
    assert day["burned"] == 420.0
    assert len(day["exercise"]) == 1


def test_burn_counts_only_on_its_own_day(owner):
    setup_profile(owner, weight_kg=100.0)
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    log_run(owner, minutes=40, date=yesterday)
    today = owner.get(f"/diary?date={TODAY}").json()["targets"]
    assert today["exercise_kcal"] == 0.0


def test_editing_minutes_recomputes_the_burn(owner):
    setup_profile(owner, weight_kg=100.0)
    entry = log_run(owner, minutes=40).json()
    res = owner.patch(f"/me/exercise/{entry['id']}", json={"minutes": 20})
    assert res.status_code == 200
    assert res.json()["kcal"] == 210.0


def test_deleting_an_exercise_entry(owner):
    setup_profile(owner, weight_kg=100.0)
    entry = log_run(owner).json()
    assert owner.delete(f"/me/exercise/{entry['id']}").status_code == 204
    assert owner.get(f"/diary?date={TODAY}").json()["exercise"] == []


# ---- privacy ---------------------------------------------------------------------


def test_exercise_is_self_only(owner, child):
    setup_profile(child, weight_kg=45.0)
    entry = log_run(child, minutes=30, activity="walking").json()
    assert owner.get(f"/diary?date={TODAY}").json()["exercise"] == []
    assert owner.patch(f"/me/exercise/{entry['id']}", json={"minutes": 5}).status_code == 404
    assert owner.delete(f"/me/exercise/{entry['id']}").status_code == 404
