import pytest

from queuecast.db import RunStore
from queuecast.metrics import interval_metrics, summarize
from queuecast.simulator import simulate


@pytest.fixture
def store(tmp_path):
    return RunStore(tmp_path / "test.db")


def _save(store, ride, scenario, attraction_id=None):
    result = simulate(ride, scenario)
    return store.save_run(
        attraction_id or ride.id, scenario.seed, scenario.priority_share,
        scenario.crowd_multiplier, summarize(result), interval_metrics(result),
    )


def test_save_and_fetch_round_trip(store, small_ride, calm_scenario):
    run_id = _save(store, small_ride, calm_scenario)
    run = store.get_run(run_id)
    assert run["attraction_id"] == "test-ride"
    assert run["seed"] == calm_scenario.seed
    assert len(store.get_intervals(run_id)) == 12  # 3 hours of 15-minute buckets


def test_missing_run_returns_none(store):
    assert store.get_run(999) is None
    assert store.peak_interval(999) is None


def test_peak_interval_is_the_max(store, small_ride, calm_scenario):
    run_id = _save(store, small_ride, calm_scenario)
    peak = store.peak_interval(run_id)
    waits = [r["standby_avg_wait_min"] for r in store.get_intervals(run_id)
             if r["standby_avg_wait_min"] is not None]
    assert peak["standby_avg_wait_min"] == max(waits)


def test_list_and_filter(store, small_ride, calm_scenario):
    _save(store, small_ride, calm_scenario, "ride-a")
    _save(store, small_ride, calm_scenario, "ride-b")
    _save(store, small_ride, calm_scenario, "ride-a")
    assert len(store.list_runs()) == 3
    assert len(store.list_runs("ride-a")) == 2
    assert store.list_runs(limit=1)[0]["id"] == 3  # newest first


def test_attraction_report_groups_runs(store, small_ride, calm_scenario):
    _save(store, small_ride, calm_scenario, "ride-a")
    _save(store, small_ride, calm_scenario, "ride-a")
    _save(store, small_ride, calm_scenario, "ride-b")
    report = {r["attraction_id"]: r for r in store.attraction_report()}
    assert report["ride-a"]["runs"] == 2
    assert report["ride-b"]["runs"] == 1
