import json

from queuecast.calibrate import average_posted_wait, calibrate_attraction, calibrate_file
from queuecast.models import Attraction, load_attractions

RIDE = Attraction(id="r", name="R", vehicle_capacity=10, dispatch_interval_s=60,
                  base_arrivals_per_hour=0, mtbf_minutes=None, mttr_minutes=None)


def test_calibration_hits_target():
    result = calibrate_attraction(RIDE, target_wait_min=20, seeds=(1,), iterations=14)
    assert abs(result.error_min) <= 2.5
    assert 0 < result.base_arrivals_per_hour < 2 * RIDE.theoretical_hourly_capacity


def test_higher_target_needs_more_demand():
    low = calibrate_attraction(RIDE, 10, seeds=(1,), iterations=12)
    high = calibrate_attraction(RIDE, 40, seeds=(1,), iterations=12)
    assert high.base_arrivals_per_hour > low.base_arrivals_per_hour


def test_average_posted_wait_zero_demand():
    assert average_posted_wait(RIDE, seeds=(1,)) == 0.0


def test_calibrate_file_skips_rides_without_target(tmp_path):
    path = tmp_path / "rides.json"
    path.write_text(json.dumps([
        {"id": "a", "name": "A", "vehicle_capacity": 10, "dispatch_interval_s": 60,
         "base_arrivals_per_hour": 123},
    ]))
    assert calibrate_file(path, seeds=(1,)) == []
    assert json.loads(path.read_text())[0]["base_arrivals_per_hour"] == 123


def test_bundled_rides_are_real_and_calibrated():
    rides = load_attractions().values()
    assert len(rides) >= 40
    for a in rides:
        assert a.queue_times_id and a.queue_times_park_id
        assert a.real_avg_posted_wait_min is not None
        assert a.base_arrivals_per_hour > 0


def test_bundled_calibration_is_close_to_real_waits():
    """Spot-check that the shipped demand still reproduces real average waits."""
    rides = load_attractions()
    for ride_id in ["harry-potter-and-the-escape-from-gringotts", "jurassic-world-velocicoaster",
                    "mario-kart-bowsers-challenge"]:
        a = rides[ride_id]
        assert abs(average_posted_wait(a) - a.real_avg_posted_wait_min) < 5
