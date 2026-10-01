"""The mutable side of a bracket draw: the slots, the group anchors and the snapshot trail."""

import copy
from dataclasses import dataclass, field

from checks.bracket_checker import (
    check_base_conflicts_first_round,
    check_bye_balance_halves,
    check_country_balance_halves,
    check_country_balance_quarters,
    check_country_conflicts_first_round,
    check_half_group_separation,
    check_no_bottom_vs_bottom,
    check_no_first_vs_first,
    check_placement_balance_halves,
    check_placement_balance_quarters,
    check_quarter_group_separation,
    check_round_two_matchups,
    check_top_easy_first_round,
    forced_first_vs_first,
    score_bracket,
    split_first_vs_first,
)
from draw.bracket.context import BracketContext
from models.snapshot import Snapshot


def opponent_slot(slot: int) -> int:
    return slot + 1 if slot % 2 == 1 else slot - 1


def slots_to_matches(ctx: BracketContext, slot_state):
    """match index -> [side 0, side 1], filled slots only (a match may stay short)."""
    matches = {index: [] for index in range(1, ctx.number_of_matches + 1)}
    for slot in range(1, ctx.bracket_size + 1):
        value = slot_state[slot]
        if value is None:
            continue
        match_idx, side = ctx.geo.slot_to_match(slot)
        while len(matches[match_idx]) < side:
            matches[match_idx].append(None)
        if len(matches[match_idx]) == side:
            matches[match_idx].append(value)
        else:
            matches[match_idx][side] = value
    return matches


def bracket_violations(ctx: BracketContext, current_matches):
    # The round-two entries are spread as FLAT keys rather than one nested
    # dict: both viewers hide an empty violation list, and the HTML exporter
    # decides that with `Array.isArray(v) ? v.length : true` -- a dict would
    # always render, even when there is nothing to report.
    number_of_matches = ctx.number_of_matches
    bounds = ctx.bracket_bounds
    round_two = check_round_two_matchups(current_matches, bounds=bounds)
    # More winners than matches force some winner-vs-winner pairings; those
    # are reported separately so only the avoidable ones count as hard.
    first_vs_first, first_vs_first_forced = split_first_vs_first(
        check_no_first_vs_first(current_matches),
        forced_first_vs_first(ctx.bracket_top_count, number_of_matches),
    )
    return {
        "quarter_group_separation": check_quarter_group_separation(current_matches, number_of_matches, bounds=bounds),
        "half_group_separation": check_half_group_separation(current_matches, number_of_matches, bounds=bounds),
        "first_vs_first": first_vs_first,
        "first_vs_first_forced": first_vs_first_forced,
        "top_easy_opponent": check_top_easy_first_round(current_matches),
        "bottom_vs_bottom": check_no_bottom_vs_bottom(current_matches),
        "country_first": check_country_conflicts_first_round(current_matches),
        "country_balance": check_country_balance_halves(current_matches, number_of_matches),
        "country_balance_quarters": check_country_balance_quarters(current_matches, number_of_matches),
        # Reported only -- deliberately not part of score_bracket, see the note there.
        "bye_balance_halves": check_bye_balance_halves(current_matches, number_of_matches),
        "placement_balance_quarters": check_placement_balance_quarters(current_matches, number_of_matches),
        "placement_balance_halves": check_placement_balance_halves(current_matches, number_of_matches, bounds=bounds),
        "round2_first_vs_first": round_two["first_vs_first"],
        "round2_first_vs_first_forced": round_two["first_vs_first_forced"],
        "round2_top_easy_opponent": round_two["top_easy_opponent"],
        "round2_bottom_vs_bottom": round_two["bottom_vs_bottom"],
        "round2_country_first": round_two["country_first"],
        "base_conflicts": check_base_conflicts_first_round(current_matches),
    }


def bracket_score(ctx: BracketContext, current_matches):
    return score_bracket(
        current_matches, ctx.number_of_matches, weights=ctx.bracket_weights, top_count=ctx.bracket_top_count
    )


@dataclass
class Trial:
    """A scratch copy of the placement, scored without touching the real state.

    *tops* is the group -> anchor quarter map (BracketState.group_top_quarter).
    """

    state: dict
    locked: set
    tops: dict

    def copy(self):
        return Trial(dict(self.state), set(self.locked), dict(self.tops))

    def apply(self, ctx: BracketContext, participant, slot, needs_bye):
        """Commit one placement onto this trial (mirrors BracketState.place)."""
        self.state[slot] = participant
        self.locked.add(slot)
        # Only top-group-pos players anchor their group's quarter/half.
        if participant.group_pos == ctx.top_group_pos and getattr(participant, "group_no", None) is not None:
            self.tops[participant.group_no] = ctx.geo.slot_quarter(slot)
        if needs_bye:
            bye_slot = opponent_slot(slot)
            self.state[bye_slot] = "BYE"
            self.locked.add(bye_slot)


@dataclass
class BracketState:
    ctx: BracketContext = field(repr=False)
    # slot (1..bracket_size) -> participant, "BYE" or None.
    slot_state: dict
    locked_slots: set
    # group_no -> quarter (0-3) where that group's top-pos player landed.
    # group_top_half is kept in sync as its half for the half-level checks.
    group_top_quarter: dict
    group_top_half: dict
    snapshots: list

    @classmethod
    def empty(cls, ctx: BracketContext):
        return cls(ctx, {slot: None for slot in range(1, ctx.bracket_size + 1)}, set(), {}, {}, [])

    def trial(self) -> Trial:
        return Trial(dict(self.slot_state), set(self.locked_slots), dict(self.group_top_quarter))

    def matches(self):
        return slots_to_matches(self.ctx, self.slot_state)

    def place(self, participant, slot, needs_bye):
        """Put *participant* into *slot* (with a BYE opposite if *needs_bye*) and lock it."""
        ctx = self.ctx
        self.slot_state[slot] = participant
        self.locked_slots.add(slot)
        if participant.group_pos == ctx.top_group_pos and getattr(participant, "group_no", None) is not None:
            quarter = ctx.geo.slot_quarter(slot)
            self.group_top_quarter[participant.group_no] = quarter
            self.group_top_half[participant.group_no] = ctx.geo.quarter_half(quarter)
        if needs_bye:
            bye_slot = opponent_slot(slot)
            self.slot_state[bye_slot] = "BYE"
            self.locked_slots.add(bye_slot)

    def record(self, action, groups, participants, matches=None, *, violations=None, violation_score=None):
        """Append a snapshot of *matches* (default: the current state).

        Violations and score default to bracket_violations / bracket_score of it.
        """
        if matches is None:
            matches = self.matches()
        if violations is None:
            violations = bracket_violations(self.ctx, matches)
        if violation_score is None:
            violation_score = bracket_score(self.ctx, matches)
        self.snapshots.append(
            Snapshot(action, groups, None, participants, violations, violation_score, state=copy.deepcopy(matches))
        )

    def fail(self, action, failure_details, participants=None):
        """Record a failure snapshot of the current state and raise.

        The ValueError carries the whole trail as `snapshots` and the failing
        entry as `failure_snapshot`.
        """
        matches = self.matches()
        violations = bracket_violations(self.ctx, matches)
        violations["failure"] = failure_details
        self.record(action, sorted(self.locked_slots), participants, matches, violations=violations)
        error = ValueError(failure_details.get("message", "Bracket slotting failed."))
        error.snapshots = self.snapshots
        error.failure_snapshot = self.snapshots[-1]
        raise error
