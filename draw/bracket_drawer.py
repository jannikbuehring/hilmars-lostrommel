"""Module to handle drawing of single-elimination brackets with country conflict avoidance."""
import math
import random
import logging
from typing import List, Optional
from models.player import players_by_start_number
from models.draw_data import DrawDataRow
from models.draw_data import seeding_by_start_numbers
from models.match import Match
from models.snapshot import Snapshot
from viewer.bracket_viewer import show_bracket_table
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

    def bye_hierarchy(num_matches: int) -> List[List[int]]:
        """Return hierarchical subdivisions for bye placement.
        Example for num_matches=16:
            [[1], [16], [8,9], [4,5,12,13], [2,3,6,7,10,11,14,15]]
        """
        if num_matches < 2 or (num_matches & (num_matches - 1)) != 0:
            raise ValueError("num_matches must be a power of two >= 2")

        levels = int(math.log2(num_matches))
        groups: List[List[int]] = [[1], [num_matches]]

        # For each level L produce all seam pairs (boundary, boundary+1)
        # using block = num_matches // (2**L) and taking i odd only.
        for L in range(1, levels):
            block = num_matches // (2 ** L)
            group: List[int] = []
            # i goes 1..(2**L - 1); pick odd i to avoid duplicating seams from higher levels
            for i in range(1, 2 ** L):
                if i % 2 == 1:
                    boundary = i * block
                    group.append(boundary)
                    group.append(boundary + 1)
            groups.append(group)

        return groups

    def generate_bye_order(num_matches: int) -> List[int]:
        """Flatten the hierarchy into the deterministic full order."""
        groups = bye_hierarchy(num_matches)
        order: List[int] = []
        for g in groups:
            order.extend(g)
        return order

    def pick_byes(num_matches: int, num_byes: int, bye_recipients: list[DrawDataRow], seed: Optional[int] = None) -> List[int]:
        """Pick num_byes match indices while balancing halves and group-by-half constraints."""
        if num_byes < 0:
            raise ValueError("num_byes must be >= 0")
        if num_byes == 0:
            return []

        full_groups = bye_hierarchy(num_matches)
        slot_order = [slot for group in full_groups for slot in group]
        slot_half = {slot: 0 if slot <= (num_matches // 2) else 1 for slot in slot_order}
        available_slots = list(slot_order)
        chosen: List[int] = []
        half_counts = [0, 0]

        # Group-level constraints: if a bye recipient from a group appears in both
        # the 1/4 and 2/3 sets, those participants must be placed in opposite halves.
        group_half_assignments = {}

        def _preferred_half_for_pos(pos: int) -> int:
            return 0 if pos in (1, 4) else 1

        for recipient in bye_recipients:
            group_no = recipient.group_no
            pos_set = "14" if recipient.group_pos in (1, 4) else "23"
            assigned_half = None

            if group_no in group_half_assignments and pos_set in group_half_assignments[group_no]:
                assigned_half = group_half_assignments[group_no][pos_set]
            elif group_no in group_half_assignments:
                # If the opposite position set is already anchored, use the opposite half.
                other_set = "23" if pos_set == "14" else "14"
                if other_set in group_half_assignments[group_no]:
                    assigned_half = 1 - group_half_assignments[group_no][other_set]

            if assigned_half is None:
                preferred_half = _preferred_half_for_pos(recipient.group_pos)
                # Keep halves balanced: choose the half with fewer assigned byes when possible.
                if half_counts[0] < half_counts[1]:
                    candidate_halves = [0, 1]
                elif half_counts[1] < half_counts[0]:
                    candidate_halves = [1, 0]
                else:
                    candidate_halves = [preferred_half, 1 - preferred_half]

                for half in candidate_halves:
                    if any(slot_half[slot] == half for slot in available_slots):
                        assigned_half = half
                        break
                if assigned_half is None:
                    assigned_half = slot_half[available_slots[0]]

            if group_no not in group_half_assignments:
                group_half_assignments[group_no] = {}
            group_half_assignments[group_no][pos_set] = assigned_half

            # Select the earliest available slot in the assigned half.
            slot_candidates = [slot for slot in available_slots if slot_half[slot] == assigned_half]
            if not slot_candidates:
                slot_candidates = available_slots
            selected = slot_candidates[0]
            available_slots.remove(selected)
            chosen.append(selected)
            half_counts[assigned_half] += 1

        return chosen

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

    # 1. Sort: prioritize group_pos (1st before 2nd), then seeding
    class_subset.sort(key=lambda p: (p.group_pos, -p.seeding))

    num_participants = len(class_subset)

    # 2. Find nearest power of 2 for bracket size
    bracket_size = 1 << (num_participants - 1).bit_length()
    number_of_matches = bracket_size // 2
    byes = bracket_size - num_participants
    logging.debug(f"Bracket size: {bracket_size}, participants: {num_participants}, byes: {byes}")

    # 3. Create matches
    matches = {index: [] for index in range(1, number_of_matches + 1) }
    bye_slots = pick_byes(number_of_matches, byes, class_subset[:byes])

    def get_bracket_violations(current_matches):
        return {
            "half_group_separation": check_half_group_separation(current_matches, number_of_matches),
            "first_vs_first": check_no_first_vs_first(current_matches),
            "country_balance": check_country_balance_halves(current_matches, number_of_matches),
            "base_conflicts": check_base_conflicts_first_round(current_matches),
        }

    # Snapshot the empty bracket before any BYE placement
    snapshots = [
        Snapshot(
            "bye_start",
            None,
            None,
            None,
            get_bracket_violations(matches),
            score_bracket(matches, number_of_matches),
            initial_groups=copy.deepcopy(matches),
        )
    ]

    # 4. Slot in Byes
    # Place BYE holders: top-seeded participants get BYEs and are fixed
    for idx, bye_slot in enumerate(bye_slots):
        matches[bye_slot].append("BYE")
        matches[bye_slot].append(class_subset[idx])
        snapshots.append(
            Snapshot(
                "bye_assign",
                [bye_slot],
                None,
                [class_subset[idx]],
                get_bracket_violations(matches),
                score_bracket(matches, number_of_matches),
                initial_groups=copy.deepcopy(matches),
            )
        )

    # Remaining participants to place
    remaining = class_subset[len(bye_slots):]

    # Snapshot the bracket after all BYEs are placed
    initial_byes_state = copy.deepcopy(matches)
    snapshots.append(
        Snapshot(
            "bye_complete",
            list(bye_slots),
            None,
            [class_subset[i] for i in range(len(bye_slots))],
            get_bracket_violations(initial_byes_state),
            score_bracket(initial_byes_state, number_of_matches),
            initial_groups=copy.deepcopy(initial_byes_state),
        )
    )

    # Helper to build a full matches structure from a permutation of remaining participants
    def build_matches_from_perm(perm):
        m = {k: list(v) for k, v in matches.items()}  # shallow copy existing BYE placements
        it = iter(perm)
        for match_idx in range(1, number_of_matches + 1):
            cur = m[match_idx]
            # if BYE already present, skip to next
            if len(cur) == 2:
                continue
            # ensure we append two participants for empty matches
            try:
                p1 = next(it)
            except StopIteration:
                p1 = None
            try:
                p2 = next(it)
            except StopIteration:
                p2 = None
            if p1 is not None:
                m[match_idx].append(p1)
            if p2 is not None:
                m[match_idx].append(p2)
        return m

    # Monte Carlo / randomized search for low-score assignment
    max_attempts = 2000
    try:
        max_attempts = int(config.get("bracket_draw", {}).get("max_attempts", max_attempts))
    except Exception:
        # config not present: keep default
        pass

    rng = random.Random()
    # Support seeded determinism if configured
    try:
        seed = int(config["settings"].get("random_seed", "0"))
        if seed:
            rng.seed(seed)
    except Exception:
        pass

    participants_list = list(remaining)

    # Build the first full bracket fill and record it as the starting snapshot.
    first_full_matches = build_matches_from_perm(participants_list)
    first_full_violations = get_bracket_violations(first_full_matches)
    first_full_score = score_bracket(first_full_matches, number_of_matches)

    snapshots.append(
        Snapshot(
            "seeded_byes",
            None,
            None,
            None,
            get_bracket_violations(initial_byes_state),
            score_bracket(initial_byes_state, number_of_matches),
            initial_groups=copy.deepcopy(initial_byes_state),
        )
    )
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

    # If no remaining participants, simply return current matches and snapshots
    if not remaining:
        snapshots.append(Snapshot("final", None, None, None, first_full_violations, first_full_score, initial_groups=copy.deepcopy(first_full_matches)))
        return first_full_matches, snapshots

    snapshot_interval = max(1, max_attempts // 10)

    # Try randomized permutations and keep best-scoring bracket
    for attempt in range(max_attempts):
        perm = participants_list[:]
        rng.shuffle(perm)
        m_try = build_matches_from_perm(perm)
        score = score_bracket(m_try, number_of_matches)

        if score < best_score:
            best_score = score
            best_matches = copy.deepcopy(m_try)
            violations = get_bracket_violations(m_try)
            snapshots.append(Snapshot("improvement", [attempt], None, None, violations, score, initial_groups=copy.deepcopy(m_try)))
            if best_score == 0:
                break
        elif attempt % snapshot_interval == 0:
            violations = get_bracket_violations(m_try)
            snapshots.append(Snapshot("progress", [attempt], None, None, violations, score, initial_groups=copy.deepcopy(m_try)))

    if best_matches is None:
        # fallback: deterministic filling left-to-right
        best_matches = build_matches_from_perm(participants_list)
        best_score = score_bracket(best_matches, number_of_matches)
        violations = get_bracket_violations(best_matches)
        snapshots.append(Snapshot("fallback", [], None, None, violations, best_score, initial_groups=copy.deepcopy(best_matches)))

    # Always preserve a final replay state for the chosen bracket
    final_violations = get_bracket_violations(best_matches)
    final_score = score_bracket(best_matches, number_of_matches)
    snapshots.append(Snapshot("final", None, None, None, final_violations, final_score, initial_groups=copy.deepcopy(best_matches)))

    return best_matches, snapshots
