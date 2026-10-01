import pytest

from core.config import reset_settings
from models.draw_data import seeding_by_start_numbers
from models.player import players_by_start_number, players_list


def _clear_registries():
    players_list.clear()
    players_by_start_number.clear()
    seeding_by_start_numbers.clear()


@pytest.fixture(autouse=True)
def reset_registries():
    """Player construction and read_draw_data fill module-level registries; isolate each test."""
    _clear_registries()
    yield
    _clear_registries()


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
