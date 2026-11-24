"""Turn raw guest records into the numbers an operations team cares about."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from queuecast.models import GuestRecord, SimulationResult


@dataclass(frozen=True)
class IntervalMetric:
    bucket_start_min: int
    arrivals: int
    standby_avg_wait_min: float | None
    priority_avg_wait_min: float | None


@dataclass(frozen=True)
class Summary:
    guests_served: int
    standby_avg_wait_min: float
    standby_p90_wait_min: float
    standby_max_wait_min: float
    priority_avg_wait_min: float
    throughput_per_hour: float
    utilization: float
    breakdowns: int
    downtime_min: float

    def to_dict(self) -> dict:
        return asdict(self)


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Returns 0.0 for an empty list."""
    if not values:
        return 0.0
    if not 0 <= pct <= 100:
        raise ValueError("pct must be between 0 and 100")
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil without importing math
    return ordered[int(rank) - 1]


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize(result: SimulationResult) -> Summary:
    standby = [g.wait_s / 60 for g in result.guests if g.lane == "standby"]
    priority = [g.wait_s / 60 for g in result.guests if g.lane == "priority"]
    operating_hours = max(result.end_s, 1.0) / 3600
    return Summary(
        guests_served=len(result.guests),
        standby_avg_wait_min=round(_avg(standby), 1),
        standby_p90_wait_min=round(percentile(standby, 90), 1),
        standby_max_wait_min=round(max(standby, default=0.0), 1),
        priority_avg_wait_min=round(_avg(priority), 1),
        throughput_per_hour=round(len(result.guests) / operating_hours, 1),
        utilization=round(result.seats_filled / result.seats_offered, 3)
        if result.seats_offered
        else 0.0,
        breakdowns=result.breakdowns,
        downtime_min=round(result.downtime_s / 60, 1),
    )


def interval_metrics(result: SimulationResult, bucket_min: int = 15) -> list[IntervalMetric]:
    """Average wait by arrival time bucket -- what a posted wait sign would show."""
    if bucket_min <= 0:
        raise ValueError("bucket_min must be positive")
    bucket_s = bucket_min * 60
    n_buckets = int(result.scenario.park_hours * 3600 // bucket_s)
    buckets: list[list[GuestRecord]] = [[] for _ in range(n_buckets)]
    for g in result.guests:
        idx = min(int(g.arrival_s // bucket_s), n_buckets - 1)
        buckets[idx].append(g)

    out = []
    for i, group in enumerate(buckets):
        sb = [g.wait_s / 60 for g in group if g.lane == "standby"]
        pr = [g.wait_s / 60 for g in group if g.lane == "priority"]
        out.append(
            IntervalMetric(
                bucket_start_min=i * bucket_min,
                arrivals=len(group),
                standby_avg_wait_min=round(_avg(sb), 1) if sb else None,
                priority_avg_wait_min=round(_avg(pr), 1) if pr else None,
            )
        )
    return out
