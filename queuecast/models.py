"""Core data models for attractions, scenarios, and simulation output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources

# Relative crowd level for each park hour, starting at park open (9 AM - 9 PM).
# Morning rush, midday peak, dip at dinner, small evening bump.
DEFAULT_HOURLY_PROFILE: tuple[float, ...] = (
    0.55, 0.80, 0.95, 1.00, 1.00, 0.95, 0.90, 0.85, 0.70, 0.75, 0.60, 0.40,
)


@dataclass(frozen=True)
class Attraction:
    id: str
    name: str
    vehicle_capacity: int
    dispatch_interval_s: int
    base_arrivals_per_hour: float
    mtbf_minutes: float | None = None  # mean time between breakdowns
    mttr_minutes: float | None = None  # mean time to repair

    def __post_init__(self) -> None:
        if self.vehicle_capacity <= 0:
            raise ValueError("vehicle_capacity must be positive")
        if self.dispatch_interval_s <= 0:
            raise ValueError("dispatch_interval_s must be positive")
        if self.base_arrivals_per_hour < 0:
            raise ValueError("base_arrivals_per_hour cannot be negative")
        if (self.mtbf_minutes is None) != (self.mttr_minutes is None):
            raise ValueError("mtbf_minutes and mttr_minutes must both be set or both be None")

    @property
    def theoretical_hourly_capacity(self) -> float:
        return self.vehicle_capacity * 3600 / self.dispatch_interval_s

    @property
    def has_breakdowns(self) -> bool:
        return self.mtbf_minutes is not None


@dataclass(frozen=True)
class Scenario:
    """Operating choices for one simulated day."""

    priority_share: float = 0.0  # fraction of arriving guests using the priority lane
    priority_seat_ratio: float = 0.7  # max fraction of each vehicle given to priority guests
    crowd_multiplier: float = 1.0  # scales the whole day's demand (e.g. 1.3 for a holiday)
    hourly_profile: tuple[float, ...] = DEFAULT_HOURLY_PROFILE
    seed: int = 42
    breakdowns_enabled: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.priority_share <= 1.0:
            raise ValueError("priority_share must be between 0 and 1")
        if not 0.0 <= self.priority_seat_ratio <= 1.0:
            raise ValueError("priority_seat_ratio must be between 0 and 1")
        if self.crowd_multiplier < 0:
            raise ValueError("crowd_multiplier cannot be negative")
        if not self.hourly_profile or any(h < 0 for h in self.hourly_profile):
            raise ValueError("hourly_profile must be non-empty with non-negative values")

    @property
    def park_hours(self) -> int:
        return len(self.hourly_profile)


@dataclass(frozen=True)
class GuestRecord:
    arrival_s: float
    board_s: float
    lane: str  # "standby" or "priority"

    @property
    def wait_s(self) -> float:
        return self.board_s - self.arrival_s


@dataclass
class SimulationResult:
    attraction: Attraction
    scenario: Scenario
    guests: list[GuestRecord] = field(default_factory=list)
    seats_offered: int = 0
    seats_filled: int = 0
    downtime_s: float = 0.0
    breakdowns: int = 0
    end_s: float = 0.0


def load_attractions() -> dict[str, Attraction]:
    """Load the bundled sample attractions keyed by id."""
    raw = resources.files("queuecast").joinpath("data/attractions.json").read_text("utf-8")
    return {item["id"]: Attraction(**item) for item in json.loads(raw)}
