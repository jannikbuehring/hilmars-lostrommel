"""Tests for checks/validity_checker.py."""
from models.player import Player, players_by_start_number
from models.draw_data import DrawDataRow
from checks.validity_checker import (
    check_all_players_only_exist_once,
    find_missing_players,
    find_players_not_in_draw_data,
    find_players_in_wrong_competition,
    find_invalid_round_flags,
    find_group_no_pos_mismatch,
    find_duplicate_players_in_class,
    find_duplicate_group_positions,
    find_invalid_pairs,
    find_invalid_mixed_pairs,
    find_inconsistent_group_counts,
    find_missing_group_seedings,
    find_too_few_group_entries,
    find_draw_data_errors,
)

from tests.conftest import populate_players_by_start_number


def make_row(competition_class, start_number_a, start_number_b=''):
    return DrawDataRow('S', competition_class, '', '', '', '', True, False, start_number_a, start_number_b)


def group_row(competition, competition_class, start_number_a, start_number_b='', amount_of_groups='2', seeding='100'):
    """A group-stage row (no group_no/group_pos, no bracket flags)."""
    return DrawDataRow(competition, competition_class, seeding, amount_of_groups, '', '', False, False, start_number_a, start_number_b)


def bracket_row(competition, competition_class, group_no, group_pos, start_number_a, start_number_b='', main_round=True, consolation_round=False):
    """A bracket-stage row (group result given)."""
    return DrawDataRow(competition, competition_class, '', '', group_no, group_pos, main_round, consolation_round, start_number_a, start_number_b)


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


def test_find_invalid_round_flags_accepts_valid_rows():
    draw_data = [
        group_row('S', 'M1', 1),
        bracket_row('S', 'M1', '1', '1', 2),
        bracket_row('S', 'M1', '1', '4', 3, main_round=False, consolation_round=True),
    ]

    assert find_invalid_round_flags(draw_data) == []


def test_find_invalid_round_flags_detects_both_and_neither():
    draw_data = [
        bracket_row('S', 'M1', '1', '1', 1, main_round=True, consolation_round=True),
        bracket_row('S', 'M1', '1', '2', 2, main_round=False, consolation_round=False),
        DrawDataRow('S', 'M1', '', '2', '', '', True, False, 3, ''),
    ]

    errors = find_invalid_round_flags(draw_data)

    assert len(errors) == 3
    assert 'entry 1' in errors[0] and 'entry 2' in errors[1] and 'entry 3' in errors[2]


def test_find_group_no_pos_mismatch():
    draw_data = [
        group_row('S', 'M1', 1),
        bracket_row('S', 'M1', '1', '1', 2),
        DrawDataRow('S', 'M1', '', '', '1', '', False, False, 3, ''),
        DrawDataRow('S', 'M1', '', '', '', '2', True, False, 4, ''),
    ]

    errors = find_group_no_pos_mismatch(draw_data)

    assert len(errors) == 2
    assert 'entry 3' in errors[0] and 'entry 4' in errors[1]


def test_find_duplicate_players_in_class_detects_duplicates():
    draw_data = [
        group_row('S', 'M1', 1),
        group_row('S', 'M1', 1),
        group_row('D', 'M1', 2, 3),
        group_row('D', 'M1', 4, 2),
    ]

    errors = find_duplicate_players_in_class(draw_data)

    assert len(errors) == 2
    assert 'Start number 1' in errors[0]
    assert 'Start number 2' in errors[1]


def test_find_duplicate_players_in_class_allows_other_class_and_stage():
    draw_data = [
        group_row('S', 'M1', 1),
        group_row('S', 'M2', 1),
        group_row('D', 'M1', 1, 2),
        bracket_row('S', 'M1', '1', '1', 1),
    ]

    assert find_duplicate_players_in_class(draw_data) == []


def test_find_duplicate_group_positions():
    draw_data = [
        bracket_row('S', 'M1', '1', '1', 1),
        bracket_row('S', 'M1', '1', '2', 2),
        bracket_row('S', 'M1', '1', '2', 3),
        bracket_row('S', 'M1', '2', '2', 4),
        bracket_row('S', 'M2', '1', '2', 5),
    ]

    errors = find_duplicate_group_positions(draw_data)

    assert len(errors) == 1
    assert 'M1 group 1 has group_pos 2' in errors[0]


def test_find_invalid_pairs():
    draw_data = [
        group_row('S', 'M1', 1),
        group_row('D', 'M1', 2, 3),
        group_row('D', 'M1', 4),
        group_row('M', 'X1', 5),
        group_row('S', 'M1', 6, 7),
        group_row('D', 'M1', 8, 8),
    ]

    errors = find_invalid_pairs(draw_data)

    assert len(errors) == 4
    assert 'entry 4 has no partner' in errors[0]
    assert 'entry 5 has no partner' in errors[1]
    assert 'singles entry with a partner' in errors[2]
    assert 'with themselves' in errors[3]


def test_find_invalid_mixed_pairs():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Bob', 'Bravo', 'SWE', 'Base2', 'M', 1100)
    Player(3, 'Carl', 'Charlie', 'GER', 'Base1', 'M', 1150)
    populate_players_by_start_number()

    draw_data = [
        group_row('M', 'X1', 1, 2),
        group_row('M', 'X1', 2, 3),
        group_row('D', 'M1', 2, 3),
    ]

    errors = find_invalid_mixed_pairs(draw_data)

    assert len(errors) == 1
    assert 'entry 2/3' in errors[0]


def test_find_inconsistent_group_counts():
    draw_data = [
        group_row('S', 'M1', 1, amount_of_groups='2'),
        group_row('S', 'M1', 2, amount_of_groups='3'),
        group_row('S', 'M2', 3, amount_of_groups=''),
        group_row('S', 'W1', 4, amount_of_groups='2'),
        group_row('S', 'W1', 5, amount_of_groups='2'),
        bracket_row('S', 'W1', '1', '1', 6),
    ]

    errors = find_inconsistent_group_counts(draw_data)

    assert len(errors) == 2
    assert 'M1 has inconsistent #groups values: [2, 3]' in errors[0]
    assert 'M2 has group-stage rows without #groups' in errors[1]


def test_find_missing_group_seedings():
    draw_data = [
        group_row('S', 'M1', 1),
        group_row('S', 'M1', 2, seeding=''),
        bracket_row('S', 'M1', '1', '1', 3),  # bracket rows carry no seeding
    ]

    errors = find_missing_group_seedings(draw_data)

    assert errors == ['S M1 entry 2 has no seeding']


def test_find_too_few_group_entries():
    draw_data = [
        # 3 entries for 4 groups: one group would be empty
        *[group_row('S', 'M1', sn, amount_of_groups='4') for sn in (1, 2, 3)],
        # 4 entries for 4 groups: one per group is allowed
        *[group_row('S', 'M2', sn, amount_of_groups='4') for sn in (4, 5, 6, 7)],
        group_row('S', 'W1', 8, amount_of_groups='0'),
        # inconsistent #groups is left to find_inconsistent_group_counts
        group_row('S', 'W2', 9, amount_of_groups='2'),
        group_row('S', 'W2', 10, amount_of_groups='5'),
        bracket_row('S', 'W3', '1', '1', 11),
    ]

    errors = find_too_few_group_entries(draw_data)

    assert len(errors) == 2
    assert 'M1 has 3 group-stage entries for 4 groups' in errors[0]
    assert 'W1 has #groups=0' in errors[1]


def test_find_draw_data_errors_accepts_valid_input():
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Bob', 'Bravo', 'SWE', 'Base2', 'M', 1100)
    Player(3, 'Carl', 'Charlie', 'GER', 'Base1', 'M', 1150)
    populate_players_by_start_number()

    draw_data = [
        group_row('S', 'M1', 2),
        group_row('S', 'M1', 3),
        group_row('D', 'M1', 2, 3, amount_of_groups='1'),
        group_row('M', 'X1', 1, 2, amount_of_groups='1'),
        bracket_row('S', 'W1', '1', '1', 1),
    ]

    assert find_draw_data_errors(draw_data) == []


def test_find_draw_data_errors_on_committed_test_input():
    """Guards against false positives on a real-size input."""
    from misc.config import config
    from data_io.input_reader import read_draw_data, read_players

    if not config.has_section("files"):
        config.add_section("files")
    originals = {key: config["files"].get(key) for key in ("draw_data_path", "players_path")}
    config["files"]["draw_data_path"] = "input/draw_input_2026_20260626_test.csv"
    config["files"]["players_path"] = "input/players_2026_test.csv"
    try:
        read_players()
        draw_data = read_draw_data()
    finally:
        for key, value in originals.items():
            if value is None:
                config.remove_option("files", key)
            else:
                config["files"][key] = value

    assert check_all_players_only_exist_once() == set()
    assert find_missing_players(draw_data) == set()
    assert find_draw_data_errors(draw_data) == []
