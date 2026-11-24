import pytest
from fastapi.testclient import TestClient

from queuecast.api import app, get_store
from queuecast.db import RunStore


@pytest.fixture
def client(tmp_path):
    store = RunStore(tmp_path / "api.db")
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_dashboard_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "QueueCast" in res.text


def test_list_attractions(client):
    ids = {a["id"] for a in client.get("/attractions").json()}
    assert "comet-coaster" in ids


def test_create_then_fetch_simulation(client):
    res = client.post("/simulations", json={"attraction_id": "comet-coaster", "seed": 1})
    assert res.status_code == 201
    run_id = res.json()["run_id"]

    run = client.get(f"/simulations/{run_id}").json()
    assert run["attraction_id"] == "comet-coaster"
    assert "peak_interval" in run

    waits = client.get(f"/simulations/{run_id}/wait-times").json()
    assert len(waits) == 48  # 12 park hours * 4 buckets

    assert len(client.get("/simulations").json()) == 1
    assert client.get("/reports/attractions").json()[0]["runs"] == 1


def test_unknown_attraction_is_404(client):
    res = client.post("/simulations", json={"attraction_id": "nope"})
    assert res.status_code == 404


def test_missing_run_is_404(client):
    assert client.get("/simulations/123").status_code == 404
    assert client.get("/simulations/123/wait-times").status_code == 404


@pytest.mark.parametrize("field,value", [("priority_share", 2), ("crowd_multiplier", -1)])
def test_validation_errors_are_422(client, field, value):
    res = client.post("/simulations", json={"attraction_id": "comet-coaster", field: value})
    assert res.status_code == 422


def test_compare_returns_one_row_per_share(client):
    res = client.post(
        "/simulations/compare",
        json={"attraction_id": "comet-coaster", "priority_shares": [0, 0.3, 0.6]},
    )
    rows = res.json()["results"]
    assert [r["priority_share"] for r in rows] == [0, 0.3, 0.6]


def test_compare_rejects_out_of_range_share(client):
    res = client.post(
        "/simulations/compare",
        json={"attraction_id": "comet-coaster", "priority_shares": [0.2, 1.5]},
    )
    assert res.status_code == 422
