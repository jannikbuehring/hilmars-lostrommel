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
    bracket_weights = {
        "quarter_split": 200,
        "half_split": 150,
        "first_vs_first": 100,
        "country_half": 10,
        "country_quarter": 4,
        "base_first": 20,
    }
    for weight_key, config_key in (
        ("half_split", "half_split_weight"),
        ("first_vs_first", "first_vs_first_weight"),
        ("country_half", "country_half_weight"),
        ("country_quarter", "country_quarter_weight"),
        ("base_first", "base_first_weight"),
    ):
        try:
            bracket_weights[weight_key] = config.getint("bracket_draw", config_key, fallback=bracket_weights[weight_key])
        except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
            pass

    top_group_pos = min(p.group_pos for p in class_subset if p.group_pos is not None)
    top_participants = [p for p in class_subset if p.group_pos == top_group_pos]

    # Per-group opposite/same-half loads, used to weight each group winner by how
    # much it actually loads its OWN half.  A winner forces its 2nd/3rd (delta 1/2)
    # into the opposite half and its 4th (delta 3) into the same half; balancing
    # raw winner counts wrongly assumes every group demands the same 2 opposite
    # slots, which breaks for uneven groups (e.g. a consolation group missing its
    # 3rd).  See top_reverse_weight below.
    group_opp_load: dict = {}
    group_same_load: dict = {}
    for _p in class_subset:
        _g = getattr(_p, "group_no", None)
        if _g is None or _p.group_pos is None:
            continue
        _delta = _p.group_pos - top_group_pos
        if _delta in (1, 2):
            group_opp_load[_g] = group_opp_load.get(_g, 0) + 1
        elif _delta == 3:
            group_same_load[_g] = group_same_load.get(_g, 0) + 1

    def top_reverse_weight(group_no):
        """Net load a group's winner places on its OWN half: opposite demand minus
        same-half demand minus the winner's own slot.  A full group (2nd + 3rd in
        the opposite half) yields 1 — so this collapses to the plain winner count
        for symmetric brackets — while a group missing its 3rd yields 0."""
        if group_no is None:
            return 1
        return group_opp_load.get(group_no, 0) - group_same_load.get(group_no, 0) - 1
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
    # Per-step placement penalty, evaluated against an EXPLICIT trial state so a
    # whole batch of participants can be scored as one joint assignment.
    #
    # Primary objective: keep (tops + byes) balanced across quarters/halves.
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
        # Half balance is on the *net load* (winner reverse-weights minus byes), not
        # raw tops — the PRIMARY capacity constraint.  A group winner forces its
        # 2nd/3rd (delta 1/2) into the OPPOSITE half and its 4th (delta 3) into the
        # SAME half, so its net pressure on its own half is top_reverse_weight(g)
        # (= 1 for a full group); a bye consumes a slot with no opposite demand, so
        # each bye a half holds requires one extra unit of winner load to stay
        # feasible (winners and byes co-locate).  Balancing raw tops would treat a
        # 3-2 and a 2-3 split as equal even when only one is fillable, and would
        # over-count a winner from an uneven group (e.g. a consolation group missing
        # its 3rd, whose weight is 0).
        half_load_now = {0: 0, 1: 0}
        for _gno, _gq in trial_tops.items():
            half_load_now[_gq // quarters_per_half] += top_reverse_weight(_gno)
        byes_in_half_now = {
            h: sum(1 for s in trial_locked if trial_state[s] == "BYE" and slot_half(s) == h)
            for h in range(2)
        }
        half_net_now = {h: half_load_now[h] - byes_in_half_now[h] for h in range(2)}

        q = slot_quarter(slot)
        future = combined_in_q[q] + 1 + (1 if needs_bye else 0)
        # Allow up to 1 above the current minimum without penalty.
        combined_excess = max(0, future - min_combined - 1)

        h = q // quarters_per_half
        # A winner adds its reverse-weight; a bye recipient (winner, or the Phase
        # 1b non-winners that also go through here) subtracts one for its bye.
        is_top = participant.group_pos == top_group_pos
        tw = top_reverse_weight(getattr(participant, "group_no", None)) if is_top else 0
        future_h_net = half_net_now[h] + tw - (1 if needs_bye else 0)
        # Penalise if this half's net load would be more than 1 ahead of the opposite.
        half_excess = max(0, future_h_net - half_net_now[1 - h] - 1)

        return combined_excess * 10000 + half_excess * 100000

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
        total += score_bracket(slots_to_matches(trial_state), number_of_matches, weights=bracket_weights)
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
                cost += score_bracket(slots_to_matches(step_state), number_of_matches, weights=bracket_weights)
                if best is None or cost < best[0]:
                    best = (cost, slot)
            if best is None:
                return None
            slot = best[1]
            chosen.append(slot)
            _apply_placement(participant, slot, trial_state, trial_locked, trial_tops, needs_bye)
        return chosen

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
                    score_bracket(step_matches, number_of_matches, weights=bracket_weights),
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
            free_in_group = [s for s in hierarchy_group if slot_state[s] is None]
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
                chunk.append(participant)
                chunk_groups.add(group_no)
                allowed_slots[id(participant)] = allowed
            if not chunk:
                break

            chosen_slots = place_batch(
                chunk, [free_in_group], action_name="bye_assign", allowed_slots=allowed_slots
            )
            if chosen_slots is None:
                # Constraints leave no feasible assignment here; the per-participant
                # tiers below take over for these players.
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
