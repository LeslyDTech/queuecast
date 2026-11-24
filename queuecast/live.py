"""Live posted wait times for real Orlando parks, from the Queue-Times.com Real Time API.

Queue-Times updates every 5 minutes and asks every app using it to show
"Powered by Queue-Times.com" with a link back. The dashboard does that.

Only the parks listed in PARKS can be requested, so this module can never be
used to fetch arbitrary URLs.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace

API_URL = "https://queue-times.com/parks/{park_id}/queue_times.json"
ATTRIBUTION = {"text": "Powered by Queue-Times.com", "url": "https://queue-times.com/"}
CACHE_SECONDS = 300  # the source only refreshes every 5 minutes
TIMEOUT_SECONDS = 8

PARKS: dict[int, str] = {
    65: "Universal Studios Florida",
    64: "Islands of Adventure",
    334: "Epic Universe",
}


class LiveDataError(RuntimeError):
    """The upstream API could not be reached or returned something unexpected."""


@dataclass(frozen=True)
class LiveRide:
    id: int | None
    name: str
    land: str
    is_open: bool
    wait_time_min: int | None  # None when the ride is closed
    last_updated: str
    single_rider_open: bool = False  # True when the ride's single-rider line is running


SINGLE_RIDER = re.compile(r"\s*single rider\s*$", re.IGNORECASE)


def _base_name(name: str) -> str:
    """Normalize names so "Revenge of the Mummy™ Single Rider" matches "Revenge of the Mummy"."""
    name = SINGLE_RIDER.sub("", name)
    return re.sub(r"[™®©]", "", name).strip().casefold()


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "QueueCast (portfolio project)"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.load(resp)
    except Exception as exc:  # network errors, timeouts, bad JSON
        raise LiveDataError(f"Could not load live data: {exc}") from exc


def parse_rides(payload: dict) -> list[LiveRide]:
    """Flatten the API's lands -> rides structure. Longest open waits first.

    Queue-Times lists single-rider lines as separate rides with a 0-minute wait.
    They aren't separate rides, and their zeros would drag down park averages,
    so they're folded into their main ride as a `single_rider_open` flag.
    """
    if not isinstance(payload, dict):
        raise LiveDataError("Unexpected response format")

    rides: list[LiveRide] = []
    single_rider_open: dict[str, bool] = {}
    groups = [(land.get("name", ""), land.get("rides", [])) for land in payload.get("lands", [])]
    groups.append(("", payload.get("rides", [])))  # some parks list rides without lands

    for land_name, items in groups:
        for r in items:
            name = r.get("name", "Unknown")
            if SINGLE_RIDER.search(name):
                key = _base_name(name)
                single_rider_open[key] = single_rider_open.get(key, False) or bool(r.get("is_open"))
                continue
            is_open = bool(r.get("is_open"))
            rides.append(
                LiveRide(
                    id=r.get("id"),
                    name=name,
                    land=land_name,
                    is_open=is_open,
                    wait_time_min=int(r.get("wait_time", 0)) if is_open else None,
                    last_updated=r.get("last_updated", ""),
                )
            )
    rides = [
        replace(r, single_rider_open=r.is_open and single_rider_open.get(_base_name(r.name), False))
        for r in rides
    ]
    rides.sort(key=lambda r: (not r.is_open, -(r.wait_time_min or 0), r.name))
    return rides


class LiveWaitClient:
    """Fetches live waits with a small in-memory cache to respect the free API."""

    def __init__(
        self,
        fetch: Callable[[str], dict] = _fetch_json,
        clock: Callable[[], float] = time.monotonic,
        cache_seconds: float = CACHE_SECONDS,
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._cache_seconds = cache_seconds
        self._cache: dict[int, tuple[float, list[LiveRide]]] = {}

    def get_park(self, park_id: int) -> dict:
        if park_id not in PARKS:
            raise KeyError(park_id)

        cached = self._cache.get(park_id)
        if cached and self._clock() - cached[0] < self._cache_seconds:
            rides = cached[1]
        else:
            rides = parse_rides(self._fetch(API_URL.format(park_id=park_id)))
            self._cache[park_id] = (self._clock(), rides)

        open_waits = [r.wait_time_min for r in rides if r.is_open and r.wait_time_min is not None]
        return {
            "park_id": park_id,
            "park": PARKS[park_id],
            "open_rides": len(open_waits),
            "average_wait_min": round(sum(open_waits) / len(open_waits), 1) if open_waits else None,
            "rides": [asdict(r) for r in rides],
            "attribution": ATTRIBUTION,
        }
