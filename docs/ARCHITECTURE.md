# Architecture

## Goals

1. Produce believable wait-time curves for one attraction over one day.
2. Make what-if comparisons fair by holding randomness constant (seeded runs).
3. Keep the core engine dependency-free so it is easy to test and reason about.
4. Expose results three ways: CLI for quick checks, REST API for integration, and a dashboard for demos.

## Layers

| Layer | Module | Depends on |
| --- | --- | --- |
| Domain | `models.py` | standard library |
| Engine | `simulator.py` | models |
| Analytics | `metrics.py` | models |
| Persistence | `db.py` | metrics (types only), `sqlite3` |
| Interfaces | `api.py`, `cli.py`, `static/` | everything above |

Dependencies point in one direction only: the engine knows nothing about HTTP or SQL. You can swap SQLite for Postgres, or FastAPI for something else, without touching the simulation.

## Simulation model

**Time.** Measured in seconds from park open. Arrivals stop at close, but the ride keeps dispatching until both lines are empty, the same way a real attraction handles its last guests.

**Events.** Stored as `(time, priority, sequence, event)` tuples in a min-heap. The `priority` field settles ties at the same timestamp in this order: a repair, then a breakdown, then an arrival, then a dispatch. That way an arriving guest can board the vehicle leaving at that exact second, and a ride that breaks at that second does not dispatch. The `sequence` counter keeps ordering stable and ensures the heap never compares Event objects directly.

**Arrivals.** Hourly demand is `base_arrivals_per_hour × crowd_multiplier × hourly_profile[h]`. To sample a process whose rate changes over time, candidate arrivals are drawn at the peak rate, and each is kept with probability `rate(t) / peak_rate` (Lewis–Shedler thinning).

**Boarding.** For each dispatch:

1. Board up to `floor(capacity × priority_seat_ratio)` priority guests.
2. Fill the remaining seats from standby.
3. Give any seats still empty to remaining priority guests.

**Breakdowns.** The time between failures and the length of each repair are both exponentially distributed, with means of `mtbf_minutes` and `mttr_minutes`. While the ride is down, dispatch events still happen but board nobody. That keeps the schedule simple and correctly lets the line build up during the outage.

## Metrics

- **Standby average, 90th percentile, max wait.** The 90th percentile matters more than the average for guest experience, since it describes the worst wait a typical guest might realistically face.
- **Throughput per hour.** Guests boarded divided by operating hours.
- **Utilization.** Seats filled divided by seats offered.
- **Interval metrics.** Average wait grouped by *arrival* time in 15-minute buckets, which approximates what a posted wait sign would have shown at that moment.

## Data model

```
simulation_runs (1) ──── (many) interval_metrics
  id PK                        run_id FK → simulation_runs.id (cascade delete)
  attraction_id (indexed)      bucket_start_min
  seed, priority_share, ...    arrivals, standby_avg_wait_min, priority_avg_wait_min
  summary columns              PK (run_id, bucket_start_min)
```

## Testing strategy

- **Unit tests** for metrics math, using hand-built guest records with known answers.
- **Property-style tests** on the engine: invariants that must hold on any seed (no overfilled vehicle, first-in first-out within a lane, boarding never before arrival, throughput no higher than capacity).
- **Directional tests:** more crowd means longer waits, and more priority users mean longer standby waits.
- **Integration tests** for the API, using FastAPI's `TestClient` with the database swapped for a temporary file through dependency overrides.
- **CI** runs it all on three Python versions and requires at least 85% coverage.
