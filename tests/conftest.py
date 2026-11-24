import pytest

from queuecast.models import Attraction, Scenario


@pytest.fixture
def small_ride() -> Attraction:
    return Attraction(
        id="test-ride",
        name="Test Ride",
        vehicle_capacity=10,
        dispatch_interval_s=60,
        base_arrivals_per_hour=500,
        mtbf_minutes=120,
        mttr_minutes=10,
    )


@pytest.fixture
def calm_scenario() -> Scenario:
    return Scenario(hourly_profile=(1.0, 1.0, 1.0), seed=7)
