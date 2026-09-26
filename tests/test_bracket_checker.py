"""Tests for the violation checks and scoring in checks/bracket_checker.py.

Covers the per-quarter country distribution check plus the three round-one
matchup-quality rules (top-gets-an-easy-opponent, no bottom-vs-bottom, no
same-country pairing) and the weight ladder that ranks them.
"""
import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from checks.bracket_checker import (
    check_bye_balance_halves,
    check_country_balance_halves,
    check_country_balance_quarters,
    check_no_first_vs_first,
    check_top_easy_first_round,
    check_no_bottom_vs_bottom,
    check_country_conflicts_first_round,
    check_half_group_separation,
    check_quarter_group_separation,
    quarter_misfits,
    check_placement_balance_quarters,
    check_round_two_matchups,
    derive_round_two_matches,
    forced_first_vs_first,
    split_first_vs_first,
    score_bracket,
    score_bracket_tiers,
    score_round_two,
    validate_bracket_weights,
    DEFAULT_BRACKET_WEIGHTS,
    ROUND_TWO_DEFAULT_WEIGHTS,
)
from models.bracket_geometry import BracketGeometry

# score_bracket's own defaults, passed explicitly so a partially-specified weights
# dict never silently reintroduces a term through the .get() fallbacks.
DEFAULT_WEIGHTS = DEFAULT_BRACKET_WEIGHTS


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


def tiered(start_number, group_no, group_pos):
    """A singles row that carries a group placement (singles() leaves it blank)."""
    return DrawDataRow('S', 'M1', '', '', group_no, group_pos, True, False, start_number, '')


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


def _ger_doubles_field():
    """1-4 form two GER/GER teams, 5/6 a GER/ENG team; everyone else is SWE."""
    register_players(
        [(i, 'GER') for i in range(1, 6)] + [(6, 'ENG')] + [(i, 'SWE') for i in range(7, 41)]
    )


def _swe_team(k):
    return doubles(5 + 2 * k, 6 + 2 * k)  # k >= 1 -> two SWE players


def test_full_country_doubles_teams_sharing_a_quarter_violate():
    """Two GER/GER teams in one quarter are a concentration, not a lumpy split."""
    _ger_doubles_field()
    # 8 matches => 2 matches per quarter; both GER/GER teams in quarter 0.
    matches = {i: [_swe_team(2 * i), _swe_team(2 * i + 1)] for i in range(1, 9)}
    matches[1] = [doubles(1, 2), _swe_team(1)]
    matches[2] = [doubles(3, 4), _swe_team(2)]
    ger = [v for v in check_country_balance_quarters(matches, len(matches)) if v[0] == 'GER']
    assert ger, 'Two GER/GER teams in one quarter should be flagged.'
    _country, counts, magnitude = ger[0]
    assert counts == [4, 0, 0, 0]
    # allowed = ceil(4/4) + 1 (doubles) = 2, so the excess in Q0 is 2
    assert magnitude == 2


def test_full_country_doubles_teams_spread_are_clean():
    """One GER/GER team per quarter is as even as two-player teams can get."""
    _ger_doubles_field()
    matches = {i: [_swe_team(2 * i), _swe_team(2 * i + 1)] for i in range(1, 9)}
    matches[1] = [doubles(1, 2), _swe_team(1)]  # Q0
    matches[3] = [doubles(3, 4), _swe_team(2)]  # Q1
    ger = [v for v in check_country_balance_quarters(matches, len(matches)) if v[0] == 'GER']
    assert not ger, f'GER/GER teams in different quarters should not violate: {ger}'


def test_full_country_doubles_teams_do_not_excuse_half_imbalance():
    """2x GER/GER + GER/ENG all in one half is 5/0, and 3/2 was available."""
    _ger_doubles_field()
    matches = {i: [_swe_team(2 * i), _swe_team(2 * i + 1)] for i in range(1, 9)}
    matches[1] = [doubles(1, 2), _swe_team(1)]
    matches[2] = [doubles(3, 4), _swe_team(2)]
    matches[3] = [doubles(5, 6), _swe_team(3)]
    ger = [v for v in check_country_balance_halves(matches, len(matches)) if v[0] == 'GER']
    # diff 5 - allowed 2 (doubles)
    assert ger == [('GER', 5, 0, 3)]

    # Same teams split 3/2 across the halves -> clean.
    matches[2] = [_swe_team(2), _swe_team(4)]
    matches[5] = [doubles(3, 4), _swe_team(10)]
    ger = [v for v in check_country_balance_halves(matches, len(matches)) if v[0] == 'GER']
    assert not ger, f'A 3/2 split should not violate: {ger}'


def test_quarter_country_term_contributes_to_score():
    """A country concentrated in one quarter must cost more than a spread one."""
    register_players([(i, 'GER' if i <= 4 else f'C{i}') for i in range(1, 17)])
    # score_bracket's group-separation checks need real group_no/group_pos values.
    grouped = {sn: DrawDataRow('S', 'M1', '', '', sn, 1, True, False, sn, '') for sn in range(1, 17)}
    # All 4 GER players in quarter 0 of an 8-match bracket.
    matches = {i: [grouped[i * 2 - 1], grouped[i * 2]] for i in range(1, 9)}

    weights_without = {**DEFAULT_WEIGHTS, 'country_quarter': 0}
    assert score_bracket(matches, len(matches)) > score_bracket(matches, len(matches), weights=weights_without)


# ---------------------------------------------------------------------------
# Bye distribution across the halves.
# ---------------------------------------------------------------------------

def bye_bracket(bye_matches, number_of_matches=8):
    """An 8-match bracket whose matches in *bye_matches* hold a BYE."""
    register_players([(i, f'C{i}') for i in range(1, number_of_matches * 2 + 1)])
    matches = {}
    for match_idx in range(1, number_of_matches + 1):
        if match_idx in bye_matches:
            matches[match_idx] = [singles(match_idx * 2 - 1), 'BYE']
        else:
            matches[match_idx] = [singles(match_idx * 2 - 1), singles(match_idx * 2)]
    return matches


def test_evenly_split_byes_are_clean():
    """3 byes per half of an 8-match bracket -> no violation."""
    assert not check_bye_balance_halves(bye_bracket({1, 2, 3, 5, 6, 7}), 8)


def test_odd_bye_count_may_differ_by_one():
    """5 byes can only ever split 3/2, so that must not be flagged."""
    assert not check_bye_balance_halves(bye_bracket({1, 2, 3, 5, 6}), 8)


def test_uneven_byes_across_halves_violate():
    """The S M1 consolation failure mode: 6 byes split 4/2."""
    violations = check_bye_balance_halves(bye_bracket({1, 2, 3, 4, 5, 6}), 8)
    assert violations, 'A 4/2 bye split should be flagged.'
    count_half0, count_half1, magnitude = violations[0]
    assert (count_half0, count_half1) == (4, 2)
    # allowed difference is 1, so the excess is 1
    assert magnitude == 1


def test_bye_balance_is_not_part_of_the_score():
    """Byes never move after Phase 1b, so scoring the term would only stop the
    phase-5 `score == 0` early exits from ever firing."""
    grouped = {sn: DrawDataRow('S', 'M1', '', '', sn, 1, True, False, sn, '') for sn in range(1, 17)}
    register_players([(i, f'C{i}') for i in range(1, 17)])
    balanced = {i: [grouped[i * 2 - 1], 'BYE' if i in (1, 2, 3, 5, 6, 7) else grouped[i * 2]] for i in range(1, 9)}
    lopsided = {i: [grouped[i * 2 - 1], 'BYE' if i in (1, 2, 3, 4, 5, 6) else grouped[i * 2]] for i in range(1, 9)}

    assert check_bye_balance_halves(lopsided, 8) and not check_bye_balance_halves(balanced, 8)
    assert score_bracket(lopsided, 8) == score_bracket(balanced, 8)


# ---------------------------------------------------------------------------
# Round-one matchup quality: top gets a BYE or a bottom-tier opponent,
# no bottom-vs-bottom, no same-country pairing.
# ---------------------------------------------------------------------------

def three_tier_matches(pairings):
    """Build a matches dict from [(pos_a, pos_b), ...], one group per participant.

    Each participant gets its own group_no so the group-separation checks stay out
    of the way; start numbers are allocated sequentially.
    """
    matches = {}
    start_number = 1
    for match_idx, (pos_a, pos_b) in enumerate(pairings, start=1):
        side = []
        for pos in (pos_a, pos_b):
            if pos == 'BYE':
                side.append('BYE')
            else:
                side.append(tiered(start_number, start_number, pos))
                start_number += 1
        matches[match_idx] = side
    return matches


def test_top_gets_bottom_opponent_is_clean():
    """1-vs-3 is exactly what the rule asks for."""
    matches = three_tier_matches([(1, 3), (1, 3), (2, 2), (2, 3)])
    assert check_top_easy_first_round(matches) == []


def test_top_against_middle_violates():
    """A group winner facing a runner-up is the violation the rule exists for."""
    matches = three_tier_matches([(1, 2), (1, 3), (2, 3), (3, 2)])
    violations = check_top_easy_first_round(matches)
    assert len(violations) == 1
    match_idx, player, opponent = violations[0]
    assert match_idx == 1
    assert (player.group_pos, opponent.group_pos) == (1, 2)


def test_top_with_bye_is_clean():
    """A BYE satisfies the earned-easier-matchup right outright."""
    matches = three_tier_matches([(1, 'BYE'), ('BYE', 1), (2, 3), (3, 2)])
    assert check_top_easy_first_round(matches) == []


def test_partial_match_is_not_a_violation():
    """slots_to_matches emits short and half-filled matches mid-draw."""
    row = tiered(1, 1, 1)
    matches = {1: [None, row], 2: [tiered(2, 2, 1)], 3: [], 4: [None, None]}
    assert check_top_easy_first_round(matches) == []
    assert check_no_bottom_vs_bottom(matches) == []
    assert check_country_conflicts_first_round(matches) == []


def test_top_vs_top_is_left_to_first_vs_first():
    """The two terms partition the space; rule A never double-charges a 1-vs-1."""
    matches = three_tier_matches([(1, 1), (2, 3), (2, 3), (3, 2)])
    assert check_top_easy_first_round(matches) == []
    assert len(check_no_first_vs_first(matches)) == 1


def test_two_tier_bracket_is_exempt():
    """Doubles/mixed have only 2 tiers, where "bottom" IS the runner-up."""
    register_players([(i, f'C{i}') for i in range(1, 9)])
    matches = three_tier_matches([(1, 2), (2, 2), (1, 2), (2, 2)])
    assert check_top_easy_first_round(matches) == []
    assert check_no_bottom_vs_bottom(matches) == []
    # The country rule has no tier guard, so it still applies here.
    assert check_country_conflicts_first_round(matches) == []


def test_bottom_vs_bottom_flagged():
    """3-vs-3 is not okay, 2-vs-3 is (open_questions.md 29.07)."""
    matches = three_tier_matches([(3, 3), (2, 3), (1, 3), (2, 2)])
    violations = check_no_bottom_vs_bottom(matches)
    assert len(violations) == 1
    assert violations[0][0] == 1


def test_relative_tiers_in_consolation():
    """Bounds are relative to the bracket: a consolation draw runs 4..6."""
    matches = three_tier_matches([(4, 6), (4, 5), (6, 6), (5, 6)])
    top_violations = check_top_easy_first_round(matches)
    assert [v[0] for v in top_violations] == [2]          # 4-vs-6 clean, 4-vs-5 not
    assert [v[0] for v in check_no_bottom_vs_bottom(matches)] == [3]


# ---------------------------------------------------------------------------
# Half separation: relative to the bracket's top position, like the tiers above.
# ---------------------------------------------------------------------------

def group_layout_matches(placements, shift=0):
    """Build an 8-match bracket from {match_idx: [(group_no, group_pos), ...]}.

    *shift* moves every group_pos by the same amount, so shift=3 turns a main
    layout (1/2/3) into the identical consolation layout (4/5/6).
    """
    matches = {idx: [] for idx in range(1, 9)}
    start_number = 1
    for match_idx, sides in placements.items():
        for group_no, group_pos in sides:
            matches[match_idx].append(tiered(start_number, group_no, group_pos + shift))
            start_number += 1
    return matches


# Group 1's winner (match 1) and runner-up (match 2) share the upper half.
WINNER_AND_RUNNER_UP_SAME_HALF = {
    1: [(1, 1), (2, 3)],
    2: [(1, 2), (2, 2)],
    6: [(1, 3), (2, 1)],
}


def test_half_separation_flags_runner_up_in_winners_half():
    matches = group_layout_matches(WINNER_AND_RUNNER_UP_SAME_HALF)
    violations = check_half_group_separation(matches, len(matches))
    assert (1, "positions 1/4 and 2/3 share a half") in violations


def test_half_separation_is_relative_in_consolation():
    """The same layout shifted to 4/5/6 must report the same violations."""
    main = group_layout_matches(WINNER_AND_RUNNER_UP_SAME_HALF)
    consolation = group_layout_matches(WINNER_AND_RUNNER_UP_SAME_HALF, shift=3)
    main_violations = check_half_group_separation(main, len(main))
    consolation_violations = check_half_group_separation(consolation, len(consolation))
    assert [g for g, _ in consolation_violations] == [g for g, _ in main_violations]
    assert (1, "positions 4/7 and 5/6 share a half") in consolation_violations
    assert score_bracket(consolation, len(consolation), DEFAULT_WEIGHTS) == \
        score_bracket(main, len(main), DEFAULT_WEIGHTS)


def test_half_separation_clean_consolation_layout():
    matches = group_layout_matches({1: [(1, 1), (2, 3)], 2: [(2, 2)], 6: [(1, 2), (2, 1)], 8: [(1, 3)]}, shift=3)
    assert check_half_group_separation(matches, len(matches)) == []


def test_half_separation_bounds_override():
    """A partial state without the winners must not re-anchor on the runners-up."""
    matches = {idx: [] for idx in range(1, 9)}
    matches[1] = [tiered(1, 1, 5)]
    matches[6] = [tiered(2, 1, 6)]
    # Derived from the matches, 5 reads as the top and 6 as its runner-up: clean.
    assert check_half_group_separation(matches, len(matches)) == []
    # With the real top (4), 5 and 6 both belong opposite the winner: split.
    assert check_half_group_separation(matches, len(matches), bounds=(4, 6)) == [
        (1, "positions 5/6 split across halves"),
    ]


def test_same_country_round_one_flagged():
    """Two players of one country must not meet in round one."""
    register_players([(1, 'GER'), (2, 'GER'), (3, 'GER'), (4, 'SWE')])
    matches = {
        1: [tiered(1, 1, 1), tiered(2, 2, 3)],   # GER vs GER
        2: [tiered(3, 3, 1), tiered(4, 4, 3)],   # GER vs SWE
    }
    violations = check_country_conflicts_first_round(matches)
    assert len(violations) == 1
    assert violations[0][0] == 1 and violations[0][1] == ['GER']


def test_same_country_doubles_teams():
    """A team's own two countries are not a conflict; an overlap with the opponent is."""
    register_players([(1, 'GER'), (2, 'GER'), (3, 'GER'), (4, 'SWE'),
                      (5, 'SWE'), (6, 'SWE'), (7, 'GER'), (8, 'SWE')])
    # GER/GER vs GER/SWE -> shares GER.  SWE/SWE vs GER/SWE -> shares SWE.
    assert len(check_country_conflicts_first_round({1: [doubles(1, 2), doubles(3, 4)]})) == 1
    assert len(check_country_conflicts_first_round({1: [doubles(5, 6), doubles(7, 8)]})) == 1
    # All-GER team vs all-SWE team -> no shared country.
    assert check_country_conflicts_first_round({1: [doubles(1, 2), doubles(5, 6)]}) == []


def test_new_terms_contribute_to_score():
    """Each new term must actually move the score."""
    register_players([(i, 'GER' if i in (5, 6) else f'C{i}') for i in range(1, 9)])
    matches = {
        1: [tiered(1, 1, 1), tiered(2, 2, 2)],   # rule A: winner vs runner-up
        2: [tiered(3, 3, 3), tiered(4, 4, 3)],   # rule B: 3rd vs 3rd
        3: [tiered(5, 5, 2), tiered(6, 6, 3)],   # rule C: GER vs GER
        4: [tiered(7, 7, 1), tiered(8, 8, 3)],   # clean
    }
    baseline = score_bracket(matches, len(matches))
    for term in ('top_easy_opponent', 'bottom_vs_bottom', 'country_first'):
        without = score_bracket(matches, len(matches), weights={**DEFAULT_WEIGHTS, term: 0})
        assert baseline > without, f'{term} does not contribute to the score'


def test_new_weights_outrank_country_distribution():
    """"1. gegen dritter oder freilos ist wichtiger als länderverteilung"."""
    register_players([(i, f'C{i}') for i in range(1, 9)])
    # One rule-A violation, no country imbalance.
    rule_a = {
        1: [tiered(1, 1, 1), tiered(2, 2, 2)],
        2: [tiered(3, 3, 1), tiered(4, 4, 3)],
        3: [tiered(5, 5, 1), tiered(6, 6, 3)],
        4: [tiered(7, 7, 1), tiered(8, 8, 3)],
    }
    assert len(check_top_easy_first_round(rule_a)) == 1
    weights = DEFAULT_WEIGHTS
    # A single rule-A violation must cost more than a 3-unit country-half imbalance.
    assert weights['top_easy_opponent'] > 3 * weights['country_half']
    assert weights['bottom_vs_bottom'] > 2 * weights['country_half']
    for term in ('top_easy_opponent', 'bottom_vs_bottom', 'country_first'):
        assert weights[term] > weights['country_half'] > weights['country_quarter']


def test_default_ladders_are_consistent():
    """The default weights keep every in-tier order and the round-two band.

    The live config.ini is checked by the same function at draw time
    (bracket_drawer logs a warning per problem), not here: the suite runs on
    the defaults only.
    """
    assert validate_bracket_weights(DEFAULT_WEIGHTS, ROUND_TWO_DEFAULT_WEIGHTS) == []


@pytest.mark.parametrize('weights, round_two, fragment', [
    ({'top_easy_opponent': 40}, {}, 'top_easy_opponent (40)'),
    ({'country_quarter': 15}, {}, 'country weights must descend'),
    # 45 is no longer below the lowest round-one matchup weight
    ({'bottom_vs_bottom': 45, 'top_easy_opponent': 70}, {}, 'round_two_first_vs_first (45)'),
    # a country weight above the round-two band
    ({'country_first': 40}, {}, 'round_two_bottom_vs_bottom (38)'),
    ({}, {'round_two_country_first': 12}, 'round_two_country_first (12)'),
])
def test_validate_bracket_weights_reports_a_broken_ladder(weights, round_two, fragment):
    problems = validate_bracket_weights(weights, round_two)
    assert any(fragment in problem for problem in problems), problems


def _h4_brackets():
    """Review finding H4: the same 8 players, 2 winners / 3 runners-up / 3 thirds.

    X: a winner faces a runner-up (1 top_easy), no same-country pairing.
    Y: both winners face a 3rd, but 3 pairings are same-country.
    """
    register_players([
        (1, 'GER'), (2, 'SWE'),                # winners
        (3, 'DEN'), (4, 'AUT'), (5, 'FRA'),    # runners-up
        (6, 'GER'), (7, 'SWE'), (8, 'DEN'),    # thirds
    ])
    w1, w2 = tiered(1, 1, 1), tiered(2, 2, 1)
    r1, r2, r3 = tiered(3, 3, 2), tiered(4, 4, 2), tiered(5, 5, 2)
    t1, t2, t3 = tiered(6, 6, 3), tiered(7, 7, 3), tiered(8, 8, 3)
    x = {1: [w1, r1], 2: [w2, t1], 3: [r2, t2], 4: [r3, t3]}
    y = {1: [w1, t1], 2: [w2, t2], 3: [r1, t3], 4: [r2, r3]}
    return x, y


def test_matchup_tier_outranks_same_country_pairings():
    """H4: one winner-vs-runner-up must rank worse than any number of same-country
    pairings, although the summed weights (70 vs 3 x 35) say the opposite."""
    x, y = _h4_brackets()
    assert len(check_top_easy_first_round(x)) == 1
    assert len(check_country_conflicts_first_round(y)) == 3
    assert len(check_top_easy_first_round(y)) == 0

    x_tiers = score_bracket_tiers(x, 4, DEFAULT_WEIGHTS)
    y_tiers = score_bracket_tiers(y, 4, DEFAULT_WEIGHTS)
    assert x_tiers[0] == y_tiers[0] == 0
    assert x_tiers > y_tiers
    # The weighted sum alone ranks them the other way round -- which is the bug.
    assert score_bracket(x, 4, DEFAULT_WEIGHTS) < score_bracket(y, 4, DEFAULT_WEIGHTS)


def test_score_bracket_is_the_sum_of_its_tiers():
    x, y = _h4_brackets()
    for matches in (x, y):
        assert score_bracket(matches, 4, DEFAULT_WEIGHTS) == sum(score_bracket_tiers(matches, 4, DEFAULT_WEIGHTS))


# ---------------------------------------------------------------------------
# Round-two matchup quality (the pairings the byes already decide).
# ---------------------------------------------------------------------------

def test_round_two_pairs_only_bye_winners():
    """Round-two match r is fed by first-round matches 2r-1 and 2r."""
    matches = three_tier_matches([(1, 'BYE'), ('BYE', 3), (2, 3), (1, 'BYE')])
    round_two = derive_round_two_matches(matches)
    assert sorted(round_two) == [1, 2]
    # Pair 1: both feeders were byes, so both winners are known.
    assert [p.group_pos for p in round_two[1]] == [1, 3]
    # Pair 2: match 3 is a real pairing, so that side stays open.
    assert round_two[2][0] is None
    assert round_two[2][1].group_pos == 1


def test_round_two_undetermined_side_is_never_a_violation():
    """A real first-round match leaves the next round open — nothing to grade."""
    matches = three_tier_matches([(1, 'BYE'), (2, 2), (1, 'BYE'), (3, 3)])
    violations = check_round_two_matchups(matches, bounds=(1, 3))
    assert all(v == [] for v in violations.values())
    assert score_round_two(matches, bounds=(1, 3)) == 0


def test_round_two_bounds_override_prevents_a_tier_misfire():
    """The decided round-two participants alone cannot reveal the bracket's tiers.

    Here every decided round-two player is a winner or a runner-up, so a derived
    range reads (1, 2) — two tiers — and the `bottom - top >= 2` guard switches
    the rule off, silently relabelling the runner-up as an acceptable "bottom"
    opponent.  The parent bracket knows better.
    """
    matches = three_tier_matches([(1, 'BYE'), ('BYE', 2), (3, 3), (3, 3)])
    round_two = derive_round_two_matches(matches)
    assert check_top_easy_first_round(round_two) == []
    flagged = check_top_easy_first_round(round_two, bounds=(1, 3))
    assert len(flagged) == 1
    _match_idx, player, opponent = flagged[0]
    assert (player.group_pos, opponent.group_pos) == (1, 2)


def test_round_two_is_not_part_of_the_score():
    """Frozen after Phase 1b, so scoring it would only break the phase-5 early exits.

    Two brackets with identical round-one content and opposite round-two quality:
    score_bracket cannot tell them apart, score_round_two must.
    """
    good = three_tier_matches([(1, 'BYE'), ('BYE', 3), (2, 'BYE'), ('BYE', 2)])
    bad = three_tier_matches([(1, 'BYE'), ('BYE', 2), (3, 'BYE'), ('BYE', 2)])
    assert score_bracket(good, 4) == score_bracket(bad, 4)
    assert score_round_two(bad, bounds=(1, 3)) > score_round_two(good, bounds=(1, 3)) == 0


def test_round_two_weights_sit_between_round_one_matchups_and_country():
    """The 36..49 band, asserted against the default ladder.

    Deliberately spelled out rather than delegated to validate_bracket_weights,
    so a mistake in that function cannot hide a broken default.
    """
    weights = DEFAULT_WEIGHTS
    tier_weights = [
        ROUND_TWO_DEFAULT_WEIGHTS[key] for key in (
            'round_two_first_vs_first',
            'round_two_top_easy_opponent',
            'round_two_bottom_vs_bottom',
        )
    ]
    round_one_floor = min(
        weights['first_vs_first'], weights['top_easy_opponent'], weights['bottom_vs_bottom']
    )
    country_ceiling = max(
        weights['country_first'], weights['country_half'], weights['country_quarter']
    )
    assert max(tier_weights) < round_one_floor
    assert min(tier_weights) > country_ceiling
    # The round-two country term ranks below round one's, not above.
    assert (weights['country_half']
            > ROUND_TWO_DEFAULT_WEIGHTS['round_two_country_first']
            > weights['country_quarter'])


# ---------------------------------------------------------------------------
# Placement tiers spread over the two quarters of each half.
# ---------------------------------------------------------------------------

TIER_BRACKET_MATCHES = 16


def tier_bracket(quarter_positions):
    """A 16-match bracket from {quarter: [group_pos, ...]}, four matches per quarter.

    One participant per match, so no match is ever a real pairing: every round-one
    matchup term stays at zero and the brackets differ ONLY in how the tiers are
    spread across the quarters.
    """
    matches = {idx: [] for idx in range(1, TIER_BRACKET_MATCHES + 1)}
    specs = []
    start_number = 1
    for quarter, positions in quarter_positions.items():
        for offset, position in enumerate(positions):
            specs.append((start_number, quarter * 4 + offset + 1, position))
            start_number += 1
    register_players([(sn, f'C{sn}') for sn, _m, _p in specs])
    for sn, match_idx, position in specs:
        matches[match_idx] = [tiered(sn, sn, position)]
    return matches


def test_tier_split_evenly_within_each_half_is_clean():
    bracket = tier_bracket({0: [2, 2], 1: [2, 2]})
    assert check_placement_balance_quarters(bracket, TIER_BRACKET_MATCHES) == []


def test_tier_may_differ_by_one_within_a_half():
    """An odd tier count cannot split evenly, so 2/1 must not be flagged."""
    bracket = tier_bracket({0: [2, 2], 1: [2]})
    assert check_placement_balance_quarters(bracket, TIER_BRACKET_MATCHES) == []


def test_lopsided_tier_within_a_half_violates():
    """The S M2 failure mode one level down: 3/1 inside a half."""
    bracket = tier_bracket({0: [2, 2, 2], 1: [2]})
    violations = check_placement_balance_quarters(bracket, TIER_BRACKET_MATCHES)
    assert len(violations) == 1
    assert violations[0] == (2, [3, 1, 0, 0], 1)


def test_tier_confined_to_one_half_is_not_flagged():
    """The whole point of comparing WITHIN a half rather than across all four.

    The separation rules pin 2nd/3rd to the half opposite their group's anchor, so
    an all-in-one-half split is structurally forced; only the quarter inside that
    half is a free choice, and here it is balanced 2/2.  A global spread over all
    four quarters would charge for this.
    """
    bracket = tier_bracket({2: [3, 3], 3: [3, 3]})
    assert check_placement_balance_quarters(bracket, TIER_BRACKET_MATCHES) == []


def test_tier_balance_is_not_part_of_the_score():
    balanced = tier_bracket({0: [2, 2], 1: [2, 2]})
    lopsided = tier_bracket({0: [2, 2, 2], 1: [2]})
    assert check_placement_balance_quarters(lopsided, TIER_BRACKET_MATCHES)
    assert not check_placement_balance_quarters(balanced, TIER_BRACKET_MATCHES)
    assert (score_bracket(lopsided, TIER_BRACKET_MATCHES)
            == score_bracket(balanced, TIER_BRACKET_MATCHES) == 0)


def test_tier_balance_exempts_a_bracket_with_one_quarter_per_half():
    """A 2-match bracket yields quarters 0/1 only, so each half IS one quarter."""
    register_players([(i, f'C{i}') for i in range(1, 5)])
    matches = {1: [tiered(1, 1, 2), tiered(2, 2, 2)], 2: [tiered(3, 3, 2), tiered(4, 4, 2)]}
    assert check_placement_balance_quarters(matches, 2) == []


@pytest.mark.parametrize('top_count, number_of_matches, expected', [
    (8, 4, 4),   # consolation of 8 groups x 3, top two advance: only thirds
    (10, 8, 2),  # 10 thirds + 6 fourths in 16 slots
    (4, 8, 0),
    (8, 8, 0),
])
def test_forced_first_vs_first(top_count, number_of_matches, expected):
    assert forced_first_vs_first(top_count, number_of_matches) == expected


def test_split_first_vs_first_keeps_the_counts():
    assert split_first_vs_first(['a', 'b', 'c'], 2) == (['c'], ['a', 'b'])
    assert split_first_vs_first(['a'], 3) == ([], ['a'])
    assert split_first_vs_first(['a', 'b'], 0) == (['a', 'b'], [])


def test_single_tier_bracket_has_no_hard_first_vs_first():
    """All participants share one placement, so every pairing is forced."""
    matches = three_tier_matches([(3, 3), (3, 3), (3, 3), (3, 3)])
    assert len(check_no_first_vs_first(matches)) == 4
    assert score_bracket_tiers(matches, 4, DEFAULT_WEIGHTS)[0] == 0


def test_only_first_vs_first_above_the_forced_count_is_hard():
    """5 top players in 4 matches force one pairing; the second one is avoidable."""
    matches = three_tier_matches([(3, 3), (3, 3), (3, 4), (4, 4)])
    assert score_bracket_tiers(matches, 4, DEFAULT_WEIGHTS)[0] == DEFAULT_WEIGHTS['first_vs_first']
    # A partial state passes the real top count; 6 tops would force both.
    assert score_bracket_tiers(matches, 4, DEFAULT_WEIGHTS, top_count=6)[0] == 0


def test_round_two_first_vs_first_forced_by_byes():
    """Four bye-advancing tops in two round-two matches cannot avoid each other."""
    matches = three_tier_matches([(1, 'BYE'), (1, 'BYE'), (1, 'BYE'), (1, 'BYE')])
    round_two = check_round_two_matchups(matches, bounds=(1, 3))
    assert round_two['first_vs_first'] == []
    assert len(round_two['first_vs_first_forced']) == 2
    assert score_round_two(matches, bounds=(1, 3)) == 0


def test_quarter_separation_flags_fourth_in_wrong_half_of_small_bracket():
    """2 matches = one quarter per half: the half must come from the quarter, not q // 2.

    The old checker computed the half as ``quarter // 2``, which puts both quarters
    of a 2-match bracket in half 0, so a 4th opposite its winner went unflagged.
    """
    matches = {1: [tiered(1, 1, 1), tiered(2, 2, 2)], 2: [tiered(3, 1, 4), tiered(4, 2, 1)]}
    assert (1, "position 4th not in same half as 1st") in check_quarter_group_separation(matches, 2)
    assert quarter_misfits(matches, BracketGeometry(2), 1) == [(1, 3, 1, [0])]


def test_quarter_separation_pair_and_fourth_in_full_bracket():
    matches = group_layout_matches({
        1: [(1, 1), (2, 3)],   # q0: winner 1, 3rd of group 2
        3: [(1, 4)],           # q1: 4th of group 1 -- same half, other quarter: fine
        5: [(1, 2)],           # q2: 2nd of group 1
        6: [(1, 3)],           # q2: 3rd of group 1 -- same quarter as the 2nd
        7: [(2, 1)],           # q3: winner of group 2
        8: [(2, 4)],           # q3: 4th of group 2 -- same quarter as its winner
    })
    assert sorted(check_quarter_group_separation(matches, len(matches))) == [
        (1, "positions 2nd/3rd in same quarter"),
        (2, "position 4th in same quarter as 1st"),
    ]


def test_quarter_separation_leaves_a_wrong_half_alone_to_the_half_check():
    """A 2nd alone in its winner's half is a half violation, not a quarter one."""
    matches = group_layout_matches({1: [(1, 1)], 3: [(1, 2)], 5: [(1, 3)]})
    assert check_quarter_group_separation(matches, len(matches)) == []
    assert check_half_group_separation(matches, len(matches))
