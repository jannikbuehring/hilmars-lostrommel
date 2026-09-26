"""Tests for models/bracket_geometry.py: the one geometry the drawer, checker and viewer share."""
import pytest

from models.bracket_geometry import BracketGeometry, allowed_quarters

MATCH_COUNTS = [1, 2, 4, 8, 16, 32]


@pytest.mark.parametrize("number_of_matches", MATCH_COUNTS)
def test_slot_and_match_views_agree(number_of_matches):
    geo = BracketGeometry(number_of_matches)
    for slot in range(1, geo.bracket_size + 1):
        match_idx, _side = geo.slot_to_match(slot)
        assert geo.slot_quarter(slot) == geo.match_quarter(match_idx)
        assert geo.slot_half(slot) == geo.match_half(match_idx)
        assert geo.quarter_half(geo.slot_quarter(slot)) == geo.slot_half(slot)
        assert geo.slot_quarter(slot) in range(geo.num_quarters)


@pytest.mark.parametrize("number_of_matches", [n for n in MATCH_COUNTS if n >= 2])
def test_matches_the_formulas_it_replaced(number_of_matches):
    """The drawer's slot_half/slot_quarter and the checker's _match_half/_match_quarter."""
    geo = BracketGeometry(number_of_matches)
    for match_idx in range(1, number_of_matches + 1):
        assert geo.match_half(match_idx) == (0 if match_idx <= number_of_matches // 2 else 1)
        assert geo.match_quarter(match_idx) == min(3, (match_idx - 1) // max(1, number_of_matches // 4))


def test_slot_to_match():
    assert [BracketGeometry.slot_to_match(s) for s in range(1, 5)] == [(1, 0), (1, 1), (2, 0), (2, 1)]


@pytest.mark.parametrize("number_of_matches, num_quarters, quarters_per_half", [
    (1, 2, 1), (2, 2, 1), (4, 4, 2), (32, 4, 2),
])
def test_quarter_counts(number_of_matches, num_quarters, quarters_per_half):
    geo = BracketGeometry(number_of_matches)
    assert geo.num_quarters == num_quarters
    assert geo.quarters_per_half == quarters_per_half
    assert geo.half_quarters(0) + geo.half_quarters(1) == list(range(num_quarters))


FULL = BracketGeometry(8)   # 4 quarters, 2 per half
SMALL = BracketGeometry(2)  # 2 quarters, 1 per half


@pytest.mark.parametrize("geo, delta, anchor, sibling, expected", [
    # 2nd/3rd: the opposite half, away from the sibling.
    (FULL, 1, 0, None, [2, 3]),
    (FULL, 2, 3, None, [0, 1]),
    (FULL, 2, 0, 2, [3]),
    (FULL, 1, 0, 3, [2]),
    (FULL, 1, 0, 1, [2, 3]),     # a sibling in the wrong half does not narrow anything
    (SMALL, 2, 0, 1, [1]),       # one quarter per half: the half rule wins
    # 4th: the winner's half, not the winner's quarter.
    (FULL, 3, 0, None, [1]),
    (FULL, 3, 3, None, [2]),
    (SMALL, 3, 1, None, [1]),    # one quarter per half: stays in the winner's half
    # No constraint.
    (FULL, 0, 0, None, [0, 1, 2, 3]),
    (FULL, 4, 0, None, [0, 1, 2, 3]),
    (FULL, 1, None, None, [0, 1, 2, 3]),
    (FULL, None, 0, None, [0, 1, 2, 3]),
    (SMALL, 1, None, None, [0, 1]),
])
def test_allowed_quarters(geo, delta, anchor, sibling, expected):
    assert allowed_quarters(delta, anchor, geo, sibling) == expected
