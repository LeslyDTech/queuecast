import pytest

from queuecast.cli import _fmt_clock, main


def test_list(capsys):
    assert main(["list"]) == 0
    assert "revenge-of-the-mummy" in capsys.readouterr().out


def test_run(capsys):
    assert main(["run", "e-t-adventure", "--seed", "5"]) == 0
    out = capsys.readouterr().out
    assert "E.T. Adventure" in out
    assert "standby avg wait min" in out


def test_compare(capsys):
    assert main(["compare", "revenge-of-the-mummy", "--shares", "0", "0.5"]) == 0
    assert "50%" in capsys.readouterr().out


def test_unknown_attraction_exits():
    with pytest.raises(SystemExit):
        main(["run", "not-a-ride"])


@pytest.mark.parametrize(("minutes", "expected"), [(0, "9:00 AM"), (180, "12:00 PM"),
                                                   (195, "12:15 PM"), (660, "8:00 PM")])
def test_clock_format(minutes, expected):
    assert _fmt_clock(minutes) == expected


def test_calibrate_command(tmp_path, capsys):
    import json

    data = tmp_path / "rides.json"
    data.write_text(json.dumps([{
        "id": "small", "name": "Small Ride", "vehicle_capacity": 10, "dispatch_interval_s": 60,
        "base_arrivals_per_hour": None, "real_avg_posted_wait_min": 15,
    }]))
    assert main(["calibrate", "--file", str(data)]) == 0
    assert "small" in capsys.readouterr().out
    assert json.loads(data.read_text())[0]["base_arrivals_per_hour"] > 0
