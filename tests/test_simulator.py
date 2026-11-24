from dataclasses import replace

import pytest

from queuecast.metrics import summarize
from queuecast.models import Attraction, Scenario, load_attractions
from queuecast.simulator import simulate


def test_same_seed_gives_identical_results(small_ride, calm_scenario):
    a = summarize(simulate(small_ride, calm_scenario))
    b = summarize(simulate(small_ride, calm_scenario))
    assert a == b


def test_different_seeds_differ(small_ride, calm_scenario):
    a = summarize(simulate(small_ride, calm_scenario))
    b = summarize(simulate(small_ride, replace(calm_scenario, seed=8)))
    assert a != b


def test_every_guest_rides_and_nobody_boards_before_arriving(small_ride, calm_scenario):
    result = simulate(small_ride, calm_scenario)
    assert result.guests, "expected some guests"
    assert all(g.board_s >= g.arrival_s for g in result.guests)
    # Arrivals stop at close, but the line keeps loading until it is empty.
    assert all(g.arrival_s < 3 * 3600 for g in result.guests)


def test_vehicle_never_overfilled(small_ride, calm_scenario):
    result = simulate(small_ride, calm_scenario)
    per_dispatch: dict[float, int] = {}
    for g in result.guests:
        per_dispatch[g.board_s] = per_dispatch.get(g.board_s, 0) + 1
    assert max(per_dispatch.values()) <= small_ride.vehicle_capacity
    assert result.seats_filled <= result.seats_offered


def test_queue_is_fifo_within_a_lane(small_ride, calm_scenario):
    result = simulate(small_ride, calm_scenario)
    standby = [g for g in result.guests if g.lane == "standby"]
    arrivals_in_board_order = [g.arrival_s for g in standby]
    assert arrivals_in_board_order == sorted(arrivals_in_board_order)


def test_no_demand_means_no_guests(small_ride):
    empty = replace(small_ride, base_arrivals_per_hour=0)
    result = simulate(empty, Scenario(hourly_profile=(1.0,)))
    assert result.guests == []
    assert summarize(result).standby_avg_wait_min == 0.0


def test_priority_lane_waits_less_than_standby_when_ride_is_overloaded(small_ride):
    busy = replace(small_ride, base_arrivals_per_hour=900)  # capacity is 600/hr
    s = summarize(simulate(busy, Scenario(priority_share=0.3, hourly_profile=(1.0,) * 4)))
    assert s.priority_avg_wait_min < s.standby_avg_wait_min


def test_more_priority_users_make_standby_worse(small_ride):
    busy = replace(small_ride, base_arrivals_per_hour=900, mtbf_minutes=None, mttr_minutes=None)
    base = Scenario(hourly_profile=(1.0,) * 4, seed=3)
    low = summarize(simulate(busy, replace(base, priority_share=0.1)))
    high = summarize(simulate(busy, replace(base, priority_share=0.5)))
    assert high.standby_avg_wait_min > low.standby_avg_wait_min


def test_bigger_crowds_mean_longer_waits(small_ride, calm_scenario):
    normal = summarize(simulate(small_ride, calm_scenario))
    holiday = summarize(simulate(small_ride, replace(calm_scenario, crowd_multiplier=1.8)))
    assert holiday.standby_avg_wait_min > normal.standby_avg_wait_min


def test_disabling_breakdowns_removes_downtime(small_ride, calm_scenario):
    result = simulate(small_ride, replace(calm_scenario, breakdowns_enabled=False))
    assert result.breakdowns == 0
    assert result.downtime_s == 0


def test_throughput_never_exceeds_theoretical_capacity():
    for attraction in load_attractions().values():
        s = summarize(simulate(attraction, Scenario(crowd_multiplier=2.0)))
        assert s.throughput_per_hour <= attraction.theoretical_hourly_capacity + 1e-9


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vehicle_capacity": 0},
        {"dispatch_interval_s": 0},
        {"base_arrivals_per_hour": -1},
        {"mtbf_minutes": 60, "mttr_minutes": None},
    ],
)
def test_invalid_attraction_rejected(kwargs):
    base = dict(id="x", name="X", vehicle_capacity=10, dispatch_interval_s=60,
                base_arrivals_per_hour=100)
    with pytest.raises(ValueError):
        Attraction(**{**base, **kwargs})


@pytest.mark.parametrize(
    "kwargs",
    [{"priority_share": 1.5}, {"priority_seat_ratio": -0.1}, {"crowd_multiplier": -1},
     {"hourly_profile": ()}],
)
def test_invalid_scenario_rejected(kwargs):
    with pytest.raises(ValueError):
        Scenario(**kwargs)
