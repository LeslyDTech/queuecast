"""Command line interface.

Examples:
    queuecast list
    queuecast run comet-coaster --priority-share 0.3 --crowd 1.2
    queuecast compare comet-coaster --shares 0 0.2 0.4 0.6
"""

from __future__ import annotations

import argparse
import sys

from queuecast.metrics import interval_metrics, summarize
from queuecast.models import Scenario, load_attractions
from queuecast.simulator import simulate


def _fmt_clock(minutes_from_open: int, open_hour: int = 9) -> str:
    total = open_hour * 60 + minutes_from_open
    h, m = divmod(total, 60)
    suffix = "AM" if h < 12 else "PM"
    return f"{(h - 1) % 12 + 1}:{m:02d} {suffix}"


def cmd_list(_: argparse.Namespace) -> int:
    print(f"{'ID':<22}{'NAME':<22}{'CAPACITY/HR':>12}{'DEMAND/HR':>11}")
    for a in load_attractions().values():
        print(
            f"{a.id:<22}{a.name:<22}{a.theoretical_hourly_capacity:>12.0f}"
            f"{a.base_arrivals_per_hour:>11.0f}"
        )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    attraction = _get(args.attraction)
    scenario = Scenario(
        priority_share=args.priority_share,
        crowd_multiplier=args.crowd,
        seed=args.seed,
        breakdowns_enabled=not args.no_breakdowns,
    )
    result = simulate(attraction, scenario)
    s = summarize(result)
    print(f"\n{attraction.name}  (seed {args.seed}, crowd x{args.crowd}, "
          f"priority {args.priority_share:.0%})")
    print("-" * 48)
    for key, value in s.to_dict().items():
        print(f"  {key.replace('_', ' '):<26}{value}")

    print("\n  Posted wait by hour (standby):")
    for m in interval_metrics(result, bucket_min=60):
        wait = m.standby_avg_wait_min or 0
        bar = "#" * int(wait // 3)
        print(f"  {_fmt_clock(m.bucket_start_min):>8}  {wait:>5.1f} min  {bar}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    attraction = _get(args.attraction)
    print(f"\n{attraction.name}: priority-lane what-if (seed {args.seed})")
    print(f"{'PRIORITY':>9}{'STANDBY AVG':>13}{'STANDBY P90':>13}{'PRIORITY AVG':>14}")
    for share in args.shares:
        s = summarize(simulate(attraction, Scenario(priority_share=share, seed=args.seed,
                                                     crowd_multiplier=args.crowd)))
        print(f"{share:>9.0%}{s.standby_avg_wait_min:>13}{s.standby_p90_wait_min:>13}"
              f"{s.priority_avg_wait_min:>14}")
    return 0


def _get(attraction_id: str):
    attractions = load_attractions()
    if attraction_id not in attractions:
        sys.exit(f"Unknown attraction '{attraction_id}'. Try: {', '.join(attractions)}")
    return attractions[attraction_id]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="queuecast", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List sample attractions").set_defaults(func=cmd_list)

    run = sub.add_parser("run", help="Simulate one day")
    run.add_argument("attraction")
    run.add_argument("--priority-share", type=float, default=0.0)
    run.add_argument("--crowd", type=float, default=1.0)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--no-breakdowns", action="store_true")
    run.set_defaults(func=cmd_run)

    cmp_ = sub.add_parser("compare", help="Compare priority-lane shares")
    cmp_.add_argument("attraction")
    cmp_.add_argument("--shares", type=float, nargs="+", default=[0, 0.2, 0.4, 0.6])
    cmp_.add_argument("--crowd", type=float, default=1.0)
    cmp_.add_argument("--seed", type=int, default=42)
    cmp_.set_defaults(func=cmd_compare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
