"""Tests for checks/validity_checker.py."""
from models.player import Player, players_by_start_number
from models.draw_data import DrawDataRow
from checks.validity_checker import (
    check_all_players_only_exist_once,
    find_missing_players,
    find_players_not_in_draw_data,
    find_players_in_wrong_competition,
)

from tests.conftest import populate_players_by_start_number


def make_row(competition_class, start_number_a, start_number_b=''):
    return DrawDataRow('S', competition_class, '', '', '', '', True, False, start_number_a, start_number_b)


def test_check_all_players_only_exist_once_no_duplicates():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Betty', 'Bravo', 'SWE', 'Base2', 'F', 1100)

    duplicates = check_all_players_only_exist_once()

    assert duplicates == set()
    assert players_by_start_number[1].first_name == 'Alice'
    assert players_by_start_number[2].first_name == 'Betty'


def test_check_all_players_only_exist_once_detects_duplicate():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(1, 'Alice2', 'Alpha2', 'GER', 'Base1', 'F', 1200)

    duplicates = check_all_players_only_exist_once()

    assert duplicates == {1}
    # first occurrence wins in players_by_start_number
    assert players_by_start_number[1].first_name == 'Alice'


def test_find_missing_players_and_not_in_draw_data_diverge():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Betty', 'Bravo', 'SWE', 'Base2', 'F', 1100)
    Player(3, 'Cara', 'Charlie', 'GER', 'Base1', 'F', 1150)
    populate_players_by_start_number()

    # References players 1 and 2 (known), plus 99 (unknown/missing).
    # Player 3 is known but never referenced.
    draw_data = [
        make_row('W1', 1, 2),
        make_row('W1', 99),
    ]

    assert find_missing_players(draw_data) == {99}
    assert find_players_not_in_draw_data(draw_data) == {3}


def test_find_players_not_in_draw_data_when_fully_referenced():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Betty', 'Bravo', 'SWE', 'Base2', 'F', 1100)
    Player(3, 'Cara', 'Charlie', 'GER', 'Base1', 'F', 1150)
    populate_players_by_start_number()

    draw_data = [
        make_row('W1', 1, 2),
        make_row('W1', 3),
    ]

    assert find_players_not_in_draw_data(draw_data) == set()
    assert find_missing_players(draw_data) == set()


def test_find_players_in_wrong_competition_detects_mismatch():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Bob', 'Bravo', 'SWE', 'Base2', 'M', 1100)
    populate_players_by_start_number()

    draw_data = [
        make_row('W1', 1, 2),  # women's event, but start number 2 is male
        make_row('M1', 2),     # men's event, correct
    ]

    errors = find_players_in_wrong_competition(draw_data)

    assert len(errors) == 1
    assert 'Start number 2' in errors[0]


def test_find_players_in_wrong_competition_all_correct():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Bob', 'Bravo', 'SWE', 'Base2', 'M', 1100)
    populate_players_by_start_number()

    draw_data = [
        make_row('W1', 1),
        make_row('M1', 2),
    ]

    assert find_players_in_wrong_competition(draw_data) == []
