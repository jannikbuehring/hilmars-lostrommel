"""Module to handle drawing of single-elimination brackets with country conflict avoidance."""
import math
import random
import logging
import configparser
from typing import List
from models.draw_data import DrawDataRow
from models.draw_data import seeding_by_start_numbers
from models.snapshot import Snapshot
from checks.bracket_checker import (
    score_bracket,
    check_half_group_separation,
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

    def slot_to_match(slot: int):
        return ((slot + 1) // 2, 0 if slot % 2 == 1 else 1)

    def slot_half(slot: int) -> int:
        match_idx, _ = slot_to_match(slot)
        return 0 if match_idx <= (number_of_matches // 2) else 1

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
            "half_group_separation": check_half_group_separation(current_matches, number_of_matches),
            "first_vs_first": check_no_first_vs_first(current_matches),
            "country_balance": check_country_balance_halves(current_matches, number_of_matches),
            "base_conflicts": check_base_conflicts_first_round(current_matches),
        }

    max_attempts = 2000
    try:
        max_attempts = int(config.get("bracket_draw", {}).get("max_attempts", max_attempts))
    except (TypeError, ValueError, KeyError, AttributeError, configparser.Error):
        pass

    rng = random.Random()
    try:
        seed = int(config["settings"].get("random_seed", "0"))
        if seed:
            rng.seed(seed)
    except (TypeError, ValueError, KeyError, configparser.Error):
        pass

    top_group_pos = min(p.group_pos for p in class_subset if p.group_pos is not None)
    top_participants = [p for p in class_subset if p.group_pos == top_group_pos]
    bye_recipients = class_subset[:byes]
    bye_recipient_ids = {id(p) for p in bye_recipients}
    slot_state = empty_slot_state()
    locked_slots = set()
    hierarchy_groups = bye_hierarchy(bracket_size)
    group_top_half = {}

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

    def slot_satisfies_half_constraint(participant, slot):
        required_half = required_half_for_participant(participant)
        if required_half is None:
            return True
        return slot_half(slot) == required_half

    def score_candidate_placement(participant, slot, current_state, needs_bye):
        trial_state = dict(current_state)
        trial_state[slot] = participant
        if needs_bye:
            trial_state[opponent_slot(slot)] = "BYE"
        trial_matches = slots_to_matches(trial_state)
        return score_bracket(trial_matches, number_of_matches), trial_matches

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
            score_bracket(current_matches, number_of_matches),
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
            score_bracket(initial_matches, number_of_matches),
            initial_groups=copy.deepcopy(initial_matches),
        )
    )

    def place_seeded_batch_backtracking(participants, action_name, feasibility_check=None):
        def recurse(participant_index, group_index):
            if participant_index >= len(participants):
                if feasibility_check is not None and not feasibility_check():
                    return False
                return True

            participant = participants[participant_index]
            needs_bye = id(participant) in bye_recipient_ids
            candidate_group_index = None
            candidate_slots = []

            for idx in range(group_index, len(hierarchy_groups)):
                available = usable_slots_in_group(hierarchy_groups[idx], slot_state, needs_bye)
                available = [slot for slot in available if slot_satisfies_half_constraint(participant, slot)]
                if available:
                    candidate_group_index = idx
                    candidate_slots = available
                    break

            if not candidate_slots:
                candidate_slots = [
                    slot
                    for slot in range(1, bracket_size + 1)
                    if slot_state[slot] is None and (not needs_bye or slot_state[opponent_slot(slot)] is None)
                ]
                candidate_slots = [slot for slot in candidate_slots if slot_satisfies_half_constraint(participant, slot)]

            scored_candidates = []
            for slot in candidate_slots:
                score, trial_matches = score_candidate_placement(participant, slot, slot_state, needs_bye)
                scored_candidates.append((score, slot, trial_matches))

            scored_candidates.sort(key=lambda item: item[0])
            if not scored_candidates:
                return False

            best_score = scored_candidates[0][0]
            best_candidates = [item for item in scored_candidates if item[0] == best_score]
            rng.shuffle(best_candidates)

            for _, chosen_slot, chosen_matches in best_candidates:
                slot_state[chosen_slot] = participant
                locked_slots.add(chosen_slot)
                if getattr(participant, "group_pos", None) == top_group_pos and getattr(participant, "group_no", None) is not None:
                    group_top_half[participant.group_no] = slot_half(chosen_slot)
                bye_slot = None
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
                        score_bracket(chosen_matches, number_of_matches),
                        initial_groups=copy.deepcopy(chosen_matches),
                    )
                )

                next_group_index = candidate_group_index if candidate_group_index is not None else group_index
                if recurse(participant_index + 1, next_group_index):
                    return True

                snapshots.pop()
                locked_slots.remove(chosen_slot)
                slot_state[chosen_slot] = None
                if bye_slot is not None:
                    locked_slots.remove(bye_slot)
                    slot_state[bye_slot] = None
                if getattr(participant, "group_pos", None) == top_group_pos and getattr(participant, "group_no", None) is not None:
                    group_top_half.pop(participant.group_no, None)

            return False

        if not recurse(0, 0):
            raise_with_failure_snapshot(
                "seed_slot_failure",
                {
                    "message": "Unable to place top seeded participants without violating half feasibility.",
                    "type": "seed_slot_failure",
                    "phase": "top_seed_backtracking",
                    "top_group_pos": top_group_pos,
                    "locked_slots": sorted(locked_slots),
                    "group_top_half": dict(group_top_half),
                },
                list(participants),
            )

    # Feasibility check: after all pos-1 players are placed, verify that the
    # resulting group_top_half map leaves enough free slots in each half to
    # accommodate every constrained non-top participant (including those who
    # will receive a bye and therefore consume two adjacent slots).
    remaining_bye_ids = {id(p) for p in bye_recipients if p.group_pos != top_group_pos}

    def top_seed_feasibility_check():
        req_in_half = {0: 0, 1: 0}
        for p in class_subset:
            if p.group_pos == top_group_pos:
                continue
            req = required_half_for_participant_with_map(p, group_top_half)
            if req in (0, 1):
                # Bye recipients occupy their own slot AND the adjacent BYE slot.
                slots_needed = 2 if id(p) in remaining_bye_ids else 1
                req_in_half[req] += slots_needed
        free_in_half = {
            h: sum(1 for s in range(1, bracket_size + 1)
                   if slot_state[s] is None and slot_half(s) == h)
            for h in (0, 1)
        }
        return all(req_in_half[h] <= free_in_half[h] for h in (0, 1))

    top_sorted = sorted(top_participants, key=lambda p: -p.seeding)
    place_seeded_batch_backtracking(top_sorted, "top_seed_assign",
                                    feasibility_check=top_seed_feasibility_check)

    post_top_matches = slots_to_matches(slot_state)
    snapshots.append(
        Snapshot(
            "top_seed_complete",
            sorted(locked_slots),
            None,
            list(top_sorted),
            get_bracket_violations(post_top_matches),
            score_bracket(post_top_matches, number_of_matches),
            initial_groups=copy.deepcopy(post_top_matches),
        )
    )

    remaining_bye_participants = [
        participant for participant in bye_recipients if participant.group_pos != top_group_pos
    ]
    if remaining_bye_participants:
        place_seeded_batch_backtracking(remaining_bye_participants, "bye_assign")

    fixed_state_matches = slots_to_matches(slot_state)
    snapshots.append(
        Snapshot(
            "seeded_byes",
            sorted(locked_slots),
            None,
            list(top_sorted) + list(remaining_bye_participants),
            get_bracket_violations(fixed_state_matches),
            score_bracket(fixed_state_matches, number_of_matches),
            initial_groups=copy.deepcopy(fixed_state_matches),
        )
    )

    free_slots = [slot for slot in range(1, bracket_size + 1) if slot_state[slot] is None]
    remaining = [
        participant
        for participant in class_subset
        if id(participant) not in bye_recipient_ids and participant.group_pos != top_group_pos
    ]
    free_slots_by_half = {
        0: [slot for slot in free_slots if slot_half(slot) == 0],
        1: [slot for slot in free_slots if slot_half(slot) == 1],
    }

    def build_matches_from_half_pools(pool_h0, pool_h1):
        """Assign ordered half pools to free slots and return a matches dict."""
        trial_state = dict(slot_state)
        for slot, participant in zip(free_slots_by_half[0], pool_h0):
            trial_state[slot] = participant
        for slot, participant in zip(free_slots_by_half[1], pool_h1):
            trial_state[slot] = participant
        return slots_to_matches(trial_state)

    # --- Phase 2: Harden half assignment ---
    # Classify every remaining participant into a fixed half before the MC runs.
    # Constrained participants (group_no in group_top_half) are individually assigned.
    # Unconstrained participants are grouped by group_no so that all members of the
    # same group always land in the same half, preventing "positions 2/3 split across
    # halves" violations that arose when unconstrained participants were re-shuffled
    # independently on each MC attempt.
    required_by_half = {0: [], 1: []}
    unconstrained_by_group: dict = {}  # group key -> [participants]

    _none_key_counter = 0
    for participant in remaining:
        req_half = required_half_for_participant(participant)
        if req_half in (0, 1):
            required_by_half[req_half].append(participant)
        else:
            group_no = getattr(participant, "group_no", None)
            if group_no is None:
                # No group info: treat as an independent singleton
                _none_key_counter += 1
                unconstrained_by_group[f"_none_{_none_key_counter}"] = [participant]
            else:
                unconstrained_by_group.setdefault(group_no, []).append(participant)

    half_capacity = {0: len(free_slots_by_half[0]), 1: len(free_slots_by_half[1])}
    required_counts = {0: len(required_by_half[0]), 1: len(required_by_half[1])}

    impossible_halves = [h for h in (0, 1) if required_counts[h] > half_capacity[h]]
    if impossible_halves:
        raise_with_failure_snapshot(
            "permutation_failure",
            {
                "message": "Half-capacity is exceeded by strictly constrained participants.",
                "type": "capacity_impossible",
                "free_slot_capacity": half_capacity,
                "required_counts": required_counts,
                "group_top_half": dict(group_top_half),
                "remaining_start_numbers": [p.start_number_a for p in remaining],
                "impossible_halves": impossible_halves,
            },
            list(remaining),
        )

    # Greedily assign each unconstrained group to the half with the most remaining
    # capacity, keeping all members of the same group together.
    remaining_capacity = {0: half_capacity[0] - required_counts[0], 1: half_capacity[1] - required_counts[1]}
    final_pool_half = {0: list(required_by_half[0]), 1: list(required_by_half[1])}

    unconstrained_groups = list(unconstrained_by_group.values())
    rng.shuffle(unconstrained_groups)

    for group_members in unconstrained_groups:
        n = len(group_members)
        can_fit_0 = remaining_capacity[0] >= n
        can_fit_1 = remaining_capacity[1] >= n
        if can_fit_0 and can_fit_1:
            chosen_half = 0 if remaining_capacity[0] >= remaining_capacity[1] else 1
        elif can_fit_0:
            chosen_half = 0
        elif can_fit_1:
            chosen_half = 1
        else:
            raise_with_failure_snapshot(
                "permutation_failure",
                {
                    "message": "Unable to fit unconstrained group into either half.",
                    "type": "unconstrained_distribution_impossible",
                    "free_slot_capacity": half_capacity,
                    "required_counts": required_counts,
                    "remaining_capacity": dict(remaining_capacity),
                    "group_top_half": dict(group_top_half),
                    "remaining_start_numbers": [p.start_number_a for p in remaining],
                },
                list(remaining),
            )
        final_pool_half[chosen_half].extend(group_members)
        remaining_capacity[chosen_half] -= n

    for h in (0, 1):
        if len(final_pool_half[h]) != half_capacity[h]:
            raise_with_failure_snapshot(
                "permutation_failure",
                {
                    "message": f"Half {h} pool size {len(final_pool_half[h])} does not match slot capacity {half_capacity[h]}.",
                    "type": "half_pool_size_mismatch",
                    "group_top_half": dict(group_top_half),
                    "remaining_start_numbers": [p.start_number_a for p in remaining],
                },
                list(remaining),
            )

    # Initial fill: shuffle each pool once to produce the starting bracket.
    init_pool_h0 = list(final_pool_half[0])
    init_pool_h1 = list(final_pool_half[1])
    rng.shuffle(init_pool_h0)
    rng.shuffle(init_pool_h1)

    first_full_matches = build_matches_from_half_pools(init_pool_h0, init_pool_h1)
    first_full_violations = get_bracket_violations(first_full_matches)
    first_full_score = score_bracket(first_full_matches, number_of_matches)

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

    if not remaining:
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

    snapshot_interval = max(1, max_attempts // 10)

    # --- Phase 3a: Half-0 Monte Carlo ---
    # The half-1 pool is fixed at the initial shuffle; only half-0 is varied.
    best_pool_h0 = list(init_pool_h0)
    fixed_pool_h1 = list(init_pool_h1)

    snapshots.append(
        Snapshot(
            "half0_mc_start",
            None,
            None,
            None,
            first_full_violations,
            first_full_score,
            initial_groups=copy.deepcopy(first_full_matches),
        )
    )

    for attempt in range(max_attempts):
        trial_pool_h0 = list(final_pool_half[0])
        rng.shuffle(trial_pool_h0)
        m_try = build_matches_from_half_pools(trial_pool_h0, fixed_pool_h1)
        score = score_bracket(m_try, number_of_matches)

        if score < best_score:
            best_score = score
            best_pool_h0 = trial_pool_h0
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

    # --- Phase 3b: Half-1 Monte Carlo ---
    # Fix half-0 at the best arrangement found above; vary half-1.
    best_pool_h1 = list(init_pool_h1)

    snapshots.append(
        Snapshot(
            "half1_mc_start",
            None,
            None,
            None,
            get_bracket_violations(best_matches),
            best_score,
            initial_groups=copy.deepcopy(best_matches),
        )
    )

    for attempt in range(max_attempts):
        trial_pool_h1 = list(final_pool_half[1])
        rng.shuffle(trial_pool_h1)
        m_try = build_matches_from_half_pools(best_pool_h0, trial_pool_h1)
        score = score_bracket(m_try, number_of_matches)

        if score < best_score:
            best_score = score
            best_pool_h1 = trial_pool_h1
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

    final_violations = get_bracket_violations(best_matches)
    final_score = score_bracket(best_matches, number_of_matches)
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
