import pytest

from core.config import reset_settings
from models.player import players_by_start_number, players_list


@pytest.fixture(autouse=True)
def reset_player_globals():
    """Player construction mutates module-level globals as a side effect; isolate each test."""
    players_list.clear()
    players_by_start_number.clear()
    yield
    players_list.clear()
    players_by_start_number.clear()


@pytest.fixture(autouse=True)
def default_settings():
    """Every test runs on the code defaults, never on a local config/config.ini.

    initialize_config never runs under pytest; this also undoes any setting a
    previous test changed.
    """
    reset_settings()
    yield
    reset_settings()


def populate_players_by_start_number():
    players_by_start_number.clear()
    for p in players_list:
        players_by_start_number[p.start_number] = p
