import pytest
from fastapi.testclient import TestClient

from queuecast.api import app, get_live_client
from queuecast.live import API_URL, LiveDataError, LiveWaitClient, parse_rides

# Trimmed copy of a real Queue-Times response shape.
SAMPLE = {
    "lands": [
        {
            "id": 1,
            "name": "Springfield",
            "rides": [
                {"id": 1, "name": "Simpsons Ride", "is_open": True, "wait_time": 25,
                 "last_updated": "2026-11-24T15:36:23.000Z"},
                {"id": 2, "name": "Twirl n Hurl", "is_open": False, "wait_time": 0,
                 "last_updated": "2026-11-24T15:36:23.000Z"},
            ],
        },
        {
            "id": 2,
            "name": "Diagon Alley",
            "rides": [
                {"id": 3, "name": "Gringotts", "is_open": True, "wait_time": 65,
                 "last_updated": "2026-11-24T15:36:23.000Z"},
            ],
        },
    ],
    "rides": [],
}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_client(payload=SAMPLE):
    calls = []
    clock = FakeClock()

    def fetch(url):
        calls.append(url)
        return payload

    return LiveWaitClient(fetch=fetch, clock=clock, cache_seconds=300), calls, clock


def test_parse_sorts_longest_open_wait_first_and_closed_last():
    rides = parse_rides(SAMPLE)
    assert [r.name for r in rides] == ["Gringotts", "Simpsons Ride", "Twirl n Hurl"]
    assert rides[0].land == "Diagon Alley"
    assert rides[0].id == 3
    assert rides[-1].wait_time_min is None  # closed rides have no wait


def test_parse_handles_rides_without_lands():
    rides = parse_rides({"lands": [], "rides": [
        {"name": "Solo", "is_open": True, "wait_time": 5, "last_updated": ""}]})
    assert rides[0].name == "Solo"
    assert rides[0].land == ""


def test_parse_rejects_bad_payload():
    with pytest.raises(LiveDataError):
        parse_rides(["not", "a", "dict"])


def test_summary_and_attribution():
    client, calls, _ = make_client()
    data = client.get_park(65)
    assert calls == [API_URL.format(park_id=65)]
    assert data["park"] == "Universal Studios Florida"
    assert data["open_rides"] == 2
    assert data["average_wait_min"] == 45.0
    assert data["attribution"]["text"] == "Powered by Queue-Times.com"


def test_cache_avoids_refetching_within_five_minutes():
    client, calls, clock = make_client()
    client.get_park(65)
    clock.now = 299
    client.get_park(65)
    assert len(calls) == 1
    clock.now = 301
    client.get_park(65)
    assert len(calls) == 2


def test_unsupported_park_never_calls_api():
    client, calls, _ = make_client()
    with pytest.raises(KeyError):
        client.get_park(999)
    assert calls == []


def test_all_closed_park_has_no_average():
    closed = {"lands": [{"name": "A", "rides": [
        {"name": "X", "is_open": False, "wait_time": 0, "last_updated": ""}]}]}
    client, _, _ = make_client(closed)
    assert client.get_park(64)["average_wait_min"] is None


# ---- API routes ----------------------------------------------------------

@pytest.fixture
def api():
    client, _, _ = make_client()
    app.dependency_overrides[get_live_client] = lambda: client
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_live_parks_route(api):
    names = [p["name"] for p in api.get("/live/parks").json()]
    assert "Islands of Adventure" in names


def test_live_park_route(api):
    res = api.get("/live/parks/65")
    assert res.status_code == 200
    assert res.json()["rides"][0]["name"] == "Gringotts"


def test_unknown_park_is_404(api):
    assert api.get("/live/parks/999").status_code == 404


def test_upstream_failure_is_502():
    def broken(url):
        raise LiveDataError("timed out")

    app.dependency_overrides[get_live_client] = lambda: LiveWaitClient(fetch=broken)
    try:
        res = TestClient(app).get("/live/parks/65")
        assert res.status_code == 502
        assert "timed out" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_dashboard_shows_attribution(api):
    assert "Powered by Queue-Times.com" in api.get("/").text
