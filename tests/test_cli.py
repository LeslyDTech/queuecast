import pytest

from queuecast.cli import _fmt_clock, main


def test_list(capsys):
    assert main(["list"]) == 0
    assert "comet-coaster" in capsys.readouterr().out


def test_run(capsys):
    assert main(["run", "starlight-spinner", "--seed", "5"]) == 0
    out = capsys.readouterr().out
    assert "Starlight Spinner" in out
    assert "standby avg wait min" in out


def test_compare(capsys):
    assert main(["compare", "comet-coaster", "--shares", "0", "0.5"]) == 0
    assert "50%" in capsys.readouterr().out


def test_unknown_attraction_exits():
    with pytest.raises(SystemExit):
        main(["run", "not-a-ride"])


@pytest.mark.parametrize(("minutes", "expected"), [(0, "9:00 AM"), (180, "12:00 PM"),
                                                   (195, "12:15 PM"), (660, "8:00 PM")])
def test_clock_format(minutes, expected):
    assert _fmt_clock(minutes) == expected
