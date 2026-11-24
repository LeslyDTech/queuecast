"""Discrete-event simulation of one operating day at an attraction.

The engine keeps a min-heap of future events ordered by time. Each step pops the
earliest event, updates state, and schedules any follow-up events. Event types:

- ARRIVAL:   a guest joins the standby or priority queue
- DISPATCH:  a ride vehicle leaves, boarding guests from both queues
- BREAKDOWN: the ride goes down; dispatches pause
- REPAIR:    the ride comes back up

Arrivals follow a non-homogeneous Poisson process (crowds change by hour),
generated with the thinning method. A fixed seed makes every run reproducible.
"""

from __future__ import annotations

import heapq
import itertools
import math
import random
from collections import deque
from enum import IntEnum

from queuecast.models import Attraction, GuestRecord, Scenario, SimulationResult


class Event(IntEnum):
    # Lower value wins ties at the same timestamp: repairs before dispatches,
    # breakdowns before dispatches, arrivals before the dispatch that could board them.
    REPAIR = 0
    BREAKDOWN = 1
    ARRIVAL = 2
    DISPATCH = 3


class Simulator:
    def __init__(self, attraction: Attraction, scenario: Scenario) -> None:
        self.attraction = attraction
        self.scenario = scenario
        self.rng = random.Random(scenario.seed)
        self.close_s = scenario.park_hours * 3600.0

        self._events: list[tuple[float, int, int, Event]] = []
        self._seq = itertools.count()  # tie-breaker so heap never compares Events directly

        self.standby: deque[float] = deque()
        self.priority: deque[float] = deque()
        self.ride_up = True
        self._down_since = 0.0
        self.result = SimulationResult(attraction=attraction, scenario=scenario)

        hourly_rates = [
            attraction.base_arrivals_per_hour * scenario.crowd_multiplier * h
            for h in scenario.hourly_profile
        ]
        self._hourly_rates_per_s = [r / 3600.0 for r in hourly_rates]
        self._max_rate_per_s = max(self._hourly_rates_per_s, default=0.0)

    # ---- scheduling helpers -------------------------------------------------

    def _schedule(self, time_s: float, event: Event) -> None:
        heapq.heappush(self._events, (time_s, int(event), next(self._seq), event))

    def _rate_at(self, t: float) -> float:
        hour = min(int(t // 3600), len(self._hourly_rates_per_s) - 1)
        return self._hourly_rates_per_s[hour]

    def _next_arrival_after(self, t: float) -> float | None:
        """Thinning: draw candidates at the max rate, accept with probability rate(t)/max."""
        if self._max_rate_per_s <= 0:
            return None
        while True:
            t += self.rng.expovariate(self._max_rate_per_s)
            if t >= self.close_s:
                return None
            if self.rng.random() * self._max_rate_per_s <= self._rate_at(t):
                return t

    def _schedule_next_breakdown(self, after_s: float) -> None:
        if not (self.scenario.breakdowns_enabled and self.attraction.has_breakdowns):
            return
        gap = self.rng.expovariate(1.0 / (self.attraction.mtbf_minutes * 60))
        if after_s + gap < self.close_s:
            self._schedule(after_s + gap, Event.BREAKDOWN)

    # ---- event handlers -----------------------------------------------------

    def _on_arrival(self, now: float) -> None:
        if self.rng.random() < self.scenario.priority_share:
            self.priority.append(now)
        else:
            self.standby.append(now)
        nxt = self._next_arrival_after(now)
        if nxt is not None:
            self._schedule(nxt, Event.ARRIVAL)

    def _on_dispatch(self, now: float) -> None:
        if self.ride_up:
            self._board_vehicle(now)
        if now < self.close_s or self.standby or self.priority or not self.ride_up:
            # Keep running after close until everyone in line has ridden.
            self._schedule(now + self.attraction.dispatch_interval_s, Event.DISPATCH)

    def _board_vehicle(self, now: float) -> None:
        seats = self.attraction.vehicle_capacity
        priority_cap = math.floor(seats * self.scenario.priority_seat_ratio)

        boarded_priority = self._board_from(self.priority, priority_cap, now, "priority")
        boarded_standby = self._board_from(self.standby, seats - boarded_priority, now, "standby")
        # Unused standby seats go back to priority guests so no seat is wasted.
        leftover = seats - boarded_priority - boarded_standby
        boarded_priority += self._board_from(self.priority, leftover, now, "priority")

        self.result.seats_offered += seats
        self.result.seats_filled += boarded_priority + boarded_standby

    def _board_from(self, queue: deque[float], n: int, now: float, lane: str) -> int:
        count = 0
        while queue and count < n:
            self.result.guests.append(GuestRecord(queue.popleft(), now, lane))
            count += 1
        return count

    def _on_breakdown(self, now: float) -> None:
        self.ride_up = False
        self._down_since = now
        self.result.breakdowns += 1
        repair = self.rng.expovariate(1.0 / (self.attraction.mttr_minutes * 60))
        self._schedule(now + repair, Event.REPAIR)

    def _on_repair(self, now: float) -> None:
        self.ride_up = True
        self.result.downtime_s += now - self._down_since
        self._schedule_next_breakdown(now)

    # ---- main loop ----------------------------------------------------------

    def run(self) -> SimulationResult:
        first = self._next_arrival_after(0.0)
        if first is not None:
            self._schedule(first, Event.ARRIVAL)
        self._schedule(self.attraction.dispatch_interval_s, Event.DISPATCH)
        self._schedule_next_breakdown(0.0)

        handlers = {
            Event.ARRIVAL: self._on_arrival,
            Event.DISPATCH: self._on_dispatch,
            Event.BREAKDOWN: self._on_breakdown,
            Event.REPAIR: self._on_repair,
        }
        now = 0.0
        while self._events:
            now, _, _, event = heapq.heappop(self._events)
            handlers[event](now)

        self.result.end_s = now
        return self.result


def simulate(attraction: Attraction, scenario: Scenario | None = None) -> SimulationResult:
    return Simulator(attraction, scenario or Scenario()).run()
