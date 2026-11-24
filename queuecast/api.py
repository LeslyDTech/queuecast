"""REST API for running and browsing simulations.

Run locally:  uvicorn queuecast.api:app --reload
Docs:         http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import os
from functools import lru_cache
from importlib import resources
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from queuecast import __version__
from queuecast.db import RunStore
from queuecast.metrics import interval_metrics, summarize
from queuecast.models import Scenario, load_attractions
from queuecast.simulator import simulate

app = FastAPI(
    title="QueueCast",
    version=__version__,
    description="Simulate attraction queues and forecast wait times under what-if scenarios.",
)

ATTRACTIONS = load_attractions()


@lru_cache
def get_store() -> RunStore:
    return RunStore(os.environ.get("QUEUECAST_DB", "queuecast.db"))


StoreDep = Annotated[RunStore, Depends(get_store)]


class SimulationRequest(BaseModel):
    attraction_id: str = Field(examples=["comet-coaster"])
    priority_share: float = Field(0.0, ge=0, le=1, description="Share of guests in priority lane")
    priority_seat_ratio: float = Field(0.7, ge=0, le=1)
    crowd_multiplier: float = Field(1.0, ge=0, le=5)
    seed: int = 42
    breakdowns_enabled: bool = True


class CompareRequest(BaseModel):
    attraction_id: str
    priority_shares: list[float] = Field(min_length=1, max_length=10)
    crowd_multiplier: float = Field(1.0, ge=0, le=5)
    seed: int = 42


def _attraction_or_404(attraction_id: str):
    try:
        return ATTRACTIONS[attraction_id]
    except KeyError:
        raise HTTPException(404, f"Unknown attraction '{attraction_id}'") from None


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    return resources.files("queuecast").joinpath("static/index.html").read_text("utf-8")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/attractions")
def list_attractions() -> list[dict]:
    return [
        {
            "id": a.id,
            "name": a.name,
            "vehicle_capacity": a.vehicle_capacity,
            "dispatch_interval_s": a.dispatch_interval_s,
            "theoretical_hourly_capacity": round(a.theoretical_hourly_capacity),
            "base_arrivals_per_hour": a.base_arrivals_per_hour,
        }
        for a in ATTRACTIONS.values()
    ]


@app.post("/simulations", status_code=201)
def create_simulation(req: SimulationRequest, store: StoreDep) -> dict:
    attraction = _attraction_or_404(req.attraction_id)
    scenario = Scenario(
        priority_share=req.priority_share,
        priority_seat_ratio=req.priority_seat_ratio,
        crowd_multiplier=req.crowd_multiplier,
        seed=req.seed,
        breakdowns_enabled=req.breakdowns_enabled,
    )
    result = simulate(attraction, scenario)
    summary = summarize(result)
    intervals = interval_metrics(result)
    run_id = store.save_run(
        attraction.id, req.seed, req.priority_share, req.crowd_multiplier, summary, intervals
    )
    return {"run_id": run_id, "attraction": attraction.name, "summary": summary.to_dict()}


@app.post("/simulations/compare")
def compare(req: CompareRequest) -> dict:
    """Run the same day (same seed) at several priority-lane shares, side by side."""
    attraction = _attraction_or_404(req.attraction_id)
    rows = []
    for share in req.priority_shares:
        if not 0 <= share <= 1:
            raise HTTPException(422, "priority_shares must each be between 0 and 1")
        scenario = Scenario(
            priority_share=share, crowd_multiplier=req.crowd_multiplier, seed=req.seed
        )
        summary = summarize(simulate(attraction, scenario))
        rows.append({"priority_share": share, **summary.to_dict()})
    return {"attraction": attraction.name, "results": rows}


@app.get("/simulations")
def list_simulations(
    store: StoreDep,
    attraction_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[dict]:
    return store.list_runs(attraction_id, limit)


@app.get("/simulations/{run_id}")
def get_simulation(run_id: int, store: StoreDep) -> dict:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return {**run, "peak_interval": store.peak_interval(run_id)}


@app.get("/simulations/{run_id}/wait-times")
def get_wait_times(run_id: int, store: StoreDep) -> list[dict]:
    if store.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")
    return store.get_intervals(run_id)


@app.get("/reports/attractions")
def attraction_report(store: StoreDep) -> list[dict]:
    return store.attraction_report()
