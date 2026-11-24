"""Calibrate each attraction's guest demand against real posted wait times.

We know each real ride's long-run average posted wait (from Queue-Times.com) and
an estimate of its hourly capacity, but not how many guests show up. Demand is
the unknown, so we search for it: bisection on demand until the simulated
average posted wait matches the real one.

Averaging over several seeds smooths out randomness from arrivals and breakdowns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from queuecast.metrics import interval_metrics
from queuecast.models import Attraction, Scenario
from queuecast.simulator import simulate

DEFAULT_SEEDS = tuple(range(1, 21))  # 20 simulated days; breakdowns make single days vary a lot


@dataclass(frozen=True)
class CalibrationResult:
    attraction_id: str
    target_wait_min: float
    simulated_wait_min: float
    base_arrivals_per_hour: float

    @property
    def error_min(self) -> float:
        return round(self.simulated_wait_min - self.target_wait_min, 1)


def average_posted_wait(attraction: Attraction, seeds=DEFAULT_SEEDS) -> float:
    """Mean standby wait across the day's 15-minute windows, averaged over seeds.

    This mirrors how a posted-wait average is built: one reading per time
    window, averaged over the operating day.
    """
    per_seed = []
    for seed in seeds:
        rows = interval_metrics(simulate(attraction, Scenario(seed=seed)))
        waits = [r.standby_avg_wait_min for r in rows if r.standby_avg_wait_min is not None]
        per_seed.append(sum(waits) / len(waits) if waits else 0.0)
    return sum(per_seed) / len(per_seed)


def calibrate_attraction(
    attraction: Attraction,
    target_wait_min: float,
    seeds=DEFAULT_SEEDS,
    iterations: int = 18,
) -> CalibrationResult:
    """Bisection on demand as a fraction of hourly capacity."""
    capacity = attraction.theoretical_hourly_capacity
    low, high = 0.05, 2.0  # demand between 5% and 200% of capacity

    def wait_at(ratio: float) -> float:
        return average_posted_wait(
            replace(attraction, base_arrivals_per_hour=ratio * capacity), seeds
        )

    best_ratio, best_wait = high, wait_at(high)
    for _ in range(iterations):
        mid = (low + high) / 2
        wait = wait_at(mid)
        if abs(wait - target_wait_min) < abs(best_wait - target_wait_min):
            best_ratio, best_wait = mid, wait
        if wait < target_wait_min:
            low = mid
        else:
            high = mid

    # Store a whole number, then re-measure: near full capacity, small demand
    # changes move waits a lot, so the reported error must match what ships.
    demand = round(best_ratio * capacity)
    final_wait = average_posted_wait(replace(attraction, base_arrivals_per_hour=demand), seeds)
    return CalibrationResult(
        attraction_id=attraction.id,
        target_wait_min=target_wait_min,
        simulated_wait_min=round(final_wait, 1),
        base_arrivals_per_hour=demand,
    )


def calibrate_file(path: Path, seeds=DEFAULT_SEEDS) -> list[CalibrationResult]:
    """Recalibrate every record in an attractions JSON file that has a real target."""
    records = json.loads(path.read_text("utf-8"))
    results = []
    for record in records:
        target = record.get("real_avg_posted_wait_min")
        if target is None:
            continue
        attraction = Attraction(**{**record, "base_arrivals_per_hour": 0})
        result = calibrate_attraction(attraction, target, seeds)
        record["base_arrivals_per_hour"] = result.base_arrivals_per_hour
        results.append(result)
    path.write_text(json.dumps(records, indent=2) + "\n", "utf-8")
    return results
