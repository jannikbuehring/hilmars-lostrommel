"""Module to handle drawing of groups with country conflict avoidance."""
import random
import logging
import copy
from collections import Counter
from models.player import players_by_start_number
from models.draw_data import DrawDataRow
from models.snapshot import Snapshot
from checks.group_checker import check_base_uniqueness, check_country_distribution

def draw_groups(class_subset: list[DrawDataRow], amount_of_groups):
    """Draw groups for a competition class using backtracking to avoid country conflicts."""
    snapshots = []  # store deltas: add/remove of DrawDataRow objects
    def get_violation_count(groups):
        competition = groups[1][0].competition
        country_violations = check_country_distribution(competition, {"dummy": {"group": groups}})
        base_violations = check_base_uniqueness({"dummy": {"group": groups}})
        return len(country_violations) + len(base_violations)


    # Helper to record delta snapshots
    def snapshot_delta(action: str, group: int, participant: DrawDataRow, placement_method=None, batch_end=False):
        snapshots.append({
            "action": action,        # "add" or "remove"
            "group": group,
            "participant": participant,
            "placement_method": placement_method,
            "batch_end": batch_end
        })

    def can_place_in_group(participant, group):
        if len(groups[group]) >= max_group_size:
            return False
        
        if participant.start_number_b is None:  # Single player
            for p in groups[group]:
                if players_by_start_number[p.start_number_a].country == players_by_start_number[participant.start_number_a].country:
                    logging.debug(f"Player {participant.start_number_a} has same country as someone in group {group}.")
                    return False
        else:  # Team
            for t in groups[group]:
                if (players_by_start_number[t.start_number_a].country == players_by_start_number[participant.start_number_a].country
                    and players_by_start_number[t.start_number_b].country == players_by_start_number[participant.start_number_b].country):
                    logging.debug(f"Team {participant.start_number_a}/{participant.start_number_b} conflicts with group {group}.")
                    return False
        return True

    def backtrack(batch, index, assigned_groups):
        if index >= len(batch):
            logging.debug(f"All players of batch placed successfully")
            return True

        participant = batch[index]

        shuffled_groups = list(range(1, amount_of_groups + 1))
        random.shuffle(shuffled_groups)
        for group in shuffled_groups:
            if group not in assigned_groups:
                if can_place_in_group(participant, group):
                    groups[group].append(participant)
                    assigned_groups.add(group)
                    # Mark batch_end True if this is the last participant in the batch
                    is_last_in_batch = (index == len(batch) - 1)
                    snapshot_delta("add", group, participant, placement_method="backtrack", batch_end=is_last_in_batch)

                    if backtrack(batch, index + 1, assigned_groups):
                        logging.debug(f"Added {participant} to group {group}")
                        return True

                    # Undo placement (backtrack)
                    groups[group].remove(participant)
                    assigned_groups.remove(group)
                    snapshot_delta("remove", group, participant, placement_method="backtrack", batch_end=False)

        return False

    def max_group_size(num_participants: int, num_groups: int) -> int:
        if num_groups <= 0:
            raise ValueError("Number of groups must be positive")
        return -(-num_participants // num_groups)  # ceiling division

    class_subset.sort(key=lambda d: d.seeding, reverse=True)
    max_group_size = max_group_size(len(class_subset), amount_of_groups)
    groups = {i + 1: [] for i in range(amount_of_groups)}

    # the first players in each group are assigned deterministically
    for i in range(amount_of_groups):
        # The first batch is always deterministic, so placement_method is 'deterministic'
        is_last_in_batch = (i == amount_of_groups - 1)
        snapshot_delta("add", i+1, class_subset[i], placement_method="deterministic", batch_end=is_last_in_batch)
        groups[i+1].append(class_subset[i])
    class_subset = class_subset[amount_of_groups:]

    for i in range(0, len(class_subset), amount_of_groups):
        batch = class_subset[i:i + amount_of_groups]
        all_groups = set(range(1, amount_of_groups + 1))
        assigned_groups = set()

        if not backtrack(batch, 0, assigned_groups):
            logging.debug("Backtracking failed for batch, using fallback assignment")

            # --- Improved Greedy Heuristic Fallback ---
            available_groups = [g for g in all_groups if g not in assigned_groups]
            # Count country frequencies in batch
            country_freq = Counter()
            for participant in batch:
                a = players_by_start_number[participant.start_number_a]
                country_freq[a.country] += 1
                if participant.start_number_b is not None:
                    b = players_by_start_number[participant.start_number_b]
                    country_freq[b.country] += 1
            # Sort batch: most common countries in batch first, then by how close the country occurrence in all groups is to a multiple of amount_of_groups
            country_occurrences = Counter()
            for group_members in groups.values():
                for member in group_members:
                    a = players_by_start_number[member.start_number_a]
                    country_occurrences[a.country] += 1
                    if member.start_number_b is not None:
                        b = players_by_start_number[member.start_number_b]
                        country_occurrences[b.country] += 1

            def closeness_to_multiple(n, multiple):
                if multiple == 0:
                    return 0
                return min([abs(n - multiple * k) for k in range((n // multiple) + 2)])

            def participant_country_key(participant):
                a = players_by_start_number[participant.start_number_a]
                batch_freq = country_freq[a.country]
                closeness = closeness_to_multiple(country_occurrences[a.country], amount_of_groups)
                if participant.start_number_b is not None:
                    b = players_by_start_number[participant.start_number_b]
                    batch_freq += country_freq[b.country]
                    closeness += closeness_to_multiple(country_occurrences[b.country], amount_of_groups)
                # Sort by batch_freq (desc), then closeness (desc)
                return (-batch_freq, -closeness)

            batch_sorted = sorted(batch, key=participant_country_key)
            idx = 0
            while idx < len(batch_sorted):
                participant = batch_sorted[idx]
                # For each group, count how many from participant's country (and teammate's country)
                group_country_counts = {}
                for group in available_groups:
                    # Check base conflict
                    base_conflict = False
                    a = players_by_start_number[participant.start_number_a]
                    base = a.base
                    for p in groups[group]:
                        pa = players_by_start_number[p.start_number_a]
                        if pa.base == base and base not in (None, "None"):
                            base_conflict = True
                            break
                        if p.start_number_b is not None:
                            pb = players_by_start_number[p.start_number_b]
                            if pb.base == base and base not in (None, "None"):
                                base_conflict = True
                                break
                    if participant.start_number_b is not None:
                        b = players_by_start_number[participant.start_number_b]
                        base_b = b.base
                        for p in groups[group]:
                            pa = players_by_start_number[p.start_number_a]
                            if pa.base == base_b and base_b not in (None, "None"):
                                base_conflict = True
                                break
                            if p.start_number_b is not None:
                                pb = players_by_start_number[p.start_number_b]
                                if pb.base == base_b and base_b not in (None, "None"):
                                    base_conflict = True
                                    break
                    if base_conflict:
                        continue
                    # Count country occurrences
                    count = 0
                    for p in groups[group]:
                        pa = players_by_start_number[p.start_number_a]
                        if pa.country == a.country:
                            count += 1
                        if participant.start_number_b is not None:
                            if p.start_number_b is not None:
                                pb = players_by_start_number[p.start_number_b]
                                if pb.country == b.country:
                                    count += 1
                            if pa.country == b.country:
                                count += 1
                    group_country_counts[group] = count
                if group_country_counts:
                    min_count = min(group_country_counts.values())
                    candidate_groups = [g for g, cnt in group_country_counts.items() if cnt == min_count]
                    chosen_group = random.choice(candidate_groups)
                else:
                    # All groups have base conflict, assign randomly
                    chosen_group = random.choice(available_groups)
                groups[chosen_group].append(participant)
                assigned_groups.add(chosen_group)
                available_groups = [g for g in available_groups if g != chosen_group]
                is_last_in_batch = (idx == len(batch_sorted) - 1)
                snapshot_delta("add", chosen_group, participant, placement_method="greedy-fallback", batch_end=is_last_in_batch)
                logging.debug(f"Greedy-fallback assigned {participant} to group {chosen_group}")

                # After assignment, check if this participant's country is now evenly distributed
                # If so, move all remaining participants of this country to the end of batch_sorted
                # and continue with the next country
                # Compute country counts for all groups
                country = players_by_start_number[participant.start_number_a].country
                # For teams, also check teammate's country
                countries = [country]
                if participant.start_number_b is not None:
                    b_country = players_by_start_number[participant.start_number_b].country
                    if b_country != country:
                        countries.append(b_country)
                
                group_country_counts_new = {}
                for group in available_groups:
                    a = players_by_start_number[participant.start_number_a]
                    # Count country occurrences
                    count = 0
                    for p in groups[group]:
                        pa = players_by_start_number[p.start_number_a]
                        if pa.country == a.country:
                            count += 1
                        if participant.start_number_b is not None:
                            if p.start_number_b is not None:
                                pb = players_by_start_number[p.start_number_b]
                                if pb.country == b.country:
                                    count += 1
                            if pa.country == b.country:
                                count += 1
                    group_country_counts_new[group] = count

                all_countries_distributed_evenly = len(set(group_country_counts_new.values())) == 1
                if (all_countries_distributed_evenly):
                    # Move all remaining participants of this country to the end
                    remaining = []
                    for p in batch_sorted[idx+1:]:
                        country_a = players_by_start_number[p.start_number_a].country
                        country_b = (
                            players_by_start_number[p.start_number_b].country
                            if p.start_number_b is not None
                            else None
                        )

                        if country_a in countries or (country_b and country_b in countries):
                            remaining.append(p)

                    batch_sorted = batch_sorted[:idx+1] + [p for p in batch_sorted[idx+1:] if p not in remaining] + remaining
                idx += 1

    
    # --- Post-draw violation minimization by swapping last batch ---
    current_violation_count = get_violation_count(groups)
    if current_violation_count == 0:
        return groups, snapshots
    
    max_attempts = 1000
    # Get last batch participants and their group assignments
    # Last participants are the last n participants where n is the length of the class subset modulo amount_of_groups (or amount_of_groups if perfectly divisible)
    last_batch_size = len(class_subset) % amount_of_groups
    if last_batch_size == 0:
        last_batch_size = amount_of_groups
    last_batch_indices = range(len(class_subset) - last_batch_size, len(class_subset)) if last_batch_size > 0 else []
    last_batch = [class_subset[i] for i in last_batch_indices] if last_batch_indices else []
    # Build reverse lookup: participant -> group
    participant_to_group = {}
    for group_no, members in groups.items():
        for member in members:
            participant_to_group[member] = group_no

    if last_batch:
        for attempt in range(max_attempts):
            # Build swap candidates: last_batch participants and 'empty' spots
            swap_candidates = list(last_batch)
            empty_spots = []
            for group_no, members in groups.items():
                if len(members) < max_group_size:
                    empty_spots.append((group_no, 'empty'))
            # Choose two swap targets: can be two participants, or one participant and one empty spot
            if swap_candidates and empty_spots:
                # 50% chance to swap with empty
                if random.random() < 0.5:
                    p1 = random.choice(swap_candidates)
                    g1 = participant_to_group.get(p1)
                    g2, _ = random.choice(empty_spots)
                    # Remove p1 from its group and add to g2
                    idx1 = groups[g1].index(p1)
                    groups[g1].pop(idx1)
                    groups[g2].append(p1)
                    participant_to_group[p1] = g2
                    # Recompute violations
                    new_violation_count = get_violation_count(groups)
                    if new_violation_count <= current_violation_count:
                        current_violation_count = new_violation_count
                        if current_violation_count == 0:
                            break
                    else:
                        # Revert swap
                        groups[g2].remove(p1)
                        groups[g1].insert(idx1, p1)
                        participant_to_group[p1] = g1
                    continue
            # Otherwise, swap two participants
            if len(swap_candidates) >= 2:
                p1, p2 = random.sample(swap_candidates, 2)
                g1 = participant_to_group.get(p1)
                g2 = participant_to_group.get(p2)
                if g1 == g2:
                    continue
                idx1 = groups[g1].index(p1)
                idx2 = groups[g2].index(p2)
                groups[g1][idx1], groups[g2][idx2] = p2, p1
                # Recompute violations
                new_violation_count = get_violation_count(groups)
                if new_violation_count <= current_violation_count:
                    participant_to_group[p1], participant_to_group[p2] = g2, g1
                    current_violation_count = new_violation_count
                    if current_violation_count == 0:
                        break
                else:
                    groups[g1][idx1], groups[g2][idx2] = p1, p2
    
    
    
    # Return both groups and the delta snapshots
    return groups, snapshots
    
# Define a safe EmptySlot class
class EmptySlot:
    """A placeholder for empty group slots."""
    def __init__(self):
        self.country = None
        self.base = None
        self.start_number_a = "EMPTY"
        self.start_number_b = None
        self.competition = None
        self.qttr = None
    def __repr__(self):
        return "Empty Slot"
    def __deepcopy__(self, memo):
        # EmptySlot is stateless, so just return a new instance
        return type(self)()

def draw_groups_monte_carlo(class_subset: list[DrawDataRow], amount_of_groups, max_attempts=10000):
    """Draw groups for a competition class using Monte Carlo optimization to minimize country conflicts."""
    # Helper to record delta snapshots
    snapshots = []
    def snapshot_delta(action: str, groups: list[int], index_in_group: int, participants: list[DrawDataRow], violation_count):
        snapshots.append(Snapshot(action, groups, index_in_group, participants, violation_count))

    def get_violation_count(groups):
        competition = groups[1][0].competition
        country_violations = check_country_distribution(competition, {"dummy": {"group": groups}})
        base_violations = check_base_uniqueness({"dummy": {"group": groups}})
        return len(country_violations) + len(base_violations)

    def calc_max_group_size(num_participants: int, num_groups: int) -> int:
        return -(-num_participants // num_groups)
    
    class_subset.sort(key=lambda d: d.seeding, reverse=True)
    max_group_size = calc_max_group_size(len(class_subset), amount_of_groups)
    groups = {i + 1: [] for i in range(amount_of_groups)}

    # Deterministic batch assignment
    batches = []
    for i in range(0, len(class_subset), amount_of_groups):
        batch = class_subset[i:i + amount_of_groups]
        batches.append(batch)
        for j, participant in enumerate(batch):
            group_no = j + 1
            groups[group_no].append(participant)

    # Fill up groups with EmptySlot for empty slots
    for group_no in groups:
        while len(groups[group_no]) < max_group_size:
            groups[group_no].append(EmptySlot())

    # Monte Carlo optimization
    current_violation_count = get_violation_count(groups)
    snapshots.append(Snapshot(None, None, None, None, current_violation_count, initial_groups=copy.deepcopy(groups)))

    for attempt in range(max_attempts):
        # Choose a batch randomly
        batch_idx = random.randint(0, len(batches) - 1)
        batch = batches[batch_idx]
        # Find group slots for this batch, but never swap the first batch (index 0)
        batch_slots = []
        for group_no in groups:
            slot_idx = batch_idx
            if slot_idx == 0:
                continue  # Never swap first batch
            if slot_idx < len(groups[group_no]):
                batch_slots.append((group_no, slot_idx))
        # Only swap if there are at least two eligible slots
        if len(batch_slots) < 2:
            continue
        slot1, slot2 = random.sample(batch_slots, 2)
        g1, idx1 = slot1
        g2, idx2 = slot2
        if idx1 != idx2:
            raise IndexError("This should never happen. Can only swap same index in different groups.")
        p1 = groups[g1][idx1]
        p2 = groups[g2][idx2]
        # Swap
        groups[g1][idx1], groups[g2][idx2] = p2, p1
        # Only keep swap if violation count is not worse
        new_violation_count = get_violation_count(groups)
        snapshot_delta("swap", [g1, g2], idx1, [p1, p2], new_violation_count)
        if new_violation_count <= current_violation_count:
            current_violation_count = new_violation_count
            if current_violation_count == 0:
                break
        else:
            # Revert swap
            groups[g1][idx1], groups[g2][idx2] = p1, p2
            snapshot_delta("revert", [g1, g2], idx1, [p1, p2], current_violation_count)
    # Remove EmptySlot placeholders from groups
    for group_no in groups:
        groups[group_no] = [p for p in groups[group_no] if not isinstance(p, EmptySlot)]
    return groups, snapshots