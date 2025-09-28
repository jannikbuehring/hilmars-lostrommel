import math
import random
import logging
from models.player import Player, players_by_start_number
from models.draw_data import DrawDataRow

class GroupDrawer:
    def draw_groups(self, class_subset: list[DrawDataRow], amount_of_groups):
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

        def can_place_in_group_no_base_conflict(participant, group):
            if participant.start_number_b is None:  # Single player
                for p in groups[group]:
                    if players_by_start_number[p.start_number_a].base == players_by_start_number[participant.start_number_a].base:
                        logging.debug(f"Player {participant.start_number_a} has same base as someone in group {group}.")
                        return False
            else:  # Team
                for t in groups[group]:
                    if (players_by_start_number[t.start_number_a].base == players_by_start_number[participant.start_number_a].base
                        and players_by_start_number[t.start_number_b].base == players_by_start_number[participant.start_number_b].base):
                        logging.debug(f"Team {participant.start_number_a}/{participant.start_number_b} base conflict with group {group}.")
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
                participants_to_assign_randomly = []

                for idx, participant in enumerate(batch):
                    placed = False
                    # Fallback: distribute countries as evenly as possible, but never allow same base in group
                    country = players_by_start_number[participant.start_number_a].country
                    base = players_by_start_number[participant.start_number_a].base
                    country_counts = {}
                    valid_groups = []
                    for group in range(1, amount_of_groups + 1):
                        if group not in assigned_groups:
                            # Check base conflict
                            base_conflict = False
                            for p in groups[group]:
                                if p.start_number_b is None:
                                    b = players_by_start_number[p.start_number_a].base
                                    if b == base:
                                        base_conflict = True
                                        break
                                else:
                                    b1 = players_by_start_number[p.start_number_a].base
                                    b2 = players_by_start_number[p.start_number_b].base
                                    if b1 == base or b2 == base:
                                        base_conflict = True
                                        break
                            if base_conflict:
                                continue
                            # Count country occurrences
                            count = 0
                            for p in groups[group]:
                                if p.start_number_b is None:
                                    c = players_by_start_number[p.start_number_a].country
                                    if c == country:
                                        count += 1
                                else:
                                    c1 = players_by_start_number[p.start_number_a].country
                                    c2 = players_by_start_number[p.start_number_b].country
                                    if c1 == country:
                                        count += 1
                                    if participant.start_number_b is not None and c2 == country:
                                        count += 1
                            country_counts[group] = count
                            valid_groups.append(group)
                    if country_counts:
                        min_count = min(country_counts.values())
                        candidate_groups = [g for g, cnt in country_counts.items() if cnt == min_count]
                        chosen_group = random.choice(candidate_groups)
                        groups[chosen_group].append(participant)
                        assigned_groups.add(chosen_group)
                        is_last_in_batch = (idx == len(batch) - 1)
                        snapshot_delta("add", chosen_group, participant, placement_method="fallback", batch_end=is_last_in_batch)
                        logging.debug(f"Added {participant} to group {chosen_group} (country+base fallback)")
                        placed = True

                    if not placed:
                        participants_to_assign_randomly.append((idx, participant))

                for idx, participant in participants_to_assign_randomly:
                    available_groups = list(all_groups - assigned_groups)
                    random_group = random.choice(available_groups)
                    groups[random_group].append(participant)
                    assigned_groups.add(random_group)
                    is_last_in_batch = (idx == len(batch) - 1)
                    snapshot_delta("add", random_group, participant, placement_method="random", batch_end=is_last_in_batch)
                    logging.debug(f"Randomly assigned {participant} to group {random_group}")

        # Return both groups and the delta snapshots
        return groups, snapshots