"""Tests for app/cli.py: parsing the command-line arguments."""

import pytest

from app.cli import parse_args
from core.version import __version__


def test_no_arguments_override_nothing():
    args = parse_args([])

    assert args.config is None
    assert args.players is None
    assert args.draw_input is None
    assert args.output is None
    assert args.seed is None
    assert args.log_level is None
    assert args.no_html is False
    assert args.no_menu is False


def test_every_argument_is_parsed():
    args = parse_args(
        [
            "--config", "c.ini",
            "--players", "p.csv",
            "--draw-input", "d.csv",
            "--output", "o.csv",
            "--seed", "123",
            "--log-level", "warning",
            "--no-html",
            "--no-menu",
        ]
    )  # fmt: skip

    assert args.config == "c.ini"
    assert args.players == "p.csv"
    assert args.draw_input == "d.csv"
    assert args.output == "o.csv"
    # Kept as text, like random_seed in config.ini.
    assert args.seed == "123"
    assert args.log_level == 30
    assert args.no_html is True
    assert args.no_menu is True


@pytest.mark.parametrize("value", ["debug", "DEBUG", "10"])
def test_log_level_accepts_names_and_numbers(value):
    assert parse_args(["--log-level", value]).log_level == 10


def test_unknown_log_level_is_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(["--log-level", "loud"])

    assert exc.value.code == 2
    assert "invalid log level 'loud'" in capsys.readouterr().err


def test_version_prints_the_version(capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(["--version"])

    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
