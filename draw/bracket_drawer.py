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

    def place_seeded_batch(participants, action_name):
        group_index = 0
        for participant in participants:
            needs_bye = id(participant) in bye_recipient_ids
            candidate_group_index = None
            candidate_slots = []

            for idx in range(group_index, len(hierarchy_groups)):
                available = usable_slots_in_group(hierarchy_groups[idx], slot_state, needs_bye)
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

            if not candidate_slots:
                raise ValueError("No available bracket slot for seeded placement.")

            scored_candidates = []
            for slot in candidate_slots:
                score, trial_matches = score_candidate_placement(participant, slot, slot_state, needs_bye)
                scored_candidates.append((score, slot, trial_matches))

            best_score = min(score for score, _, _ in scored_candidates)
            best_choices = [(slot, trial_matches) for score, slot, trial_matches in scored_candidates if score == best_score]
            chosen_slot, chosen_matches = rng.choice(best_choices)

            slot_state[chosen_slot] = participant
            locked_slots.add(chosen_slot)
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

            if candidate_group_index is not None:
                group_index = candidate_group_index

    top_sorted = sorted(top_participants, key=lambda p: -p.seeding)
    place_seeded_batch(top_sorted, "top_seed_assign")

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
        place_seeded_batch(remaining_bye_participants, "bye_assign")

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

    def build_matches_from_perm(perm):
        trial_state = dict(slot_state)
        for slot, participant in zip(free_slots, perm):
            trial_state[slot] = participant
        return slots_to_matches(trial_state)

    participants_list = list(remaining)
    first_full_matches = build_matches_from_perm(participants_list)
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

    for attempt in range(max_attempts):
        perm = participants_list[:]
        rng.shuffle(perm)
        m_try = build_matches_from_perm(perm)
        score = score_bracket(m_try, number_of_matches)

        if score < best_score:
            best_score = score
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
