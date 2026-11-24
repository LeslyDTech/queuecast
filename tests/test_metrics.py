import pytest

from queuecast.metrics import interval_metrics, percentile, summarize
from queuecast.models import Attraction, GuestRecord, Scenario, SimulationResult


def make_result(guests, hours=1):
    ride = Attraction(id="r", name="R", vehicle_capacity=4, dispatch_interval_s=60,
                      base_arrivals_per_hour=10)
    return SimulationResult(
        attraction=ride,
        scenario=Scenario(hourly_profile=(1.0,) * hours),
        guests=guests,
        seats_offered=8,
        seats_filled=len(guests),
        end_s=3600 * hours,
    )


@pytest.mark.parametrize(
    ("values", "pct", "expected"),
    [([], 90, 0.0), ([5], 90, 5), ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90, 9),
     ([3, 1, 2], 50, 2), ([1, 2, 3], 100, 3)],
)
def test_percentile(values, pct, expected):
    assert percentile(values, pct) == expected


def test_percentile_rejects_bad_pct():
    with pytest.raises(ValueError):
        percentile([1, 2], 150)


def test_summary_math():
    guests = [
        GuestRecord(0, 600, "standby"),     # 10 min
        GuestRecord(60, 1260, "standby"),   # 20 min
        GuestRecord(120, 180, "priority"),  # 1 min
    ]
    s = summarize(make_result(guests))
    assert s.guests_served == 3
    assert s.standby_avg_wait_min == 15.0
    assert s.standby_max_wait_min == 20.0
    assert s.priority_avg_wait_min == 1.0
    assert s.utilization == round(3 / 8, 3)
    assert s.throughput_per_hour == 3.0


def test_interval_buckets_by_arrival_time():
    guests = [
        GuestRecord(0, 300, "standby"),       # bucket 0, 5 min
        GuestRecord(100, 700, "standby"),     # bucket 0, 10 min
        GuestRecord(1000, 1060, "priority"),  # bucket 15
    ]
    rows = interval_metrics(make_result(guests), bucket_min=15)
    assert len(rows) == 4
    assert rows[0].arrivals == 2
    assert rows[0].standby_avg_wait_min == 7.5
    assert rows[0].priority_avg_wait_min is None
    assert rows[1].priority_avg_wait_min == 1.0
    assert rows[3].arrivals == 0


def test_interval_rejects_bad_bucket():
    with pytest.raises(ValueError):
        interval_metrics(make_result([]), bucket_min=0)
