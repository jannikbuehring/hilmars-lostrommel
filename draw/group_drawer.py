"""Module to handle drawing of groups with country conflict avoidance."""
import random
import logging
from collections import Counter
from models.player import players_by_start_number
from models.draw_data import DrawDataRow

class GroupDrawer:
    """Class to handle drawing of groups with country conflict avoidance."""
    def draw_groups(self, class_subset: list[DrawDataRow], amount_of_groups):
        """Draw groups for a competition class using backtracking to avoid country conflicts."""
        snapshots = []  # store deltas: add/remove of DrawDataRow objects

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
                # Sort batch: most common countries first
                def participant_country_key(participant):
                    a = players_by_start_number[participant.start_number_a]
                    freq = country_freq[a.country]
                    if participant.start_number_b is not None:
                        b = players_by_start_number[participant.start_number_b]
                        freq += country_freq[b.country]
                    return -freq
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

        # Return both groups and the delta snapshots
        return groups, snapshots