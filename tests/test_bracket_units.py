"""Unit tests for the building blocks of draw/bracket, without running a whole draw."""

import pytest

from draw.bracket.context import build_context
from draw.bracket.costs import half_load_cost, placement_penalty, projected_half_balance_units
from draw.bracket.hierarchy import bye_hierarchy, winner_level_slots
from draw.bracket.placement import max_matching
from draw.bracket.quarters import assign_quarter_buckets, over_capacity_quarters
from draw.bracket.rules import allowed_for, required_half
from draw.bracket.state import BracketState, opponent_slot
from tests.bracket_shapes import build_tiered_rows


def by_group_pos(ctx, group_no, group_pos):
    return next(p for p in ctx.participants if p.group_no == group_no and p.group_pos == group_pos)


def test_bye_hierarchy_lists_the_strongest_slots_first():
    assert bye_hierarchy(2) == [[1], [2]]
    assert bye_hierarchy(8) == [[1], [8], [4, 5], [2, 3, 6, 7]]
    assert sorted(s for level in bye_hierarchy(32) for s in level) == list(range(1, 33))


@pytest.mark.parametrize("num_slots", [0, 1, 3, 12])
def test_bye_hierarchy_rejects_non_powers_of_two(num_slots):
    with pytest.raises(ValueError):
        bye_hierarchy(num_slots)


def test_winner_level_slots_fills_the_levels_in_seeding_order():
    levels = bye_hierarchy(8)
    winners = ["w1", "w2", "w3", "w4", "w5"]
    level_of = winner_level_slots(levels, winners)
    assert [level_of[id(w)] for w in winners] == [[1], [8], [4, 5], [4, 5], [2, 3, 6, 7]]
    # The very list objects, so the lookahead can key its room by identity.
    assert level_of[id("w3")] is levels[2]


def test_max_matching_finds_a_perfect_matching_when_one_exists():
    # Greedy in item order would give "a" slot 1 and strand "b".
    assert max_matching(["a", "b"], {"a": {1, 2}, "b": {1}}) == {1: "b", 2: "a"}


def test_max_matching_reports_an_impossible_batch_by_its_size():
    matched = max_matching(["a", "b", "c"], {"a": {1, 2}, "b": {1, 2}, "c": {1}})
    assert len(matched) == 2


def test_build_context_derives_sizes_byes_and_residuals():
    ctx = build_context(build_tiered_rows(5, (1, 2, 3)), half_balance=True)
    assert (ctx.bracket_size, ctx.number_of_matches, ctx.byes) == (16, 8, 1)
    assert ctx.top_group_pos == 1
    assert ctx.bracket_bounds == (1, 3)
    assert ctx.tier_totals == {1: 5, 2: 5, 3: 5}
    # Sorted by (group_pos, -seeding): the strongest group winner gets the bye.
    assert ctx.bye_recipients == [by_group_pos(ctx, 1, 1)]
    assert ctx.non_top_bye_recipients == []
    assert len(ctx.residual_players) == 10
    assert all(p.group_pos in (2, 3) for p in ctx.residual_players)
    # A full group loads its winner's own half by 1; its own bye takes one off.
    assert ctx.top_net_load[id(by_group_pos(ctx, 1, 1))] == 0
    assert ctx.top_net_load[id(by_group_pos(ctx, 2, 1))] == 1


def test_required_half_and_allowed_quarters_follow_the_anchor():
    ctx = build_context(build_tiered_rows(4, (1, 2, 3, 4)), half_balance=True)
    winner, second, third, fourth = (by_group_pos(ctx, 1, pos) for pos in (1, 2, 3, 4))
    top_half = {1: 0}
    assert required_half(ctx, winner, top_half) is None
    assert required_half(ctx, second, top_half) == 1
    assert required_half(ctx, third, top_half) == 1
    assert required_half(ctx, fourth, top_half) == 0
    assert required_half(ctx, second, {}) is None

    tops = {1: 0}
    assert allowed_for(ctx, tops, second) == [2, 3]
    assert allowed_for(ctx, tops, third, sibling_quarter=2) == [3]
    assert allowed_for(ctx, tops, fourth) == [1]
    assert allowed_for(ctx, {}, second) == [0, 1, 2, 3]


def test_place_with_a_bye_locks_both_slots_and_sets_the_anchor():
    ctx = build_context(build_tiered_rows(5, (1, 2, 3)), half_balance=True)
    state = BracketState.empty(ctx)
    winner = by_group_pos(ctx, 3, 1)
    state.place(winner, 11, needs_bye=True)
    assert state.slot_state[11] is winner
    assert state.slot_state[opponent_slot(11)] == "BYE" and opponent_slot(11) == 12
    assert state.locked_slots == {11, 12}
    assert state.group_top_quarter == {3: 2}
    assert state.group_top_half == {3: 1}
    assert state.matches()[6] == [winner, "BYE"]


def test_record_and_fail_append_snapshots():
    ctx = build_context(build_tiered_rows(5, (1, 2, 3)), half_balance=True)
    state = BracketState.empty(ctx)
    state.record("seed_start", None, None)
    with pytest.raises(ValueError, match="boom") as raised:
        state.fail("test_failure", {"message": "boom"})
    assert [s.action for s in state.snapshots] == ["seed_start", "test_failure"]
    assert raised.value.failure_snapshot is state.snapshots[-1]
    assert raised.value.failure_snapshot.violations["failure"] == {"message": "boom"}


def test_placement_penalty_charges_a_crowded_quarter():
    ctx = build_context(build_tiered_rows(5, (1, 2, 3)), half_balance=True)
    state = BracketState.empty(ctx)
    assert placement_penalty(ctx, 1, state.trial(), needs_bye=False) == 0
    state.place(by_group_pos(ctx, 1, 1), 1, needs_bye=True)  # quarter 0: one top, one bye
    state.place(by_group_pos(ctx, 2, 1), 3, needs_bye=False)  # quarter 0: two tops
    # Quarter 0 (slots 1-4) would go from 3 to 4 against an empty quarter: 3 above the allowed 1.
    assert placement_penalty(ctx, 4, state.trial(), needs_bye=False) == 3 * 10000
    assert placement_penalty(ctx, 9, state.trial(), needs_bye=False) == 0


def test_half_load_cost_charges_only_an_imbalance_the_pending_winners_cannot_close():
    ctx = build_context(build_tiered_rows(5, (1, 2, 3)), half_balance=True)
    # Group 1's winner has the bye (net load 0), the other four load 1 each.
    assert half_load_cost(ctx, {1: 2, 2: 0, 3: 1, 4: 2, 5: 3}) == 0
    assert half_load_cost(ctx, {1: 2, 2: 0, 3: 0, 4: 1, 5: 1}) == 3 * 100000
    # Two winners still pending can make up two units of the 4/0 split.
    assert half_load_cost(ctx, {1: 2, 2: 0, 3: 0, 4: 1}) == 0 + max(0, 3 - 1 - 1) * 100000


def test_projected_half_balance_counts_bound_players_in_their_forced_half():
    ctx = build_context(build_tiered_rows(4, (1, 2)), half_balance=True)
    state = BracketState.empty(ctx)
    # All four winners in half 0 (slots 1-4) force all four runners-up into
    # half 1: 4/0 on both tiers, nothing left to even it out.
    for group_no, slot in zip(range(1, 5), (1, 2, 3, 4)):
        state.place(by_group_pos(ctx, group_no, 1), slot, needs_bye=False)
    assert projected_half_balance_units(ctx, state.matches(), state.group_top_quarter) == (0, 3 + 3)


def test_assign_quarter_buckets_sends_runners_up_to_the_opposite_half():
    ctx = build_context(build_tiered_rows(4, (1, 2, 3)), half_balance=True)
    state = BracketState.empty(ctx)
    for group_no, slot in zip(range(1, 5), (1, 16, 8, 9)):
        state.place(
            by_group_pos(ctx, group_no, 1), slot, needs_bye=id(by_group_pos(ctx, group_no, 1)) in ctx.bye_recipient_ids
        )
    required = assign_quarter_buckets(ctx, state, ctx.residual_players)
    for p in ctx.residual_players:
        anchor_half = state.group_top_half[p.group_no]
        assert ctx.geo.quarter_half(required[id(p)]) == 1 - anchor_half
    for group_no in range(1, 5):
        second, third = by_group_pos(ctx, group_no, 2), by_group_pos(ctx, group_no, 3)
        assert required[id(second)] != required[id(third)]
    assert over_capacity_quarters(ctx, state, ctx.residual_players, required) == []
