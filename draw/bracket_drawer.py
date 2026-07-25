"""Module to handle drawing of single-elimination brackets with country conflict avoidance."""
import math
import random
import logging
import configparser
from typing import List
from models.draw_data import DrawDataRow
from models.draw_data import seeding_by_start_numbers
from models.player import players_by_start_number
from models.snapshot import Snapshot
from checks.bracket_checker import (
    score_bracket,
    check_half_group_separation,
    check_quarter_group_separation,
    check_no_first_vs_first,
    check_country_balance_halves,
    check_base_conflicts_first_round,
)
from misc.config import config
import copy

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
        return {
            "quarter_group_separation": check_quarter_group_separation(current_matches, number_of_matches),
            "half_group_separation": check_half_group_separation(current_matches, number_of_matches),
            "first_vs_first": check_no_first_vs_first(current_matches),
            "country_balance": check_country_balance_halves(current_matches, number_of_matches),
            "base_conflicts": check_base_conflicts_first_round(current_matches),
        }

    max_attempts = 2000
    try:
        max_attempts = config.getint("bracket_draw", "max_attempts", fallback=max_attempts)
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
    bracket_weights = {
        "quarter_split": 200,
        "half_split": 150,
        "first_vs_first": 100,
        "country_half": 10,
        "base_first": 20,
    }
    for weight_key, config_key in (
        ("half_split", "half_split_weight"),
        ("first_vs_first", "first_vs_first_weight"),
        ("country_half", "country_half_weight"),
        ("base_first", "base_first_weight"),
    ):
        try:
            bracket_weights[weight_key] = config.getint("bracket_draw", config_key, fallback=bracket_weights[weight_key])
        except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
            pass

    top_group_pos = min(p.group_pos for p in class_subset if p.group_pos is not None)
    top_participants = [p for p in class_subset if p.group_pos == top_group_pos]
    bye_recipients = class_subset[:byes]
    bye_recipient_ids = {id(p) for p in bye_recipients}
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

    def score_candidate_placement(participant, slot, current_state, needs_bye):
        trial_state = dict(current_state)
        trial_state[slot] = participant
        if needs_bye:
            trial_state[opponent_slot(slot)] = "BYE"
        trial_matches = slots_to_matches(trial_state)
        return score_bracket(trial_matches, number_of_matches, weights=bracket_weights), trial_matches

    def usable_slots_in_group(group, current_state, needs_bye):
        available = []
        for slot in group:
            if current_state[slot] is not None:
                continue
            if needs_bye and current_state[opponent_slot(slot)] is not None:
                continue
            available.append(slot)
        return available

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
            score_bracket(current_matches, number_of_matches, weights=bracket_weights),
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
            score_bracket(initial_matches, number_of_matches, weights=bracket_weights),
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
            use country-conflict count as tiebreaker."""
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

        # delta=1 (2nd place): pick the OPPOSITE-half quarter with the most
        # remaining capacity; break ties by fewest same-country conflicts.
        for p in delta1_players:
            top_q = group_top_quarter[p.group_no]
            top_h = top_q // quarters_per_half
            opp_h = 1 - top_h
            opp_qs = [opp_h * quarters_per_half + i for i in range(quarters_per_half)]
            chosen_q = _best_quarter(p, opp_qs)
            group_opposite_half_used[p.group_no] = chosen_q
            _commit(p, chosen_q)

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
    # Balanced greedy placer for a single bye recipient.
    #
    # Primary objective: keep (tops + byes) balanced across quarters/halves.
    # This joint balance is what determines whether the remaining non-bye player
    # quarter assignment will be feasible later: each quarter must keep enough
    # free slots for the players whose group top landed in the OPPOSITE half.
    # Concentrating tops+byes in one quarter shrinks its free slots and can make
    # the later assignment impossible.  Bracket score is only a tiebreaker.
    #
    # *slot_pool_tiers* is an ordered list of candidate slot lists; the first
    # tier that yields any usable slot is used (later tiers are fallbacks).
    # Returns the chosen slot, or None when no tier had a usable slot.
    # ---------------------------------------------------------------------------
    def place_bye_greedy(participant, slot_pool_tiers, action_name="top_seed_assign"):
        needs_bye = id(participant) in bye_recipient_ids

        available = []
        for tier in slot_pool_tiers:
            usable = usable_slots_in_group(tier, slot_state, needs_bye)
            if usable:
                available = usable
                break
        if not available:
            return None

        # Current combined (tops + byes) per quarter and per half.
        tops_in_q_now = {q: sum(1 for gq in group_top_quarter.values() if gq == q) for q in range(num_quarters)}
        combined_in_q = {
            q: (tops_in_q_now[q] +
                sum(1 for s in locked_slots if slot_state[s] == "BYE" and slot_quarter(s) == q))
            for q in range(num_quarters)
        }
        min_combined = min(combined_in_q.values())
        # Half-tops balance: keeps tops per half as equal as possible — the PRIMARY
        # capacity constraint, since demand on the opposite half equals the tops there.
        half_tops_now = {
            h: sum(tops_in_q_now[h * quarters_per_half + i] for i in range(quarters_per_half))
            for h in range(2)
        }

        def _combined_penalty(s):
            q = slot_quarter(s)
            future = combined_in_q[q] + 1 + (1 if needs_bye else 0)
            # Allow up to 1 above the current minimum without penalty.
            excess = max(0, future - min_combined - 1)
            return excess * 10000

        def _half_tops_penalty(s):
            h = slot_quarter(s) // quarters_per_half
            opp_h = 1 - h
            future_h_tops = half_tops_now[h] + 1
            opp_tops = half_tops_now[opp_h]
            # Penalise if this half would be more than 1 ahead of the opposite half.
            excess = max(0, future_h_tops - opp_tops - 1)
            return excess * 100000

        scored = [
            (sc + _combined_penalty(s) + _half_tops_penalty(s), s, tm)
            for s in available
            for sc, tm in [score_candidate_placement(participant, s, slot_state, needs_bye)]
        ]
        scored.sort(key=lambda x: x[0])
        best_s = scored[0][0]
        best_cands = [x for x in scored if x[0] == best_s]
        random.shuffle(best_cands)
        _, chosen_slot, chosen_matches = best_cands[0]

        slot_state[chosen_slot] = participant
        locked_slots.add(chosen_slot)
        # Only top-group-pos players anchor their group's quarter/half.
        if participant.group_pos == top_group_pos and getattr(participant, "group_no", None) is not None:
            _update_group_top(participant.group_no, chosen_slot)
        if needs_bye:
            bye_slot = opponent_slot(chosen_slot)
            slot_state[bye_slot] = "BYE"
            locked_slots.add(bye_slot)

        snapshots.append(
            Snapshot(
                action_name,
                [chosen_slot],
                None,
                [participant],
                get_bracket_violations(chosen_matches),
                score_bracket(chosen_matches, number_of_matches, weights=bracket_weights),
                initial_groups=copy.deepcopy(chosen_matches),
            )
        )
        return chosen_slot

    # ---------------------------------------------------------------------------
    # Phase 1: Place top-group-pos participants in strict seeding batches.
    #
    # Batch 0 → hierarchy_groups[0] = [slot 1]        — completely deterministic
    # Batch 1 → hierarchy_groups[1] = [last slot]     — completely deterministic
    # Batch 2 → hierarchy_groups[2] (2 slots)         — greedy best-score + shuffle
    # Batch k → hierarchy_groups[k] (2^(k-1) slots)   — greedy best-score + shuffle
    # ---------------------------------------------------------------------------
    top_sorted = sorted(top_participants, key=lambda p: -p.seeding)
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
                    score_bracket(trial_matches_det, number_of_matches, weights=bracket_weights),
                    initial_groups=copy.deepcopy(trial_matches_det),
                )
            )
        else:
            # Greedy balanced placement within this batch's hierarchy group,
            # falling back to any remaining free slot.
            any_slot_tier = list(range(1, bracket_size + 1))
            for participant in batch_players:
                if place_bye_greedy(participant, [hierarchy_group, any_slot_tier]) is None:
                    raise_with_failure_snapshot(
                        "seed_slot_failure",
                        {
                            "message": (
                                f"No slot available for top-seeded participant "
                                f"{participant.start_number_a} in batch {batch_idx}."
                            ),
                            "type": "seed_slot_failure",
                            "phase": "greedy_batch",
                            "batch_idx": batch_idx,
                            "locked_slots": sorted(locked_slots),
                        },
                        [participant],
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
            score_bracket(post_top_matches, number_of_matches, weights=bracket_weights),
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
    for participant in non_top_bye_recipients:
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

    if non_top_bye_recipients:
        seeded_bye_matches = slots_to_matches(slot_state)
        snapshots.append(
            Snapshot(
                "seeded_byes",
                sorted(locked_slots),
                None,
                list(top_sorted) + list(non_top_bye_recipients),
                get_bracket_violations(seeded_bye_matches),
                score_bracket(seeded_bye_matches, number_of_matches, weights=bracket_weights),
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

    def _fill_residual_soft(residual_players):
        """Best-effort fill of all free slots when hard quarter buckets overflow.

        Monte Carlo over every remaining free slot, keeping the lowest
        score_bracket result.  Half/quarter separation are already heavily
        weighted in the score, so this still favours them without ever failing.
        """
        free_slots_all = [s for s in range(1, bracket_size + 1) if slot_state[s] is None]

        def _fill_order(order):
            trial_state = dict(slot_state)
            for slot, participant in zip(free_slots_all, order):
                trial_state[slot] = participant
            return slots_to_matches(trial_state)

        start_matches = slots_to_matches(slot_state)
        snapshots.append(
            Snapshot(
                "quarter_capacity_degrade",
                sorted(locked_slots),
                None,
                list(residual_players),
                get_bracket_violations(start_matches),
                score_bracket(start_matches, number_of_matches, weights=bracket_weights),
                initial_groups=copy.deepcopy(start_matches),
            )
        )

        best_order = list(residual_players)
        random.shuffle(best_order)
        best_matches = _fill_order(best_order)
        best_score = score_bracket(best_matches, number_of_matches, weights=bracket_weights)
        snapshot_interval = max(1, max_attempts // 10)

        for attempt in range(max_attempts):
            trial_order = list(residual_players)
            random.shuffle(trial_order)
            m_try = _fill_order(trial_order)
            score = score_bracket(m_try, number_of_matches, weights=bracket_weights)
            if score < best_score:
                best_score = score
                best_matches = copy.deepcopy(m_try)
                snapshots.append(
                    Snapshot(
                        "improvement",
                        [attempt],
                        None,
                        None,
                        get_bracket_violations(m_try),
                        score,
                        initial_groups=copy.deepcopy(m_try),
                    )
                )
                if best_score == 0:
                    break
            elif attempt % snapshot_interval == 0:
                snapshots.append(
                    Snapshot(
                        "progress",
                        [attempt],
                        None,
                        None,
                        get_bracket_violations(m_try),
                        score,
                        initial_groups=copy.deepcopy(m_try),
                    )
                )

        snapshots.append(
            Snapshot(
                "final",
                None,
                None,
                None,
                get_bracket_violations(best_matches),
                best_score,
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
        first_full_score = score_bracket(first_full_matches, number_of_matches, weights=bracket_weights)
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
    first_full_score = score_bracket(first_full_matches, number_of_matches, weights=bracket_weights)

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
            score = score_bracket(m_try, number_of_matches, weights=bracket_weights)

            if score < best_score:
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
    final_score = score_bracket(best_matches, number_of_matches, weights=bracket_weights)
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
