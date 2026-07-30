"""Tests for the per-quarter country distribution check in checks/bracket_checker.py."""
import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from checks.bracket_checker import check_country_balance_quarters, score_bracket


def register_players(specs):
    """specs: list of (start_number, country). Populates players_by_start_number."""
    for start_number, country in specs:
        Player(start_number, f'P{start_number}', f'L{start_number}', country, f'Base{start_number}', 'F', 1000)
    for p in players_list:
        players_by_start_number[p.start_number] = p


def singles(start_number):
    return DrawDataRow('S', 'M1', '', '', '', '', True, False, start_number, '')


def doubles(start_number_a, start_number_b):
    return DrawDataRow('D', 'W1', '', '', '', '', True, False, start_number_a, start_number_b)


@pytest.fixture(autouse=True)
def clear_seeding():
    seeding_by_start_numbers.clear()
    yield
    seeding_by_start_numbers.clear()


def test_country_spread_one_per_quarter_is_clean():
    """4 GER players, one in each quarter of an 8-match bracket -> no violation."""
    register_players([(i, 'GER' if i % 2 else 'SWE') for i in range(1, 17)])
    # 8 matches => 2 matches per quarter; one GER (odd start number) per quarter.
    matches = {
        1: [singles(1), singles(2)],    # Q0: GER, SWE
        2: [singles(4), singles(6)],    # Q0: SWE, SWE
        3: [singles(3), singles(8)],    # Q1: GER, SWE
        4: [singles(10), singles(12)],  # Q1
        5: [singles(5), singles(14)],   # Q2: GER
        6: [singles(16), singles(2)],   # Q2
        7: [singles(7), singles(4)],    # Q3: GER
        8: [singles(6), singles(8)],    # Q3
    }
    ger = [v for v in check_country_balance_quarters(matches, len(matches)) if v[0] == 'GER']
    assert not ger, f'Evenly spread GER players should not violate: {ger}'


def test_country_concentrated_in_one_quarter_violates():
    """All 4 GER players packed into quarter 0 -> violation equal to the excess."""
    register_players([(i, 'GER' if i <= 4 else 'SWE') for i in range(1, 17)])
    matches = {
        1: [singles(1), singles(2)],    # Q0: GER, GER
        2: [singles(3), singles(4)],    # Q0: GER, GER
        3: [singles(5), singles(6)],    # Q1
        4: [singles(7), singles(8)],    # Q1
        5: [singles(9), singles(10)],   # Q2
        6: [singles(11), singles(12)],  # Q2
        7: [singles(13), singles(14)],  # Q3
        8: [singles(15), singles(16)],  # Q3
    }
    ger = [v for v in check_country_balance_quarters(matches, len(matches)) if v[0] == 'GER']
    assert ger, 'Four GER players in one quarter should be flagged.'
    _country, counts, magnitude = ger[0]
    assert counts == [4, 0, 0, 0]
    # allowed = ceil(4/4) = 1, so the excess in Q0 is 3
    assert magnitude == 3


def test_small_bracket_uses_actual_quarter_count():
    """A 2-match bracket only has quarters 0/1; the allowance must not divide by 4."""
    register_players([(i, 'GER') for i in range(1, 5)])
    matches = {
        1: [singles(1), singles(2)],  # Q0
        2: [singles(3), singles(4)],  # Q1
    }
    # 4 GER over 2 quarters -> allowed 2 per quarter, actual 2 and 2 -> clean.
    assert not check_country_balance_quarters(matches, len(matches))


def test_full_country_doubles_team_is_forgiven():
    """A genuine GER/GER pair concentrated in a quarter is explained, not punished."""
    register_players([(i, 'GER') for i in range(1, 5)] + [(i, 'SWE') for i in range(5, 17)])
    matches = {
        1: [doubles(1, 2), doubles(5, 6)],      # Q0: GER/GER team + SWE/SWE
        2: [doubles(3, 4), doubles(7, 8)],      # Q0: GER/GER team + SWE/SWE
        3: [doubles(9, 10), doubles(11, 12)],   # Q1
        4: [doubles(13, 14), doubles(15, 16)],  # Q1
    }
    ger = [v for v in check_country_balance_quarters(matches, len(matches)) if v[0] == 'GER']
    assert not ger, f'Full-country doubles teams should be forgiven: {ger}'


def test_quarter_country_term_contributes_to_score():
    """A country concentrated in one quarter must cost more than a spread one."""
    register_players([(i, 'GER' if i <= 4 else f'C{i}') for i in range(1, 17)])
    # score_bracket's group-separation checks need real group_no/group_pos values.
    grouped = {sn: DrawDataRow('S', 'M1', '', '', sn, 1, True, False, sn, '') for sn in range(1, 17)}
    # All 4 GER players in quarter 0 of an 8-match bracket.
    matches = {i: [grouped[i * 2 - 1], grouped[i * 2]] for i in range(1, 9)}

    weights_without = {
        'quarter_split': 200, 'half_split': 150, 'first_vs_first': 100,
        'country_half': 10, 'country_quarter': 0, 'base_first': 20,
    }
    assert score_bracket(matches, len(matches)) > score_bracket(matches, len(matches), weights=weights_without)
