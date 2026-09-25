import pytest

from misc.config import config
from models.player import players_list, players_by_start_number


@pytest.fixture(autouse=True)
def reset_player_globals():
    """Player construction mutates module-level globals as a side effect; isolate each test."""
    players_list.clear()
    players_by_start_number.clear()
    yield
    players_list.clear()
    players_by_start_number.clear()


def _clear_config():
    for section in config.sections():
        config.remove_section(section)


@pytest.fixture(autouse=True)
def default_config():
    """Every test runs on the code defaults, never on a local config/config.ini.

    initialize_config never runs under pytest; this also drops any section a
    previous test put into the shared ConfigParser and forgot to remove.
    """
    _clear_config()
    yield
    _clear_config()


def populate_players_by_start_number():
    players_by_start_number.clear()
    for p in players_list:
        players_by_start_number[p.start_number] = p
