"""Module to handle drawing of single-elimination brackets with country conflict avoidance."""
import math
import random
import logging
import itertools
import configparser
from typing import List
from models.draw_data import DrawDataRow
from models.draw_data import seeding_by_start_numbers
from models.player import players_by_start_number
from models.snapshot import Snapshot
from checks.bracket_checker import (
    score_bracket,
    score_bracket_tiers,
    check_half_group_separation,
    check_quarter_group_separation,
    check_no_first_vs_first,
    check_top_easy_first_round,
    check_no_bottom_vs_bottom,
    check_country_conflicts_first_round,
    check_country_balance_halves,
    check_country_balance_quarters,
    check_bye_balance_halves,
    check_bye_seeding_order,
    check_base_conflicts_first_round,
    check_placement_balance_quarters,
    check_round_two_matchups,
    forced_first_vs_first,
    split_first_vs_first,
    score_round_two,
    validate_bracket_weights,
    DEFAULT_BRACKET_WEIGHTS,
    ROUND_TWO_DEFAULT_WEIGHTS,
)
from misc.config import config
import copy


# Rank 4 of the Phase-1 penalty ladder (see placement_penalty): a placement tier
# must not be lopsided between the two quarters of ONE half.  Deliberately NOT a
# config key -- the ladder ranks are a strict-ordering proof (feasibility >
# explicit distribution rules > quality tiebreakers), not a matter of taste, and
# a value above 5000 would silently outrank the feasibility terms and push
# placeable layouts onto the quarter_capacity_degrade path.  It sits 2x below
# BYE_HALF_BALANCE_WEIGHT (byes are both a rule and a feasibility input, tier
# spread is quality only) and an order of magnitude above the score_bracket values
# seen during Phase 1/1b (measured ceiling 250 on a 33-player/64-slot draw).
TIER_QUARTER_BALANCE_WEIGHT = 2500

# Rank 3 of the same ladder: "Freilose ... gleichmaessig auf die Haelften
# verteilen".  Same value the per-step form used, but charged ONCE on the finished
# assignment (see assignment_quality_cost) instead of accumulated per placement.
#
# The per-step form was unsound as an objective.  It charged a marginal excess on
# the RUNNING PREFIX, and its justification only ever proved the sufficient
# direction -- a final split with a gap >= 2 does charge at least one unit whatever
# the order.  The converse fails: a perfectly legal final split is also charged
# whenever the iteration happens to visit one half twice in a row.  On the S M2
# main draw (33 players / 64 slots) the three leftover group winners enter Phase
# 1's last batch with the byes at 4/4, so every assignment ends 6/5 -- clean -- yet
# the orders h0,h1,* and h1,h0,* scored 0 while h0,h0,h1 scored 5000, on nothing
# but participant order.  That phantom 5000 outranked country_half (20) by 250x and
# was the sole reason two Slovenian group winners shared a half: the country-clean
# assignment needed both of its first two placements in the upper half.
BYE_HALF_BALANCE_WEIGHT = 5000

# winner_country_lookahead enumerates 2^k half choices for the k group winners
# still to be placed; 12 keeps one enumeration at a few thousand leaves.
WINNER_LOOKAHEAD_MAX_PENDING = 12


def _max_matching(items, allowed):
    """Maximum bipartite matching (Kuhn's algorithm): items -> slots.

    *items* is an ordered list of keys, *allowed* maps each key to its set of
    candidate slots.  Returns {slot: item}; a perfect matching exists for the
    whole list iff len(result) == len(items).  Candidate slots are visited in
    sorted order so the result is deterministic under the shared seeded RNG.
    """
    match = {}

    def _augment(item, seen):
        for slot in sorted(allowed[item]):
            if slot in seen:
                continue
            seen.add(slot)
            if slot not in match or _augment(match[slot], seen):
                match[slot] = item
                return True
        return False

    for item in items:
        _augment(item, set())
    return match


# The rules a finished bracket must not break ("darf eigentlich nicht verletzt
# werden").  Every other key of get_bracket_violations is a quality goal.
HARD_BRACKET_RULES = ("half_group_separation", "quarter_group_separation", "first_vs_first")
# Pairings the rules would forbid but the bracket's shape makes unavoidable (more
# top placements than matches, see forced_first_vs_first).  Shown, never counted.
FORCED_BRACKET_RULES = ("first_vs_first_forced", "round2_first_vs_first_forced")


def _describe_hard_violation(rule, violation):
    """One readable line for a HARD_BRACKET_RULES violation tuple."""
    if rule in ("first_vs_first", *FORCED_BRACKET_RULES):
        match_idx, a, b = violation

        def who(p):
            return f"#{p.start_number_a} (group {p.group_no}, pos {p.group_pos})"
        return f"match {match_idx}: {who(a)} vs {who(b)}"
    group_no, text = violation
    return f"group {group_no}: {text}"


def bracket_quality(snapshots):
    """Summarise a finished draw_bracket result for the operator.

    Every return path of draw_bracket appends a snapshot of exactly the state it
    returns as its LAST snapshot, so the final violations are read from there
    instead of being re-checked.  Returns
    {"degraded": bool, "hard": {rule: [description]}, "forced": {rule: [description]},
    "bye_order": [description], "soft_count": int}; "hard" and "forced" only carry
    rules that actually have entries, one readable line each.  "forced" pairings
    are unavoidable and so count neither as hard nor as soft violations.

    "degraded" means the draw took the quarter_capacity_degrade path AND its fill
    did not repair it: a hard violation is left, or byes were handed out of
    seeding order ("bye_order") to get rid of one.  A fill that ends clean is a
    regular bracket.
    """
    violations = (snapshots[-1].violations or {}) if snapshots else {}
    final_matches = (snapshots[-1].initial_groups or {}) if snapshots else {}
    hard = {
        rule: [_describe_hard_violation(rule, v) for v in violations[rule]]
        for rule in HARD_BRACKET_RULES if violations.get(rule)
    }
    forced = {
        rule: [_describe_hard_violation(rule, v) for v in violations[rule]]
        for rule in FORCED_BRACKET_RULES if violations.get(rule)
    }
    soft_count = sum(
        len(value) for key, value in violations.items()
        if key not in HARD_BRACKET_RULES and key not in FORCED_BRACKET_RULES and isinstance(value, list)
    )
    group_positions = [
        p.group_pos for participants in final_matches.values() for p in participants
        if p not in (None, "BYE") and p.group_pos is not None
    ]
    bye_order = [
        f"pos {group_pos}: #{without_bye.start_number_a} (seeding {without_bye.seeding}) has no bye, "
        f"#{with_bye.start_number_a} (seeding {with_bye.seeding}) has one"
        for group_pos, without_bye, with_bye in (
            check_bye_seeding_order(final_matches, min(group_positions)) if group_positions else []
        )
    ]
    degraded = any(s.action == "quarter_capacity_degrade" for s in snapshots) and bool(hard or bye_order)
    return {"degraded": degraded, "hard": hard, "forced": forced, "bye_order": bye_order, "soft_count": soft_count}


def draw_bracket(class_subset: list[DrawDataRow]):
    """
    Build a single-elimination bracket from seeded participants.
    class_subset: players advancing from groups
    """

    def bye_hierarchy(num_slots: int) -> List[List[int]]:
        """Return hierarchical subdivisions for seeded slot placement."""
        if num_slots < 2 or (num_slots & (num_slots - 1)) != 0:
            raise ValueError("num_slots must be a power of two >= 2")

        levels = int(math.log2(num_slots))
        groups: List[List[int]] = [[1], [num_slots]]

        for level in range(1, levels):
            block = num_slots // (2 ** level)
            group: List[int] = []
            for idx in range(1, 2 ** level):
                if idx % 2 == 1:
                    boundary = idx * block
                    group.append(boundary)
                    group.append(boundary + 1)
            groups.append(group)

        return groups

    for entry in class_subset:
        key = str(entry.start_number_a)
        if entry.start_number_b is not None:
            alternate_key = f"{entry.start_number_b}/{entry.start_number_a}"
            key = f"{entry.start_number_a}/{entry.start_number_b}"
            if key in seeding_by_start_numbers:
                entry.seeding = seeding_by_start_numbers[key]
            elif alternate_key in seeding_by_start_numbers:
                entry.seeding = seeding_by_start_numbers[alternate_key]
            else:
                raise KeyError(f"Seeding key not found for participant: {key} or {alternate_key}")
        else:
            entry.seeding = seeding_by_start_numbers[key]

    class_subset.sort(key=lambda p: (p.group_pos, -p.seeding))

    num_participants = len(class_subset)
    bracket_size = 1 << (num_participants - 1).bit_length()
    number_of_matches = bracket_size // 2
    byes = bracket_size - num_participants
    logging.debug("Bracket size: %s, participants: %s, byes: %s", bracket_size, num_participants, byes)

    # Quarter geometry: at most 4 quarters, at least 2; each half contains
    # quarters_per_half quarters.  For small brackets (2 first-round matches)
    # there are only 2 quarters (one per half, quarters_per_half = 1).
    num_quarters = min(4, max(2, number_of_matches))
    quarters_per_half = max(1, num_quarters // 2)

    def slot_to_match(slot: int):
        return ((slot + 1) // 2, 0 if slot % 2 == 1 else 1)

    def slot_half(slot: int) -> int:
        match_idx, _ = slot_to_match(slot)
        return 0 if match_idx <= (number_of_matches // 2) else 1

    def slot_quarter(slot: int) -> int:
        match_idx, _ = slot_to_match(slot)
        matches_per_quarter = max(1, number_of_matches // 4)
        return min(3, (match_idx - 1) // matches_per_quarter)

    def opponent_slot(slot: int) -> int:
        return slot + 1 if slot % 2 == 1 else slot - 1

    def empty_slot_state():
        return {slot: None for slot in range(1, bracket_size + 1)}

    def slots_to_matches(slot_state):
        matches = {index: [] for index in range(1, number_of_matches + 1)}
        for slot in range(1, bracket_size + 1):
            value = slot_state[slot]
            if value is None:
                continue
            match_idx, side = slot_to_match(slot)
            while len(matches[match_idx]) < side:
                matches[match_idx].append(None)
            if len(matches[match_idx]) == side:
                matches[match_idx].append(value)
            else:
                matches[match_idx][side] = value
        return matches

    def get_bracket_violations(current_matches):
        # The round-two entries are spread as FLAT keys rather than one nested
        # dict: both viewers hide an empty violation list, and the HTML exporter
        # decides that with `Array.isArray(v) ? v.length : true` -- a dict would
        # always render, even when there is nothing to report.
        round_two = check_round_two_matchups(current_matches, bounds=bracket_bounds)
        # More winners than matches force some winner-vs-winner pairings; those
        # are reported separately so only the avoidable ones count as hard.
        first_vs_first, first_vs_first_forced = split_first_vs_first(
            check_no_first_vs_first(current_matches),
            forced_first_vs_first(bracket_top_count, number_of_matches),
        )
        return {
            "quarter_group_separation": check_quarter_group_separation(current_matches, number_of_matches),
            "half_group_separation": check_half_group_separation(current_matches, number_of_matches, bounds=bracket_bounds),
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
            "round2_first_vs_first": round_two["first_vs_first"],
            "round2_first_vs_first_forced": round_two["first_vs_first_forced"],
            "round2_top_easy_opponent": round_two["top_easy_opponent"],
            "round2_bottom_vs_bottom": round_two["bottom_vs_bottom"],
            "round2_country_first": round_two["country_first"],
            "base_conflicts": check_base_conflicts_first_round(current_matches),
        }

    max_attempts = 2000
    try:
        max_attempts = config.getint("bracket_draw", "max_attempts", fallback=max_attempts)
    except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
        pass

    # Evaluation budget for the joint per-batch assignment in Phase 1/1b.  A batch
    # is solved exactly when its assignment count P(pool, batch) fits the budget,
    # otherwise a hill-climb seeded with the player-by-player result runs for that
    # many iterations.  Raising it buys optimality on large batches at the cost of
    # draw runtime.
    joint_batch_max_evaluations = 5000
    try:
        joint_batch_max_evaluations = config.getint(
            "bracket_draw", "joint_batch_max_evaluations", fallback=joint_batch_max_evaluations
        )
    except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
        pass

    # max_draw_phase controls how many phases to execute (1-5; default=5=all).
    # Set to 1 in config to stop after the top-group-pos seeded placement only.
    max_draw_phase = 5
    try:
        max_draw_phase = config.getint("bracket_draw", "max_draw_phase", fallback=max_draw_phase)
    except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
        pass

    # Uses the shared global `random` module (seeded once from
    # config[settings].random_seed by misc.config.initialize_config), the same
    # RNG stream draw/group_drawer.py uses, so a single config seed
    # deterministically drives the whole pipeline instead of each bracket_draw
    # call restarting its own Random() from the same seed.

    # weights for bracket_checker.score_bracket (lower score = better bracket)
    bracket_weights = dict(DEFAULT_BRACKET_WEIGHTS)
    for weight_key, config_key in (
        ("quarter_split", "quarter_split_weight"),
        ("half_split", "half_split_weight"),
        ("first_vs_first", "first_vs_first_weight"),
        ("top_easy_opponent", "top_easy_opponent_weight"),
        ("bottom_vs_bottom", "bottom_vs_bottom_weight"),
        ("country_first", "country_first_weight"),
        ("country_half", "country_half_weight"),
        ("country_quarter", "country_quarter_weight"),
        ("base_first", "base_first_weight"),
    ):
        try:
            bracket_weights[weight_key] = config.getint("bracket_draw", config_key, fallback=bracket_weights[weight_key])
        except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
            pass

    # weights for bracket_checker.score_round_two (round-two matchup quality)
    round_two_weights = dict(ROUND_TWO_DEFAULT_WEIGHTS)
    for weight_key in round_two_weights:
        try:
            round_two_weights[weight_key] = config.getint(
                "bracket_draw", f"{weight_key}_weight", fallback=round_two_weights[weight_key]
            )
        except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
            pass
    for problem in validate_bracket_weights(bracket_weights, round_two_weights):
        logging.warning("bracket_draw weights: %s", problem)

    top_group_pos = min(p.group_pos for p in class_subset if p.group_pos is not None)
    top_participants = [p for p in class_subset if p.group_pos == top_group_pos]
    # Ground-truth tier range, taken from the INPUT rather than from a bracket
    # state.  Every tier-guarded checker derives (top, bottom) from the matches it
    # is handed, which is right for a finished bracket but wrong for the partial
    # states this drawer scores: during Phase 1 only the winners are placed, so a
    # derived range reads (top, top) and the three-tier guard switches the
    # round-two rules off exactly where they are needed.
    bracket_bounds = (
        top_group_pos,
        max(p.group_pos for p in class_subset if p.group_pos is not None),
    )
    # How many participants each placement tier will end up holding, so a partial
    # state can tell a finished tier from one still being filled.
    tier_totals: dict = {}
    for _p in class_subset:
        if _p.group_pos is not None:
            tier_totals[_p.group_pos] = tier_totals.get(_p.group_pos, 0) + 1
    # Taken from the input for the same reason as bracket_bounds: first-vs-first is
    # only charged above what forced_first_vs_first says the bracket cannot avoid,
    # and a Phase 1 state still missing some winners would under-count it.
    bracket_top_count = tier_totals.get(top_group_pos, 0)

    # Per-group opposite/same-half loads, used to weight each group winner by how
    # much it actually loads its OWN half.  A winner forces its 2nd/3rd (delta 1/2)
    # into the opposite half and its 4th (delta 3) into the same half; balancing
    # raw winner counts wrongly assumes every group demands the same 2 opposite
    # slots, which breaks for uneven groups (e.g. a consolation group missing its
    # 3rd).  See top_reverse_weight below.
    #
    # A non-winner bye recipient counts TWICE: its BYE sits opposite it, so it
    # takes two slots of the half its group anchor sends it to.  Who gets a bye
    # is fixed by seeding before anything is placed, so this is known up front --
    # counting it as one slot let Phase 1 put 8 winners into one half of the S M1
    # consolation draw (15 groups of 4th/5th/6th, 8 byes for the 5th places),
    # leaving the other half short of room and the draw on the degrade path.
    bye_recipients = class_subset[:byes]
    bye_recipient_ids = {id(p) for p in bye_recipients}
    group_opp_load: dict = {}
    group_same_load: dict = {}
    for _p in class_subset:
        _g = getattr(_p, "group_no", None)
        if _g is None or _p.group_pos is None:
            continue
        _delta = _p.group_pos - top_group_pos
        _slots = 2 if id(_p) in bye_recipient_ids else 1
        if _delta in (1, 2):
            group_opp_load[_g] = group_opp_load.get(_g, 0) + _slots
        elif _delta == 3:
            group_same_load[_g] = group_same_load.get(_g, 0) + _slots

    def top_reverse_weight(group_no):
        """Net load a group's winner places on its OWN half: opposite demand minus
        same-half demand minus the winner's own slot, the byes of its non-winners
        included (see above).  A full group without such byes (2nd + 3rd in the
        opposite half) yields 1 — so this collapses to the plain winner count for
        symmetric brackets — while a group missing its 3rd yields 0."""
        if group_no is None:
            return 1
        return group_opp_load.get(group_no, 0) - group_same_load.get(group_no, 0) - 1
    slot_state = empty_slot_state()
    locked_slots = set()
    hierarchy_groups = bye_hierarchy(bracket_size)
    # group_top_quarter maps group_no -> quarter (0-3) where that group's top-pos player landed.
    # group_top_half is kept in sync as quarter // 2 for backward-compat with half-level checks.
    group_top_quarter = {}
    group_top_half = {}

    def _update_group_top(group_no, slot):
        """Record the quarter (and derived half) for a group's top-placed participant."""
        q = slot_quarter(slot)
        group_top_quarter[group_no] = q
        group_top_half[group_no] = q // quarters_per_half

    def required_half_for_participant_with_map(participant, top_half_map):
        group_no = getattr(participant, "group_no", None)
        group_pos = getattr(participant, "group_pos", None)
        if group_no is None or group_pos is None:
            return None
        if group_no not in top_half_map:
            return None
        delta = group_pos - top_group_pos
        anchor_half = top_half_map[group_no]
        if delta in (1, 2):
            return 1 - anchor_half
        if delta == 3:
            return anchor_half
        return None

    def required_half_for_participant(participant):
        return required_half_for_participant_with_map(participant, group_top_half)

    def raise_with_failure_snapshot(action, failure_details, participants=None):
        current_matches = slots_to_matches(slot_state)
        violations = get_bracket_violations(current_matches)
        violations["failure"] = failure_details
        snapshot = Snapshot(
            action,
            sorted(locked_slots),
            None,
            participants,
            violations,
            score_bracket(current_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
            initial_groups=copy.deepcopy(current_matches),
        )
        snapshots.append(snapshot)
        error = ValueError(failure_details.get("message", "Bracket slotting failed."))
        error.snapshots = snapshots
        error.failure_snapshot = snapshot
        raise error

    snapshots = []
    initial_matches = slots_to_matches(slot_state)
    snapshots.append(
        Snapshot(
            "seed_start",
            None,
            None,
            None,
            get_bracket_violations(initial_matches),
            score_bracket(initial_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
            initial_groups=copy.deepcopy(initial_matches),
        )
    )

    # ---------------------------------------------------------------------------
    # Helper: collect the country identifier(s) for a bracket participant.
    # ---------------------------------------------------------------------------
    def _participant_countries(participant):
        countries = []
        try:
            countries.append(players_by_start_number[participant.start_number_a].country)
        except (KeyError, AttributeError):
            pass
        try:
            if getattr(participant, "start_number_b", None) is not None:
                countries.append(players_by_start_number[participant.start_number_b].country)
        except (KeyError, AttributeError):
            pass
        return countries

    # ---------------------------------------------------------------------------
    # assign_quarter_buckets
    # Compute the hard quarter assignment (0-3) for every non-top-group-pos
    # participant using the group_top_quarter map built during Phase 1.
    # ---------------------------------------------------------------------------
    remaining_bye_ids = {id(p) for p in bye_recipients if p.group_pos != top_group_pos}

    def assign_quarter_buckets(non_top_participants):
        """Return dict mapping id(participant) → required quarter (0-3).

        Capacity is tracked dynamically: after every commit the remaining slot
        count for the chosen quarter is decremented.  Bye recipients (those in
        *remaining_bye_ids*) consume two slots (player + adjacent BYE).

        Selection criterion for delta=1 (2nd-place) players when both options
        are valid: primary = most remaining quarter capacity, secondary =
        fewest same-country players already committed to that quarter.  This
        prevents all players from piling into the same quarter when country
        counts are tied (the most common case early in assignment).
        """
        # Prime the country-count table with already-placed (seeded) participants.
        quarter_country_counts: dict = {q: {} for q in range(4)}
        for slot_idx, p in slot_state.items():
            if p is None or p == "BYE":
                continue
            q = slot_quarter(slot_idx)
            for country in _participant_countries(p):
                quarter_country_counts[q][country] = quarter_country_counts[q].get(country, 0) + 1

        # quarter_remaining tracks how many free slots each quarter still has.
        # Initialise from total slots, then subtract already-locked slots.
        quarter_remaining: dict = {
            q: sum(1 for s in range(1, bracket_size + 1) if slot_quarter(s) == q)
            for q in range(4)
        }
        for s in locked_slots:
            quarter_remaining[slot_quarter(s)] -= 1

        required_quarter_map: dict = {}
        # Tracks which opposite-half quarter each group already used for its
        # delta=1 player so the delta=2 player goes to the other one.
        group_opposite_half_used: dict = {}

        # Seed it from what Phase 1/1b already committed.  A group's delta=1 may
        # have received a bye and been placed back in Phase 1b, in which case it
        # is NOT in non_top_participants and this map would start empty — leaving
        # the residual delta=2 to be chosen on capacity alone and land in the very
        # quarter its runner-up already occupies.  That is a violation of a rule
        # that "darf eigentlich nicht verletzt werden" (open_questions.md), and it
        # fires for every group of that shape: a 12-group / 36-player / 64-slot
        # layout produced 8 of them.  Mirrors _required_quarters_for's
        # group_opposite_quarter_used, which enforces the same thing inside 1b.
        for placed_slot, placed in slot_state.items():
            if placed is None or placed == "BYE":
                continue
            placed_group = getattr(placed, "group_no", None)
            if placed_group is None or placed.group_pos is None:
                continue
            if placed.group_pos - top_group_pos in (1, 2):
                group_opposite_half_used.setdefault(placed_group, slot_quarter(placed_slot))

        delta3_players, delta1_players, delta2_players, unconstrained_players = [], [], [], []

        for p in non_top_participants:
            group_no = getattr(p, "group_no", None)
            if group_no is None or group_no not in group_top_quarter:
                unconstrained_players.append(p)
                continue
            delta = p.group_pos - top_group_pos
            if delta == 3:
                delta3_players.append(p)
            elif delta == 1:
                delta1_players.append(p)
            elif delta == 2:
                delta2_players.append(p)
            else:
                unconstrained_players.append(p)

        def _slots_for(p):
            return 2 if id(p) in remaining_bye_ids else 1

        def _commit(p, q):
            required_quarter_map[id(p)] = q
            quarter_remaining[q] -= _slots_for(p)
            for country in _participant_countries(p):
                quarter_country_counts[q][country] = quarter_country_counts[q].get(country, 0) + 1

        def _country_cost(p, q):
            return sum(quarter_country_counts[q].get(c, 0) for c in _participant_countries(p))

        def _best_quarter(p, candidates):
            """Pick the quarter from *candidates* with the most remaining capacity;
            use country-conflict count as tiebreaker.

            A same-tier count was tried as an intermediate tiebreaker, to spread
            the placement tiers over the quarters the way Phase 1/1b now does.
            It does not work here: capacity almost always decides before any
            tiebreaker is reached, so across the real input the tier imbalance was
            unchanged (12 units either way) while country conflicts rose (36 -> 38
            first-round, 18 -> 21 quarter spread).  See check_placement_balance_quarters
            for what this phase consequently still leaves on the table.
            """
            return min(candidates, key=lambda q: (-quarter_remaining[q], _country_cost(p, q)))

        # delta=3 (4th place): other quarter of the SAME half as pos-1.
        for p in delta3_players:
            top_q = group_top_quarter[p.group_no]
            top_h = top_q // quarters_per_half
            same_half_qs = [top_h * quarters_per_half + i for i in range(quarters_per_half)]
            other_qs = [q for q in same_half_qs if q != top_q]
            if other_qs:
                _commit(p, _best_quarter(p, other_qs))
            else:
                # Only one quarter in this half (small bracket) — treat as unconstrained.
                unconstrained_players.append(p)

        def _place_delta1(p):
            top_q = group_top_quarter[p.group_no]
            top_h = top_q // quarters_per_half
            opp_h = 1 - top_h
            opp_qs = [opp_h * quarters_per_half + i for i in range(quarters_per_half)]
            chosen_q = _best_quarter(p, opp_qs)
            group_opposite_half_used[p.group_no] = chosen_q
            _commit(p, chosen_q)

        # A full group's delta=1 and delta=2 occupy the two DIFFERENT opposite-half
        # quarters (one each), so their placement is effectively forced.  A "solo"
        # delta=1 — a short group with no delta=2 sibling, e.g. a consolation group
        # missing its 3rd — has a real choice, so defer it until AFTER the forced
        # delta=2 players are committed.  Placed greedily up front, a solo delta=1
        # can steal the quarter a full group's delta=2 is forced into, overflowing
        # it and needlessly triggering the quarter-capacity degrade.
        groups_with_delta2 = {p.group_no for p in delta2_players}
        paired_delta1 = [p for p in delta1_players if p.group_no in groups_with_delta2]
        solo_delta1 = [p for p in delta1_players if p.group_no not in groups_with_delta2]

        # delta=1 (paired): pick the OPPOSITE-half quarter with the most remaining
        # capacity; break ties by fewest same-country conflicts.
        for p in paired_delta1:
            _place_delta1(p)

        # delta=2 (3rd place): MUST use the OTHER opposite-half quarter so that
        # 2nd and 3rd from the same group land in different quarters.
        for p in delta2_players:
            top_q = group_top_quarter[p.group_no]
            top_h = top_q // quarters_per_half
            opp_h = 1 - top_h
            opp_qs = [opp_h * quarters_per_half + i for i in range(quarters_per_half)]
            if p.group_no in group_opposite_half_used:
                already = group_opposite_half_used[p.group_no]
                other = [q for q in opp_qs if q != already]
                chosen_q = other[0] if other else opp_qs[0]
            else:
                # No delta=1 sibling yet; pick by capacity then country.
                chosen_q = _best_quarter(p, opp_qs)
                group_opposite_half_used[p.group_no] = chosen_q
            _commit(p, chosen_q)

        # delta=1 (solo): short groups whose delta=1 has no delta=2 sibling — placed
        # last, into whatever opposite-half capacity the forced players left free.
        for p in solo_delta1:
            _place_delta1(p)

        # Unconstrained players: group by group_no, assign each group to the
        # quarter with the most remaining capacity.
        unc_by_group: dict = {}
        _none_ctr = 0
        for p in unconstrained_players:
            gno = getattr(p, "group_no", None)
            if gno is None:
                _none_ctr += 1
                key = f"_none_{_none_ctr}"
            else:
                key = gno
            unc_by_group.setdefault(key, []).append(p)

        for group_members in unc_by_group.values():
            n = sum(_slots_for(p) for p in group_members)
            viable = [q for q in range(4) if quarter_remaining[q] >= n]
            chosen_q = max(viable if viable else range(4), key=lambda q: quarter_remaining[q])
            for p in group_members:
                _commit(p, chosen_q)

        return required_quarter_map

    # ---------------------------------------------------------------------------
    # rebalance_bottom_tier_quarters
    # Post-pass over the Phase-2 assignment so every quarter holding a non-bye
    # group winner also holds a bottom-tier player to pair it with.
    # ---------------------------------------------------------------------------
    def rebalance_bottom_tier_quarters(required_quarter, residual_players):
        """Repair the per-quarter bottom-tier supply that check_top_easy_first_round needs.

        A group winner earned a BYE or a lowest-placed opponent, and that outranks
        the country distribution (open_questions.md 29.07).  Scoring alone cannot
        deliver it: the phase-5 Monte Carlo only shuffles WITHIN a quarter, so a
        non-bye winner can only be paired with a bottom-tier player that Phase 2
        already assigned to its quarter — and assign_quarter_buckets decides that
        blind to this rule, breaking the very first capacity tie on quarter index.
        For the live 10-group/32-slot layout that deterministically splits the
        3rd places 2/3 across the two quarters that need 3 and 2, stranding one
        winner in each half.

        Exchanging the quarters of a group's delta=1/delta=2 pair is exactly
        capacity-neutral (each quarter still receives one of the two), and both
        stay in the opposite half in different quarters — so the half separation
        and the 2nd/3rd different-quarter rule are untouched and only the
        deliberately lower-weighted country spread can shift.  That makes it safe
        to repair the allocation AFTER capacity has been settled, which a tie-break
        inside _best_quarter could not do: it would only steer the first delta=1 of
        each half (capacity forces the rest), and ranking it above capacity would
        risk the far more expensive quarter_capacity_degrade path.

        Deterministic and consumes no RNG.  Known limitation: only delta=1/delta=2
        pairs can be swapped, because only those two share a half and so can trade
        quarters without moving anyone across halves.  A 4-tier bracket's bottom
        tier is delta=3, which lives in the anchor's OWN half, so there swapping
        would break the half separation outright — that case bails out below and
        falls back to scoring alone.
        """
        positions = [p.group_pos for p in class_subset if p.group_pos is not None]
        if not positions:
            return
        bottom_pos = max(positions)
        bottom_delta = bottom_pos - top_group_pos
        # delta < 2: fewer than three tiers, the rule is exempt (see the checker).
        # delta > 2: the bottom tier sits in the anchor's own half, so no swap here
        # is half-preserving; leave it to the score.
        if bottom_delta != 2:
            return

        # Non-bye winners whose opponent slot is still free — one bottom-tier
        # player is owed to each of them, in their own quarter.
        demand = {q: 0 for q in range(4)}
        for slot in range(1, bracket_size + 1):
            participant = slot_state[slot]
            if participant is None or participant == "BYE":
                continue
            if participant.group_pos != top_group_pos:
                continue
            if slot_state[opponent_slot(slot)] is None:
                demand[slot_quarter(slot)] += 1

        players_by_identity = {id(p): p for p in residual_players}

        def unmet_demand():
            supply = {q: 0 for q in range(4)}
            for participant_id, quarter in required_quarter.items():
                participant = players_by_identity.get(participant_id)
                if participant is not None and participant.group_pos == bottom_pos:
                    supply[quarter] += 1
            return sum(max(0, demand[q] - supply[q]) for q in range(4))

        # Swap candidates: a bottom-tier player and a delta 1/2 sibling of the same
        # group that currently sit in different quarters.
        members_by_group: dict = {}
        for p in residual_players:
            group_no = getattr(p, "group_no", None)
            if group_no is not None:
                members_by_group.setdefault(group_no, []).append(p)

        swap_candidates = []
        for members in members_by_group.values():
            bottom_members = [p for p in members if p.group_pos == bottom_pos]
            other_members = [
                p for p in members
                if p.group_pos != bottom_pos and p.group_pos - top_group_pos in (1, 2)
            ]
            for low in bottom_members:
                for high in other_members:
                    if required_quarter.get(id(low)) != required_quarter.get(id(high)):
                        swap_candidates.append((low, high))

        # Greedy first-improving swaps; bounded by the candidate count.
        for _ in range(len(swap_candidates)):
            base_cost = unmet_demand()
            if base_cost == 0:
                return
            for low, high in swap_candidates:
                low_q, high_q = required_quarter[id(low)], required_quarter[id(high)]
                required_quarter[id(low)], required_quarter[id(high)] = high_q, low_q
                if unmet_demand() < base_cost:
                    break
                required_quarter[id(low)], required_quarter[id(high)] = low_q, high_q
            else:
                return  # no single swap improves any more

    # ---------------------------------------------------------------------------
    # Per-step placement penalty, evaluated against an EXPLICIT trial state so a
    # whole batch of participants can be scored as one joint assignment.
    #
    # Primary objective: keep (tops + byes) balanced across quarters/halves, plus
    # the byes on their own balanced across the halves.
    # This joint balance is what determines whether the remaining non-bye player
    # quarter assignment will be feasible later: each quarter must keep enough
    # free slots for the players whose group top landed in the OPPOSITE half.
    # Concentrating tops+byes in one quarter shrinks its free slots and can make
    # the later assignment impossible.  Bracket score is only a tiebreaker.
    # ---------------------------------------------------------------------------
    def placement_penalty(participant, slot, trial_state, trial_locked, trial_tops, needs_bye):
        # Combined (tops + byes) per quarter in the trial state.
        tops_in_q_now = {q: sum(1 for gq in trial_tops.values() if gq == q) for q in range(num_quarters)}
        combined_in_q = {
            q: (tops_in_q_now[q] +
                sum(1 for s in trial_locked if trial_state[s] == "BYE" and slot_quarter(s) == q))
            for q in range(num_quarters)
        }
        min_combined = min(combined_in_q.values())

        q = slot_quarter(slot)
        future = combined_in_q[q] + 1 + (1 if needs_bye else 0)
        # Allow up to 1 above the current minimum without penalty.
        combined_excess = max(0, future - min_combined - 1)

        # The half balance (half_load_cost) and the byes' own balance across the
        # halves ("Freilose ... gleichmaessig auf die Haelften verteilen",
        # assignment_quality_cost) are both charged on the FINISHED assignment, not
        # here: accumulated as per-step marginals they charged legal layouts for
        # the order they happened to be built in.  See BYE_HALF_BALANCE_WEIGHT.
        #
        # Ladder, highest first:
        #   half_load_cost      x 100000  net half load           (feasibility)
        #   combined_excess     x  10000  quarter tops+byes       (feasibility)
        #   bye_half     (5000)           byes even over halves
        #   tier_quarter (2500)           tiers even within a half
        #                                 -- both in assignment_quality_cost
        #   score_bracket + score_round_two          quality tiebreakers
        # score_bracket peaks at 250 across a full 33-player/64-slot draw's Phase
        # 1/1b calls (the few-thousand values only occur on a finished, degraded
        # bracket, which no phase-1 candidate ever is).  So neither distribution
        # rule can be bought off with a country/matchup tiebreak, and neither can
        # override a feasibility constraint or push a placeable layout onto the
        # quarter_capacity_degrade path.
        return combined_excess * 10000

    # Net load of each group winner on its own half once placed: its reverse
    # weight, minus one for its own BYE.  Non-winner byes are already inside the
    # reverse weight (see group_opp_load), so they add nothing here.
    top_net_load = {
        id(p): top_reverse_weight(getattr(p, "group_no", None)) - (1 if id(p) in bye_recipient_ids else 0)
        for p in top_participants
    }

    def half_load_cost(trial_tops):
        """Rank 1 of the ladder: the net half load, on a finished batch.

        A group winner forces its 2nd/3rd (delta 1/2) into the OPPOSITE half and
        its 4th (delta 3) into the SAME half, so the two halves only both fill up
        when the winners' net loads (top_net_load) cancel out.  Balancing raw
        winner counts would treat a 3-2 and a 2-3 split as equal even when only one
        is fillable, and would over-count a winner from an uneven group.

        Charged only for the imbalance the winners still to be placed can no
        longer make up (their loads summed), so a batch is never pushed into a
        half by a gap a later batch closes anyway -- that would decide halves on
        participant order and cost the country balance of the group winners.
        """
        net = {0: 0, 1: 0}
        pending = 0
        for p in top_participants:
            gq = trial_tops.get(getattr(p, "group_no", None))
            if gq is None:
                pending += abs(top_net_load[id(p)])
            else:
                net[gq // quarters_per_half] += top_net_load[id(p)]
        return max(0, abs(net[0] - net[1]) - pending - 1) * 100000

    # ---------------------------------------------------------------------------
    # Ranks 3 and 4 of the ladder, plus the round-two tiebreaker.  All three are
    # functions of a FINISHED assignment rather than per-step marginals, so unlike
    # the two feasibility terms above they are evaluated once on the completed
    # trial state instead of being accumulated placement by placement.
    #
    # The two feasibility terms have to stay per-step: they gate whether the REST
    # of the draw can still be filled, so they must be charged as the capacity is
    # consumed.  These three only grade the result, and measuring the result
    # directly is both exact and cheaper -- accumulating a marginal is at best a
    # lower bound on it, and for bye_half_excess it was not even that (a legal
    # final split could be charged for the order it was built in, which is what
    # BYE_HALF_BALANCE_WEIGHT documents).
    # ---------------------------------------------------------------------------
    def assignment_quality_cost(trial_matches):
        """Bye-half + tier-quarter balance + round-two quality for a finished state."""
        # Only charge for a tier every member of which is already on the board.
        # A partially placed tier's counts are a moving target: in a 33-player /
        # 64-slot draw the 3rd places arrive as 9 bye recipients here and 2
        # residual players in Phase 2, so a "repair" of the 9 is chasing a number
        # Phase 2 is about to change -- and Phase 1c would happily pay a real
        # round-two violation for it.  Round two needs no such guard: it is
        # already fully determined (see score_round_two).
        tier_units = sum(
            v[-1] for v in check_placement_balance_quarters(trial_matches, number_of_matches)
            if sum(v[1]) == tier_totals.get(v[0], 0)
        )
        # No "fully placed" guard for the byes: unlike a tier, every bye is written
        # the moment its recipient is committed (opponent_slot), so a partial state
        # holds a prefix of the byes and never a number a later phase revises.
        bye_half_units = sum(
            v[-1] for v in check_bye_balance_halves(trial_matches, number_of_matches)
        )
        return (
            bye_half_units * BYE_HALF_BALANCE_WEIGHT
            + tier_units * TIER_QUARTER_BALANCE_WEIGHT
            + score_round_two(trial_matches, weights=round_two_weights, bounds=bracket_bounds)
        )

    # ---------------------------------------------------------------------------
    # Country lookahead for the group winners.
    #
    # Phase 1 places the winners one hierarchy level at a time, and half_load_cost
    # can leave a later level no choice: on 11 groups x 3 (33 players, 64 slots)
    # the two groups whose 3rd gets no bye must share the half that takes 6
    # winners.  An earlier level that already put the other winner of one of
    # those groups' countries in that half has then made the country pile-up
    # unavoidable.  So each candidate assignment is also charged for the best
    # winner country split still REACHABLE: the pending winners enumerated over
    # the halves their own level still has room in, keeping the final net half
    # load balanced.  Enumeration is exponential in the pending winners, so it
    # only runs once at most WINNER_LOOKAHEAD_MAX_PENDING are left; the levels
    # before that are too wide open for a single pile-up to be forced anyway.
    # ---------------------------------------------------------------------------
    top_sorted = sorted(top_participants, key=lambda p: -p.seeding)
    winner_level_slots = {}
    _start = 0
    for _hierarchy_group in hierarchy_groups:
        for _p in top_sorted[_start:_start + len(_hierarchy_group)]:
            winner_level_slots[id(_p)] = _hierarchy_group
        _start += len(_hierarchy_group)
    winner_countries = {id(p): _participant_countries(p) for p in top_participants}
    # Same slack as check_country_balance_halves: a team carries two countries.
    winner_country_slack = 2 if any(
        getattr(p, "start_number_b", None) is not None for p in top_participants
    ) else 1
    winner_lookahead_cache: dict = {}

    def winner_country_lookahead(trial_state, trial_tops):
        """country_half cost of the best winner country split still reachable."""
        placed, pending = [], []
        for p in top_sorted:
            gq = trial_tops.get(getattr(p, "group_no", None))
            (pending if gq is None else placed).append((p, None if gq is None else gq // quarters_per_half))
        if not pending or len(pending) > WINNER_LOOKAHEAD_MAX_PENDING:
            return 0
        cache_key = frozenset((id(p), h) for p, h in placed)
        if cache_key in winner_lookahead_cache:
            return winner_lookahead_cache[cache_key]

        counts = {}
        net = [0, 0]
        for p, h in placed:
            net[h] += top_net_load[id(p)]
            for country in winner_countries[id(p)]:
                counts.setdefault(country, [0, 0])[h] += 1
        # Room per (level, half) for the pending winners.
        room = {}
        for p, _ in pending:
            level = winner_level_slots.get(id(p), ())
            if id(level) in room:
                continue
            needs_bye = id(p) in bye_recipient_ids
            level_room = [0, 0]
            for s in level:
                if trial_state[s] is None and not (needs_bye and trial_state[opponent_slot(s)] is not None):
                    level_room[slot_half(s)] += 1
            room[id(level)] = level_room

        best = None

        def search(index):
            nonlocal best
            if index == len(pending):
                if abs(net[0] - net[1]) > 1:
                    return
                excess = sum(max(0, abs(c0 - c1) - winner_country_slack) for c0, c1 in counts.values())
                if best is None or excess < best:
                    best = excess
                return
            if best == 0:
                return
            p = pending[index][0]
            level_room = room[id(winner_level_slots.get(id(p), ()))]
            for h in (0, 1):
                if level_room[h] == 0:
                    continue
                level_room[h] -= 1
                net[h] += top_net_load[id(p)]
                for country in winner_countries[id(p)]:
                    counts.setdefault(country, [0, 0])[h] += 1
                search(index + 1)
                for country in winner_countries[id(p)]:
                    counts[country][h] -= 1
                net[h] -= top_net_load[id(p)]
                level_room[h] += 1

        search(0)
        cost = (best or 0) * bracket_weights["country_half"]
        winner_lookahead_cache[cache_key] = cost
        return cost

    def _apply_placement(participant, slot, trial_state, trial_locked, trial_tops, needs_bye):
        """Commit one placement onto a trial state (mirrors the real commit)."""
        trial_state[slot] = participant
        trial_locked.add(slot)
        # Only top-group-pos players anchor their group's quarter/half.
        if participant.group_pos == top_group_pos and getattr(participant, "group_no", None) is not None:
            trial_tops[participant.group_no] = slot_quarter(slot)
        if needs_bye:
            bye_slot = opponent_slot(slot)
            trial_state[bye_slot] = "BYE"
            trial_locked.add(bye_slot)

    def evaluate_assignment(participants, slots):
        """Total cost of assigning *participants* (in order) to *slots*.

        Simulates the sequential commit, summing the same per-step penalties the
        single-slot placer used, then scores the finished batch ONCE.  Because a
        sequential greedy result is itself one of the assignments in this search
        space and scores identically here, the joint search can only match or
        beat the old player-by-player behaviour.

        Returns the cost, or None when the assignment is infeasible (slot taken,
        or bye-adjacency blocked by an earlier player of the same batch).
        """
        trial_state = dict(slot_state)
        trial_locked = set(locked_slots)
        trial_tops = dict(group_top_quarter)
        total = 0
        for participant, slot in zip(participants, slots):
            needs_bye = id(participant) in bye_recipient_ids
            if trial_state[slot] is not None:
                return None
            if needs_bye and trial_state[opponent_slot(slot)] is not None:
                return None
            total += placement_penalty(participant, slot, trial_state, trial_locked, trial_tops, needs_bye)
            _apply_placement(participant, slot, trial_state, trial_locked, trial_tops, needs_bye)
        trial_matches = slots_to_matches(trial_state)
        total += half_load_cost(trial_tops) + winner_country_lookahead(trial_state, trial_tops)
        total += score_bracket(trial_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)
        total += assignment_quality_cost(trial_matches)
        return total

    def greedy_assignment(participants, pool, allowed_slots):
        """Player-by-player assignment — the pre-joint behaviour, kept as the
        starting point for the hill-climb on batches too large to enumerate."""
        trial_state = dict(slot_state)
        trial_locked = set(locked_slots)
        trial_tops = dict(group_top_quarter)
        chosen = []
        for participant in participants:
            needs_bye = id(participant) in bye_recipient_ids
            allowed = allowed_slots[id(participant)] if allowed_slots is not None else None
            best = None
            for slot in pool:
                if slot in chosen or (allowed is not None and slot not in allowed):
                    continue
                if trial_state[slot] is not None:
                    continue
                if needs_bye and trial_state[opponent_slot(slot)] is not None:
                    continue
                step_state = dict(trial_state)
                step_locked = set(trial_locked)
                step_tops = dict(trial_tops)
                cost = placement_penalty(participant, slot, trial_state, trial_locked, trial_tops, needs_bye)
                _apply_placement(participant, slot, step_state, step_locked, step_tops, needs_bye)
                step_matches = slots_to_matches(step_state)
                cost += half_load_cost(step_tops) + winner_country_lookahead(step_state, step_tops)
                cost += score_bracket(step_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)
                cost += assignment_quality_cost(step_matches)
                if best is None or cost < best[0]:
                    best = (cost, slot)
            if best is None:
                return None
            slot = best[1]
            chosen.append(slot)
            _apply_placement(participant, slot, trial_state, trial_locked, trial_tops, needs_bye)
        return chosen

    def matching_seed(participants, pool, allowed_slots):
        """Feasibility-only assignment, used when greedy_assignment strands a player.

        greedy_assignment picks each slot by cost, so an early low-cost choice can
        leave a later participant with nothing even though the batch is solvable.
        Ignoring cost entirely and solving the pure bipartite matching gives a
        starting point for the hill-climb in exactly those cases.  Returns the slot
        list aligned with *participants*, or None when no perfect matching exists.
        """
        candidates = {}
        for participant in participants:
            needs_bye = id(participant) in bye_recipient_ids
            allowed = allowed_slots[id(participant)] if allowed_slots is not None else None
            candidates[id(participant)] = {
                slot for slot in pool
                if (allowed is None or slot in allowed)
                and slot_state[slot] is None
                and not (needs_bye and slot_state[opponent_slot(slot)] is not None)
            }
        ids = [id(p) for p in participants]
        matched = _max_matching(ids, candidates)
        if len(matched) < len(ids):
            return None
        slot_for = {item: slot for slot, item in matched.items()}
        return [slot_for[i] for i in ids]

    # ---------------------------------------------------------------------------
    # Joint placer for a whole batch of participants.
    #
    # Every participant of a seeding batch is assigned in ONE optimisation rather
    # than one at a time, so an early player's locally-best slot can no longer
    # force a worse assignment on the rest of its batch.
    #
    # *slot_pool_tiers* is an ordered list of candidate slot lists; the first tier
    # that admits a feasible assignment for the whole batch is used (later tiers
    # are fallbacks).  *allowed_slots* optionally restricts individual
    # participants (used by Phase 1b, where each player is bound to the quarters
    # its group's anchor allows).
    #
    # Returns the list of chosen slots (aligned with *participants*), or None
    # when no tier admitted a feasible assignment.
    # ---------------------------------------------------------------------------
    def place_batch(participants, slot_pool_tiers, action_name="top_seed_assign", allowed_slots=None):
        if not participants:
            return []
        k = len(participants)

        best_slots = None
        for tier in slot_pool_tiers:
            pool = []
            for slot in tier:
                if slot not in pool and slot_state[slot] is None:
                    pool.append(slot)
            if len(pool) < k:
                continue

            best_cost = None
            candidates = []
            if math.perm(len(pool), k) <= joint_batch_max_evaluations:
                # Small enough to solve exactly.
                for slots in itertools.permutations(pool, k):
                    if allowed_slots is not None and any(
                        s not in allowed_slots[id(p)] for p, s in zip(participants, slots)
                    ):
                        continue
                    cost = evaluate_assignment(participants, list(slots))
                    if cost is None:
                        continue
                    if best_cost is None or cost < best_cost:
                        best_cost, candidates = cost, [list(slots)]
                    elif cost == best_cost:
                        candidates.append(list(slots))
            else:
                # Too large to enumerate: start from the player-by-player result
                # and improve it with random swaps/moves within the budget.
                seed = greedy_assignment(participants, pool, allowed_slots)
                if seed is None:
                    seed = matching_seed(participants, pool, allowed_slots)
                if seed is not None:
                    best_cost = evaluate_assignment(participants, seed)
                if best_cost is not None:
                    current = seed
                    for _ in range(joint_batch_max_evaluations):
                        trial = list(current)
                        spare = [s for s in pool if s not in trial]
                        if k >= 2 and (not spare or random.random() < 0.5):
                            i, j = random.sample(range(k), 2)
                            trial[i], trial[j] = trial[j], trial[i]
                        elif spare:
                            trial[random.randrange(k)] = random.choice(spare)
                        else:
                            continue
                        if allowed_slots is not None and any(
                            s not in allowed_slots[id(p)] for p, s in zip(participants, trial)
                        ):
                            continue
                        cost = evaluate_assignment(participants, trial)
                        if cost is not None and cost < best_cost:
                            best_cost, current = cost, trial
                    candidates = [current]

            if candidates:
                random.shuffle(candidates)
                best_slots = candidates[0]
                break

        if best_slots is None:
            return None

        # Replay the winning assignment on the real state, snapshotting per
        # participant so the interactive viewer keeps its step granularity.
        for participant, slot in zip(participants, best_slots):
            needs_bye = id(participant) in bye_recipient_ids
            slot_state[slot] = participant
            locked_slots.add(slot)
            if participant.group_pos == top_group_pos and getattr(participant, "group_no", None) is not None:
                _update_group_top(participant.group_no, slot)
            if needs_bye:
                bye_slot = opponent_slot(slot)
                slot_state[bye_slot] = "BYE"
                locked_slots.add(bye_slot)

            step_matches = slots_to_matches(slot_state)
            snapshots.append(
                Snapshot(
                    action_name,
                    [slot],
                    None,
                    [participant],
                    get_bracket_violations(step_matches),
                    score_bracket(step_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                    initial_groups=copy.deepcopy(step_matches),
                )
            )
        return best_slots

    def place_bye_greedy(participant, slot_pool_tiers, action_name="top_seed_assign"):
        """Single-participant convenience wrapper around place_batch."""
        chosen = place_batch([participant], slot_pool_tiers, action_name)
        return chosen[0] if chosen else None

    # ---------------------------------------------------------------------------
    # Phase 1: Place top-group-pos participants in strict seeding batches.
    #
    # Batch 0 → hierarchy_groups[0] = [slot 1]        — completely deterministic
    # Batch 1 → hierarchy_groups[1] = [last slot]     — completely deterministic
    # Batch 2 → hierarchy_groups[2] (2 slots)         — greedy best-score + shuffle
    # Batch k → hierarchy_groups[k] (2^(k-1) slots)   — greedy best-score + shuffle
    # ---------------------------------------------------------------------------
    n_top = len(top_sorted)

    batch_start = 0
    for batch_idx, hierarchy_group in enumerate(hierarchy_groups):
        if batch_start >= n_top:
            break
        batch_end = batch_start + len(hierarchy_group)
        batch_players = top_sorted[batch_start:min(batch_end, n_top)]

        if len(hierarchy_group) == 1 and len(batch_players) == 1:
            # Completely deterministic: single slot, single player — no scoring.
            participant = batch_players[0]
            slot = hierarchy_group[0]
            needs_bye = id(participant) in bye_recipient_ids

            if slot_state[slot] is not None or (needs_bye and slot_state[opponent_slot(slot)] is not None):
                raise_with_failure_snapshot(
                    "seed_slot_failure",
                    {
                        "message": f"Required seeded slot {slot} is already occupied.",
                        "type": "seed_slot_failure",
                        "phase": "deterministic_batch",
                        "batch_idx": batch_idx,
                        "slot": slot,
                        "locked_slots": sorted(locked_slots),
                    },
                    [participant],
                )

            slot_state[slot] = participant
            locked_slots.add(slot)
            if getattr(participant, "group_no", None) is not None:
                _update_group_top(participant.group_no, slot)
            bye_slot_det = None
            if needs_bye:
                bye_slot_det = opponent_slot(slot)
                slot_state[bye_slot_det] = "BYE"
                locked_slots.add(bye_slot_det)

            trial_matches_det = slots_to_matches(slot_state)
            snapshots.append(
                Snapshot(
                    "top_seed_assign",
                    [slot],
                    None,
                    [participant],
                    get_bracket_violations(trial_matches_det),
                    score_bracket(trial_matches_det, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                    initial_groups=copy.deepcopy(trial_matches_det),
                )
            )
        else:
            # Joint balanced placement of the WHOLE batch within its hierarchy
            # group, falling back to any remaining free slot.
            any_slot_tier = list(range(1, bracket_size + 1))
            if place_batch(batch_players, [hierarchy_group, any_slot_tier]) is None:
                raise_with_failure_snapshot(
                    "seed_slot_failure",
                    {
                        "message": (
                            f"No slot assignment available for top-seeded batch {batch_idx} "
                            f"(participants {[p.start_number_a for p in batch_players]})."
                        ),
                        "type": "seed_slot_failure",
                        "phase": "joint_batch",
                        "batch_idx": batch_idx,
                        "locked_slots": sorted(locked_slots),
                    },
                    batch_players,
                )

        batch_start = batch_end

    post_top_matches = slots_to_matches(slot_state)
    snapshots.append(
        Snapshot(
            "top_seed_complete",
            sorted(locked_slots),
            None,
            list(top_sorted),
            get_bracket_violations(post_top_matches),
            score_bracket(post_top_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
            initial_groups=copy.deepcopy(post_top_matches),
        )
    )

    if max_draw_phase <= 1:
        # Return the partial bracket (only top-group-pos players placed).
        return post_top_matches, snapshots

    # ---------------------------------------------------------------------------
    # Phase 1b: When byes outnumber the top-group-pos players, keep distributing
    # the remaining byes (pos-5, pos-6, ... in seeding order) with the same
    # balanced placer, each restricted to the quarter/half required by where its
    # group's top landed.  This spreads the byes evenly so the leftover non-bye
    # players still fit; only afterwards does Phase 2 run.  In the common case
    # (byes <= number of tops) there are no non-top byes and this is a no-op.
    # ---------------------------------------------------------------------------
    non_top_bye_recipients = [p for p in bye_recipients if p.group_pos != top_group_pos]
    # Records the opposite-half quarter a group already used, so its 2nd/3rd land
    # in different quarters (mirrors assign_quarter_buckets).
    group_opposite_quarter_used: dict = {}

    def _required_quarters_for(participant):
        """Allowed quarters for a non-top bye, per the half/quarter separation rules."""
        group_no = getattr(participant, "group_no", None)
        if group_no is None or group_no not in group_top_quarter:
            return list(range(num_quarters))
        top_q = group_top_quarter[group_no]
        top_h = top_q // quarters_per_half
        delta = participant.group_pos - top_group_pos
        if delta in (1, 2):
            opp_h = 1 - top_h
            opp_qs = [opp_h * quarters_per_half + i for i in range(quarters_per_half)]
            used = group_opposite_quarter_used.get(group_no)
            if delta == 2 and used is not None:
                other = [q for q in opp_qs if q != used]
                return other if other else opp_qs
            return opp_qs
        if delta == 3:
            same_qs = [top_h * quarters_per_half + i for i in range(quarters_per_half)]
            other = [q for q in same_qs if q != top_q]
            return other if other else same_qs
        return list(range(num_quarters))

    any_slot_tier = list(range(1, bracket_size + 1))

    # Continue the seeded-slot hierarchy where Phase 1 stopped.  Phase 1 breaks out
    # of its batch loop as soon as the group winners run out, leaving the rest of
    # the partially-filled batch — and every later batch — untouched; any hierarchy
    # slot still free is therefore the strongest slot left, and the next-highest
    # bye recipients should fill it before dropping to a weaker one.  Each batch is
    # assigned jointly, exactly like Phase 1, with every participant masked to the
    # quarters its group's anchor allows, so the separation rules still bind.
    remaining_byes = list(non_top_bye_recipients)
    for hierarchy_group in hierarchy_groups:
        while remaining_byes:
            # Every phase-1b participant is a bye recipient and occupies the whole
            # match, so a slot whose partner is already taken cannot host one.
            free_in_group = [
                s for s in hierarchy_group
                if slot_state[s] is None and slot_state[opponent_slot(s)] is None
            ]
            if not free_in_group:
                break

            # A group's 2nd constrains its 3rd via group_opposite_quarter_used, which
            # only holds while they are assigned in separate batches — so never take
            # two participants of the same group into one chunk.
            chunk = []
            chunk_groups = set()
            allowed_slots = {}
            for participant in remaining_byes:
                if len(chunk) >= len(free_in_group):
                    break
                group_no = getattr(participant, "group_no", None)
                if group_no is not None and group_no in chunk_groups:
                    continue
                allowed_qs = _required_quarters_for(participant)
                allowed = {s for s in free_in_group if slot_quarter(s) in allowed_qs}
                if not allowed:
                    continue
                # Simply taking the top N by seeding can be jointly unassignable even
                # when every member has a candidate slot on its own (e.g. four players
                # needing half 0 while only three half-0 slots are free).  Admit a
                # player only while a perfect matching survives; a rejected one stays
                # in remaining_byes for the next round of this level, or the next
                # level.  Matchable subsets form a transversal matroid, so this
                # seeding-ordered greedy yields the highest-seeded maximum-size chunk.
                trial_allowed = dict(allowed_slots)
                trial_allowed[id(participant)] = allowed
                trial_ids = [id(p) for p in chunk] + [id(participant)]
                if len(_max_matching(trial_ids, trial_allowed)) < len(trial_ids):
                    continue
                chunk.append(participant)
                chunk_groups.add(group_no)
                allowed_slots[id(participant)] = allowed
            if not chunk:
                break

            chosen_slots = None
            while chunk:
                chosen_slots = place_batch(
                    chunk, [free_in_group], action_name="bye_assign", allowed_slots=allowed_slots
                )
                if chosen_slots is not None:
                    break
                # Never abandon a whole hierarchy level over one un-placeable player:
                # drop the lowest-seeded chunk member and retry, so the strong slots
                # still go to as many high seeds as will fit.
                allowed_slots.pop(id(chunk.pop()), None)
            if not chunk:
                break

            for participant, slot in zip(chunk, chosen_slots):
                group_no = getattr(participant, "group_no", None)
                if group_no is not None:
                    group_opposite_quarter_used.setdefault(group_no, slot_quarter(slot))
                remaining_byes.remove(participant)

    for participant in remaining_byes:
        allowed_qs = _required_quarters_for(participant)
        quarter_tier = [s for s in any_slot_tier if slot_quarter(s) in allowed_qs]
        required_half = required_half_for_participant(participant)
        half_tier = (
            [s for s in any_slot_tier if slot_half(s) == required_half]
            if required_half is not None else any_slot_tier
        )
        chosen = place_bye_greedy(
            participant, [quarter_tier, half_tier, any_slot_tier], action_name="bye_assign"
        )
        if chosen is None:
            raise_with_failure_snapshot(
                "bye_slot_failure",
                {
                    "message": "Unable to place bye recipients in their required quarters.",
                    "type": "bye_slot_failure",
                    "phase": "bye_distribution",
                    "top_group_pos": top_group_pos,
                    "locked_slots": sorted(locked_slots),
                    "group_top_quarter": dict(group_top_quarter),
                },
                [participant],
            )
        group_no = getattr(participant, "group_no", None)
        if group_no is not None:
            group_opposite_quarter_used.setdefault(group_no, slot_quarter(chosen))

    # ---------------------------------------------------------------------------
    # Phase 1c: repair pass over everything Phase 1/1b locked in.
    #
    # Both distribution objectives are properties of the FINISHED layout, but
    # Phase 1/1b can only ever optimise one batch at a time: an uneven tier spread
    # emerges ACROSS hierarchy levels (the runners-up of a 64-slot draw are split
    # between two levels, placed by different place_batch calls), and a chunk of
    # ~16 participants into 16 slots is far past joint_batch_max_evaluations, so it
    # falls to a hill-climb seeded by a cost-greedy pass that commits each player
    # before its round-two opposite even exists.  This pass is the only one with a
    # global view of the result.
    #
    # It swaps two NON-TOP bye recipients, which is FEASIBILITY-NEUTRAL by
    # construction and so cannot undo anything Phase 1/1b established: both slots
    # are (player, BYE) matches before and after, so every per-quarter and per-half
    # bye count is unchanged, and a top-placed participant is not a candidate at all
    # -- neither as the mover nor as its partner -- so the group anchors, and with
    # them the tops-per-quarter and net-half-load balances and Phase 2's dependence
    # on group_top_quarter, are invariant here by construction rather than by a
    # boundary check.  Phase 1 decides where the group winners sit; they stay put.
    # That is the same capacity-neutrality argument that makes
    # rebalance_bottom_tier_quarters safe to run after capacity is settled.
    #
    # Deterministic first-improvement, consuming NO randomness: drawing from the
    # shared RNG stream here would shift every downstream random outcome, so any
    # change in a drawn bracket stays attributable to the rules rather than to the
    # pass having run.  Also like rebalance_bottom_tier_quarters.
    # ---------------------------------------------------------------------------
    def repair_bye_placements():
        """Swap or move placed non-top bye recipients while it strictly improves the layout."""
        # Top-placed participants are filtered out HERE rather than skipped per pair
        # inside the sweep: a swap moves both of its participants, so a group winner
        # must not be a partner either, and dropping them up front shrinks the
        # quadratic sweep instead of paying for them on every iteration.
        def bye_recipient_slots():
            return sorted(
                s for s in locked_slots
                if slot_state[s] not in (None, "BYE")
                and slot_state[s].group_pos != top_group_pos
                and slot_state[opponent_slot(s)] == "BYE"
            )

        candidates = bye_recipient_slots()
        if not candidates:
            return

        def state_cost(trial_matches):
            return (
                score_bracket(trial_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)
                + assignment_quality_cost(trial_matches)
            )

        def separation_counts(trial_matches):
            return (
                len(check_half_group_separation(trial_matches, number_of_matches, bounds=bracket_bounds)),
                len(check_quarter_group_separation(trial_matches, number_of_matches)),
            )

        # The residual 2nd/3rd (delta 1/2) that Phase 2 still has to place, by group,
        # and the residual 4ths (delta 3), each tied to its winner's own half.
        residual_by_group = {}
        residual_fourths = []
        for p in class_subset:
            if id(p) in bye_recipient_ids or p.group_no not in group_top_quarter:
                continue
            if p.group_pos - top_group_pos in (1, 2):
                residual_by_group.setdefault(p.group_no, []).append(p)
            elif p.group_pos - top_group_pos == 3:
                residual_fourths.append(p)

        def residual_overflow():
            """Residual players the free slots of their forced quarter cannot hold.

            A group's 2nd and 3rd go to the opposite half, in different quarters.
            So once one of them sits there with a bye, the other is forced into the
            sibling quarter -- and a 2nd with a bye placed without regard for that
            can leave the sibling quarter full (S M1 consolation: free slots 4/6,
            five 6th places forced into the "4" quarter).  A 4th is forced into the
            other quarter of its winner's half.  The moves below change how many
            free slots a quarter has, so they need the 4ths counted too.
            """
            free_in_q = {q: 0 for q in range(num_quarters)}
            placed_quarters = {}
            for s in range(1, bracket_size + 1):
                value = slot_state[s]
                if value is None:
                    free_in_q[slot_quarter(s)] += 1
                elif value != "BYE" and value.group_pos - top_group_pos in (1, 2):
                    placed_quarters.setdefault(value.group_no, set()).add(slot_quarter(s))
            forced = {q: 0 for q in range(num_quarters)}
            for group_no, members in residual_by_group.items():
                opp_h = 1 - group_top_quarter[group_no] // quarters_per_half
                open_quarters = [
                    opp_h * quarters_per_half + i for i in range(quarters_per_half)
                    if opp_h * quarters_per_half + i not in placed_quarters.get(group_no, set())
                ]
                # Only a group with no choice left forces anything.
                if len(open_quarters) == len(members):
                    for q in open_quarters:
                        forced[q] += 1
            for p in residual_fourths:
                top_q = group_top_quarter[p.group_no]
                top_h = top_q // quarters_per_half
                same_qs = [top_h * quarters_per_half + i for i in range(quarters_per_half)]
                allowed = [q for q in same_qs if q != top_q] or same_qs
                if len(allowed) == 1:
                    forced[allowed[0]] += 1
            return sum(max(0, forced[q] - free_in_q[q]) for q in range(num_quarters))

        current_matches = slots_to_matches(slot_state)
        # Lexicographic: residual capacity first -- an overflow sends the whole
        # draw down the quarter_capacity_degrade path -- then the layout cost.
        best_key = (residual_overflow(), state_cost(current_matches))
        # Separations are a HARD gate, not part of the objective: at 2500 a tier
        # unit outweighs both split weights, so a scored gate would let the pass
        # buy a tier repair with a separation -- "darf eigentlich nicht verletzt
        # werden, country und base lieber violaten".  Phase 1/1b can leave one
        # behind, so the bar is "no worse", not "none".
        best_separations = separation_counts(current_matches)

        # Two kinds of step, both feasibility-guarded by residual_overflow and the
        # separation gate:
        #
        # * swap two non-top bye recipients -- every per-quarter bye count stays;
        # * move one non-top bye recipient, with its BYE, into a free match of the
        #   other quarter of its own half -- only while that lowers the overflow.
        #
        # The swap alone cannot repair a bracket without a spare slot.  S M3 main
        # (50 groups x 3, 256 slots, 106 byes) fills every slot, so each quarter
        # must hold precisely the 3rd places its sibling quarter's runners-up force
        # into it; Phase 1/1b balance tops+byes with one unit of slack and could
        # leave free slots 8/10 against 9/9 forced 3rd places.  Swapping two
        # runners-up of that half moves one forced 3rd each way (net zero), so the
        # draw went down the degrade path.  Moving ONE of them closes the gap: its
        # old quarter gains two free slots and one forced 3rd.  A move never leaves
        # its half, so the half separation and the bye-half balance stay put.
        #
        # Best-improvement rather than first-improvement: a sweep costs the same
        # either way, and taking the first improving step settles for whatever
        # trade it stumbles on -- on a 33-player draw that meant paying a real
        # round-two violation for a tier repair that a different pair delivered
        # for free.  Each accepted step strictly lowers the key, so this
        # terminates; the cap only bounds the work on a pathological plateau.
        for _ in range(2 * len(candidates) + number_of_matches):
            candidates = bye_recipient_slots()
            best_step = None
            for index, slot_a in enumerate(candidates):
                for slot_b in candidates[index + 1:]:
                    participant_a, participant_b = slot_state[slot_a], slot_state[slot_b]
                    slot_state[slot_a], slot_state[slot_b] = participant_b, participant_a
                    trial_matches = slots_to_matches(slot_state)
                    trial_key = (residual_overflow(), state_cost(trial_matches))
                    # Separations are the more expensive check, so only pay for it
                    # once a step is actually in the running.
                    if trial_key < best_key and (best_step is None or trial_key < best_step[0]):
                        trial_separations = separation_counts(trial_matches)
                        if all(t <= b for t, b in zip(trial_separations, best_separations)):
                            best_step = (trial_key, trial_separations, "bye_swap", slot_a, slot_b)
                    slot_state[slot_a], slot_state[slot_b] = participant_a, participant_b

            free_matches = [
                m for m in range(1, number_of_matches + 1)
                if slot_state[2 * m - 1] is None and slot_state[2 * m] is None
            ] if best_key[0] > 0 else []
            for slot_from in candidates:
                bye_from = opponent_slot(slot_from)
                quarter_from = slot_quarter(slot_from)
                for match_to in free_matches:
                    # Keep the player on the same side of its match.
                    slot_to = 2 * match_to - 1 if slot_from % 2 == 1 else 2 * match_to
                    quarter_to = slot_quarter(slot_to)
                    if quarter_to == quarter_from or quarter_to // quarters_per_half != quarter_from // quarters_per_half:
                        continue
                    bye_to = opponent_slot(slot_to)
                    participant = slot_state[slot_from]
                    slot_state[slot_from], slot_state[bye_from] = None, None
                    slot_state[slot_to], slot_state[bye_to] = participant, "BYE"
                    # A move shifts the per-quarter bye counts Phase 1/1b balanced,
                    # so it is only worth that when it removes an overflow.
                    trial_overflow = residual_overflow()
                    if trial_overflow < best_key[0]:
                        trial_matches = slots_to_matches(slot_state)
                        trial_key = (trial_overflow, state_cost(trial_matches))
                        if best_step is None or trial_key < best_step[0]:
                            trial_separations = separation_counts(trial_matches)
                            if all(t <= b for t, b in zip(trial_separations, best_separations)):
                                best_step = (trial_key, trial_separations, "bye_move", slot_from, slot_to)
                    slot_state[slot_to], slot_state[bye_to] = None, None
                    slot_state[slot_from], slot_state[bye_from] = participant, "BYE"

            if best_step is None:
                break

            best_key, best_separations, action, slot_a, slot_b = best_step
            if action == "bye_swap":
                participant_a, participant_b = slot_state[slot_a], slot_state[slot_b]
                slot_state[slot_a], slot_state[slot_b] = participant_b, participant_a
                moved = [participant_a, participant_b]
            else:
                bye_a, bye_b = opponent_slot(slot_a), opponent_slot(slot_b)
                moved = [slot_state[slot_a]]
                slot_state[slot_a], slot_state[bye_a] = None, None
                slot_state[slot_b], slot_state[bye_b] = moved[0], "BYE"
                locked_slots.difference_update((slot_a, bye_a))
                locked_slots.update((slot_b, bye_b))
            # No group_top_quarter/_half resync: no top-placed participant moves,
            # so the anchors cannot have moved.
            stepped_matches = slots_to_matches(slot_state)
            snapshots.append(
                Snapshot(
                    action,
                    [slot_a, slot_b],
                    None,
                    moved,
                    get_bracket_violations(stepped_matches),
                    score_bracket(stepped_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                    initial_groups=copy.deepcopy(stepped_matches),
                )
            )

    if non_top_bye_recipients:
        # Gated on Phase 1b having run.  Without it every bye recipient is a group
        # winner, so the candidate set below would come out empty anyway; the gate
        # just skips the work and keeps the low-bye draws untouched.
        repair_bye_placements()

    if non_top_bye_recipients:
        seeded_bye_matches = slots_to_matches(slot_state)
        snapshots.append(
            Snapshot(
                "seeded_byes",
                sorted(locked_slots),
                None,
                list(top_sorted) + list(non_top_bye_recipients),
                get_bracket_violations(seeded_bye_matches),
                score_bracket(seeded_bye_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                initial_groups=copy.deepcopy(seeded_bye_matches),
            )
        )

    # ---------------------------------------------------------------------------
    # Phase 2: Assign quarter buckets to the remaining (non-bye) participants and
    # verify there is enough free space in each quarter for them.  With the byes
    # already balanced above, the residual demand is small.
    # ---------------------------------------------------------------------------
    residual_non_top = [
        p for p in class_subset
        if p.group_pos != top_group_pos and id(p) not in bye_recipient_ids
    ]
    required_quarter = assign_quarter_buckets(residual_non_top)
    # Capacity-neutral repair pass so each quarter can actually serve its non-bye
    # group winners a bottom-tier opponent.  Runs before the capacity check below,
    # which by construction still sees the same per-quarter counts.
    rebalance_bottom_tier_quarters(required_quarter, residual_non_top)

    def _fill_residual_soft(residual_players):
        """Best-effort fill of all free slots when hard quarter buckets overflow.

        The degrade is usually caused upstream: Phase 1/1b left a quarter or half
        without room for a player the separation rules send there (e.g. a quarter
        filled with "player vs BYE" matches, or an 8/6 bye split across the
        halves).  So the fill cannot just shuffle the leftover players -- random
        reshuffles of 30+ free slots never converge, and no placement of the
        leftovers alone can repair a full quarter.

        Instead: start from the best of a few random fills, then hill-climb
        (sideways moves accepted, best state kept) with three move types that
        never touch a group winner, which stays in its seeded slot:

        * swap two first-round matches without a winner -- moves whole
          "player vs BYE" pairs between quarters and halves;
        * move a BYE to another player-vs-player match, only when the new
          recipient has the same group position as the old one, so each tier
          keeps its number of byes;
        * swap two non-winner players, same group position only when exactly
          one of them faces a BYE (same reason).

        The objective is compared as a tuple, most important first: the hard
        tier (separations, first-vs-first); byes in seeding order within a tier
        ("Hoechstes Seeding bekommt zuerst Freilose" -- the two bye-moving moves
        may break it, but only to remove a hard violation); Phase 1/1b/1c's own
        assignment_quality_cost (byes even over the halves, tiers even over the
        quarters of a half, round-two quality), because the moves shift exactly
        what those phases balanced; then score_bracket_tiers' matchup and
        distribution tiers.
        """
        free_slots_all = [s for s in range(1, bracket_size + 1) if slot_state[s] is None]

        def _fill_order(order):
            trial_state = dict(slot_state)
            for slot, participant in zip(free_slots_all, order):
                trial_state[slot] = participant
            return trial_state

        def _is_top(value):
            return value not in (None, "BYE") and value.group_pos == top_group_pos

        def _key(trial_state):
            trial_matches = slots_to_matches(trial_state)
            hard, matchup, distribution = score_bracket_tiers(
                trial_matches, number_of_matches, weights=bracket_weights, bounds=bracket_bounds,
                top_count=bracket_top_count,
            )
            return (
                hard,
                # "Hoechstes Seeding bekommt zuerst Freilose"
                len(check_bye_seeding_order(trial_matches, top_group_pos)),
                assignment_quality_cost(trial_matches),
                matchup,
                distribution,
            )

        start_matches = slots_to_matches(slot_state)
        snapshots.append(
            Snapshot(
                "quarter_capacity_degrade",
                sorted(locked_slots),
                None,
                list(residual_players),
                get_bracket_violations(start_matches),
                score_bracket(start_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                initial_groups=copy.deepcopy(start_matches),
            )
        )

        best_order = list(residual_players)
        random.shuffle(best_order)
        best_key = _key(_fill_order(best_order))
        for _ in range(min(200, max_attempts)):
            trial_order = list(residual_players)
            random.shuffle(trial_order)
            trial_key = _key(_fill_order(trial_order))
            if trial_key < best_key:
                best_key, best_order = trial_key, trial_order

        state = _fill_order(best_order)
        best_state = dict(state)
        current_key = best_key
        winner_free_matches = [
            m for m in range(1, number_of_matches + 1)
            if not _is_top(state[2 * m - 1]) and not _is_top(state[2 * m])
        ]
        player_slots = [s for s in range(1, bracket_size + 1) if state[s] != "BYE" and not _is_top(state[s])]
        # 4x the phase-5 budget: a move costs one scoring pass, which is small next
        # to Phase 1 on the brackets that degrade, and the S M3 draws (150 players,
        # 256 slots) only reach zero hard violations with it.
        search_iterations = 4 * max_attempts
        snapshot_interval = max(1, search_iterations // 10)

        def _random_move():
            """Apply one random move to `state`; return (changed slots, previous
            values) for the undo, or None when the drawn move is not allowed."""
            move = random.random()
            if move < 0.25:
                # Bye relocation.  Recipients are non-winners (the winners' byes
                # stay with their seeded slot).
                bye_slots = [
                    s for s in range(1, bracket_size + 1)
                    if state[s] == "BYE" and not _is_top(state[opponent_slot(s)])
                ]
                if not bye_slots:
                    return None
                bye_slot = random.choice(bye_slots)
                recipient = state[opponent_slot(bye_slot)]
                targets = [
                    s for s in player_slots
                    if s != opponent_slot(bye_slot)
                    and state[opponent_slot(s)] not in (None, "BYE")
                    and state[opponent_slot(s)].group_pos == recipient.group_pos
                ]
                if not targets:
                    return None
                target = random.choice(targets)
                changed = [bye_slot, target]
                previous = [state[s] for s in changed]
                # The player at the target takes the BYE's place opposite the old
                # recipient, and the target slot becomes the BYE.
                state[bye_slot], state[target] = previous[1], "BYE"
            elif move < 0.6 and len(winner_free_matches) >= 2:
                match_a, match_b = random.sample(winner_free_matches, 2)
                changed = [2 * match_a - 1, 2 * match_a, 2 * match_b - 1, 2 * match_b]
                previous = [state[s] for s in changed]
                for s, value in zip(changed, previous[2:] + previous[:2]):
                    state[s] = value
            else:
                slot_a, slot_b = random.sample(player_slots, 2)
                bye_a = state[opponent_slot(slot_a)] == "BYE"
                bye_b = state[opponent_slot(slot_b)] == "BYE"
                if bye_a != bye_b and state[slot_a].group_pos != state[slot_b].group_pos:
                    return None
                changed = [slot_a, slot_b]
                previous = [state[s] for s in changed]
                state[slot_a], state[slot_b] = previous[1], previous[0]
            return changed, previous

        # A hill climb on a lexicographic key plateaus: once the hard tier is
        # stuck, every move that would pass through a worse lower tier is
        # rejected.  After `stall_limit` attempts without a new best, restart
        # from the best state with a few unconditional moves -- but only while
        # hard violations remain, since that is what the fill is for.
        stall_limit = max(100, search_iterations // 80)
        kick_moves = 4
        since_best = 0

        for attempt in range(search_iterations):
            if best_key == (0, 0, 0, 0, 0):
                break
            if since_best >= stall_limit and best_key[0] > 0:
                since_best = 0
                state = dict(best_state)
                player_slots = [s for s in range(1, bracket_size + 1) if state[s] != "BYE" and not _is_top(state[s])]
                for _ in range(kick_moves):
                    if _random_move() is not None:
                        player_slots = [
                            s for s in range(1, bracket_size + 1) if state[s] != "BYE" and not _is_top(state[s])
                        ]
                current_key = _key(state)

            since_best += 1
            applied = _random_move()
            if applied is None:
                continue
            changed, previous = applied

            trial_key = _key(state)
            m_try = slots_to_matches(state)
            if trial_key <= current_key:
                current_key = trial_key
                player_slots = [s for s in range(1, bracket_size + 1) if state[s] != "BYE" and not _is_top(state[s])]
                if trial_key < best_key:
                    since_best = 0
                    best_key, best_state = trial_key, dict(state)
                    snapshots.append(
                        Snapshot(
                            "improvement",
                            [attempt],
                            None,
                            None,
                            get_bracket_violations(m_try),
                            score_bracket(m_try, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                            initial_groups=copy.deepcopy(m_try),
                        )
                    )
                    continue
            else:
                for s, value in zip(changed, previous):
                    state[s] = value
            if attempt % snapshot_interval == 0:
                snapshots.append(
                    Snapshot(
                        "progress",
                        [attempt],
                        None,
                        None,
                        get_bracket_violations(m_try),
                        score_bracket(m_try, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                        initial_groups=copy.deepcopy(m_try),
                    )
                )

        best_matches = slots_to_matches(best_state)
        snapshots.append(
            Snapshot(
                "final",
                None,
                None,
                None,
                get_bracket_violations(best_matches),
                score_bracket(best_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count),
                initial_groups=copy.deepcopy(best_matches),
            )
        )
        return best_matches, snapshots

    free_after_byes = [s for s in range(1, bracket_size + 1) if slot_state[s] is None]
    free_slots_by_quarter_cap = {
        q: [s for s in free_after_byes if slot_quarter(s) == q]
        for q in range(4)
    }
    required_counts_by_quarter: dict = {q: 0 for q in range(4)}
    for p in residual_non_top:
        rq = required_quarter.get(id(p))
        if rq is not None:
            required_counts_by_quarter[rq] += 1

    over_capacity = [
        q for q in range(4)
        if required_counts_by_quarter[q] > len(free_slots_by_quarter_cap[q])
    ]
    if over_capacity:
        # Structurally tight, near-full bracket: the residual non-bye players
        # cannot be packed into their required quarters without overflow (e.g.
        # an odd number of groups each contributing 3 positions into a bracket
        # that is almost entirely byes).  Rather than abort the whole bracket,
        # degrade gracefully — fill every remaining free slot with a Monte Carlo
        # that minimises the bracket score, so half/quarter separation become
        # soft (heavily weighted) goals instead of a hard failure.
        return _fill_residual_soft(residual_non_top)

    # ---------------------------------------------------------------------------
    # Phase 4: Build quarter pools from the remaining (non-bye, non-top) players.
    # ---------------------------------------------------------------------------
    remaining = [
        p for p in class_subset
        if id(p) not in bye_recipient_ids and p.group_pos != top_group_pos
    ]

    free_slots = [s for s in range(1, bracket_size + 1) if slot_state[s] is None]
    free_slots_by_quarter = {
        q: [s for s in free_slots if slot_quarter(s) == q]
        for q in range(4)
    }

    def build_matches_from_quarter_pools(pools):
        """Assign each quarter pool (in slot order) and return a matches dict."""
        trial_state = dict(slot_state)
        for q in range(4):
            for slot, participant in zip(free_slots_by_quarter[q], pools[q]):
                trial_state[slot] = participant
        return slots_to_matches(trial_state)

    final_pool_quarter: dict = {q: [] for q in range(4)}
    for p in remaining:
        rq = required_quarter.get(id(p), 0)
        final_pool_quarter[rq].append(p)

    for q in range(4):
        if len(final_pool_quarter[q]) != len(free_slots_by_quarter[q]):
            raise_with_failure_snapshot(
                "permutation_failure",
                {
                    "message": (
                        f"Quarter {q} pool size {len(final_pool_quarter[q])} "
                        f"does not match slot capacity {len(free_slots_by_quarter[q])}."
                    ),
                    "type": "quarter_pool_size_mismatch",
                    "group_top_quarter": dict(group_top_quarter),
                    "remaining_start_numbers": [p.start_number_a for p in remaining],
                },
                remaining,
            )

    if not remaining:
        first_full_matches = slots_to_matches(dict(slot_state))
        first_full_violations = get_bracket_violations(first_full_matches)
        first_full_score = score_bracket(first_full_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)
        snapshots.append(
            Snapshot(
                "final",
                None,
                None,
                None,
                first_full_violations,
                first_full_score,
                initial_groups=copy.deepcopy(first_full_matches),
            )
        )
        return first_full_matches, snapshots

    # Initial shuffle: each quarter pool shuffled independently.
    current_pools = {q: list(final_pool_quarter[q]) for q in range(4)}
    for q in range(4):
        random.shuffle(current_pools[q])

    first_full_matches = build_matches_from_quarter_pools(current_pools)
    first_full_violations = get_bracket_violations(first_full_matches)
    first_full_score = score_bracket(first_full_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)

    snapshots.append(
        Snapshot(
            "initial_fill",
            None,
            None,
            None,
            first_full_violations,
            first_full_score,
            initial_groups=copy.deepcopy(first_full_matches),
        )
    )

    best_score = first_full_score
    # Compared as score_bracket_tiers tuples, not the summed score: a weighted
    # sum would trade one winner-vs-runner-up for a few same-country pairings.
    best_key = score_bracket_tiers(first_full_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)
    best_matches = copy.deepcopy(first_full_matches)
    best_pools = {q: list(current_pools[q]) for q in range(4)}

    snapshot_interval = max(1, max_attempts // 10)

    # ---------------------------------------------------------------------------
    # Phase 5: Four-phase Monte Carlo — one phase per quarter.
    # Each phase fixes the other three quarters and shuffles the active one.
    # ---------------------------------------------------------------------------
    for active_q in range(4):
        if not final_pool_quarter[active_q]:
            continue  # nothing to optimise in this quarter

        snapshots.append(
            Snapshot(
                f"quarter{active_q}_mc_start",
                None,
                None,
                None,
                get_bracket_violations(best_matches),
                best_score,
                initial_groups=copy.deepcopy(best_matches),
            )
        )

        for attempt in range(max_attempts):
            trial_pool = list(final_pool_quarter[active_q])
            random.shuffle(trial_pool)
            trial_pools = dict(best_pools)
            trial_pools[active_q] = trial_pool
            m_try = build_matches_from_quarter_pools(trial_pools)
            trial_key = score_bracket_tiers(m_try, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)
            score = sum(trial_key)

            if trial_key < best_key:
                best_key = trial_key
                best_score = score
                best_pools = {q: list(trial_pools[q]) for q in range(4)}
                best_matches = copy.deepcopy(m_try)
                violations = get_bracket_violations(m_try)
                snapshots.append(
                    Snapshot(
                        "improvement",
                        [attempt],
                        None,
                        None,
                        violations,
                        score,
                        initial_groups=copy.deepcopy(m_try),
                    )
                )
                if best_score == 0:
                    break
            elif attempt % snapshot_interval == 0:
                violations = get_bracket_violations(m_try)
                snapshots.append(
                    Snapshot(
                        "progress",
                        [attempt],
                        None,
                        None,
                        violations,
                        score,
                        initial_groups=copy.deepcopy(m_try),
                    )
                )

        if best_score == 0:
            break

    final_violations = get_bracket_violations(best_matches)
    final_score = score_bracket(best_matches, number_of_matches, weights=bracket_weights, top_count=bracket_top_count)
    snapshots.append(
        Snapshot(
            "final",
            None,
            None,
            None,
            final_violations,
            final_score,
            initial_groups=copy.deepcopy(best_matches),
        )
    )

    return best_matches, snapshots
