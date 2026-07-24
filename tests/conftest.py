import pytest

from models.player import players_list, players_by_start_number


@pytest.fixture(autouse=True)
def reset_player_globals():
    """Player construction mutates module-level globals as a side effect; isolate each test."""
    players_list.clear()
    players_by_start_number.clear()
    yield
    players_list.clear()
    players_by_start_number.clear()


def populate_players_by_start_number():
    players_by_start_number.clear()
    for p in players_list:
        players_by_start_number[p.start_number] = p
