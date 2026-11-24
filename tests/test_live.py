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


def test_single_rider_lines_fold_into_main_ride():
    payload = {"lands": [{"name": "New York", "rides": [
        {"id": 1, "name": "Revenge of the Mummy", "is_open": True, "wait_time": 40},
        {"id": 2, "name": "Revenge of the Mummy™ Single Rider", "is_open": True, "wait_time": 0},
        {"id": 3, "name": "E.T. Adventure", "is_open": True, "wait_time": 20},
    ]}], "rides": [
        # Queue-Times sometimes lists a single-rider line outside any land
        {"id": 4, "name": "E.T. Adventure® single rider", "is_open": False, "wait_time": 0},
        {"id": 5, "name": "Orphan Ride Single Rider", "is_open": True, "wait_time": 0},
    ]}
    rides = {r.name: r for r in parse_rides(payload)}
    assert set(rides) == {"Revenge of the Mummy", "E.T. Adventure"}
    assert rides["Revenge of the Mummy"].single_rider_open is True
    assert rides["E.T. Adventure"].single_rider_open is False  # its single-rider line is closed


def test_single_rider_zeros_do_not_lower_park_average():
    payload = {"lands": [{"name": "A", "rides": [
        {"name": "Hulk", "is_open": True, "wait_time": 40},
        {"name": "Hulk Single Rider", "is_open": True, "wait_time": 0},
    ]}]}
    client, _, _ = make_client(payload)
    data = client.get_park(64)
    assert data["open_rides"] == 1
    assert data["average_wait_min"] == 40.0


def test_closed_ride_never_shows_single_rider():
    payload = {"lands": [{"name": "A", "rides": [
        {"name": "Kong", "is_open": False, "wait_time": 0},
        {"name": "Kong Single Rider", "is_open": True, "wait_time": 0},
    ]}]}
    assert parse_rides(payload)[0].single_rider_open is False


def test_schedule_markers_are_hidden():
    payload = {"lands": [{"name": "Diagon Alley", "rides": [
        {"name": "Hogwarts Express™ - King's Cross Station", "is_open": True, "wait_time": 30},
        {"name": "Hogwarts™ Express - First Train", "is_open": False, "wait_time": 0},
        {"name": "Hogwarts™ Express – Last Train", "is_open": False, "wait_time": 0},
    ]}]}
    assert [r.name for r in parse_rides(payload)] == ["Hogwarts Express™ - King's Cross Station"]


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
    assert names[0] == "Magic Kingdom"


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
