import math
import random
import logging
from models.player import Player, players_by_start_number
from models.draw_data import DrawDataRow

class GroupDrawer:
    def draw_groups(self, class_subset: list[DrawDataRow], amount_of_groups):
        snapshots = []  # store deltas: add/remove of DrawDataRow objects

        # Helper to record delta snapshots
        def snapshot_delta(action: str, group: int, participant: DrawDataRow):
            snapshots.append({
                "action": action,        # "add" or "remove"
                "group": group,
                "participant": participant
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

            for group in range(1, amount_of_groups + 1):
                if group not in assigned_groups:
                    if can_place_in_group(participant, group):
                        groups[group].append(participant)
                        assigned_groups.add(group)
                        snapshot_delta("add", group, participant)

                        if backtrack(batch, index + 1, assigned_groups):
                            logging.debug(f"Added {participant} to group {group}")
                            return True

                        # Undo placement (backtrack)
                        groups[group].remove(participant)
                        assigned_groups.remove(group)
                        snapshot_delta("remove", group, participant)

            return False

        def max_group_size(num_participants: int, num_groups: int) -> int:
            if num_groups <= 0:
                raise ValueError("Number of groups must be positive")
            return -(-num_participants // num_groups)  # ceiling division

        class_subset.sort(key=lambda d: d.seeding, reverse=True)
        max_group_size = max_group_size(len(class_subset), amount_of_groups)
        groups = {i + 1: [] for i in range(amount_of_groups)}

        for i in range(0, len(class_subset), amount_of_groups):
            batch = class_subset[i:i + amount_of_groups]
            all_groups = set(range(1, amount_of_groups + 1))
            assigned_groups = set()

            if not backtrack(batch, 0, assigned_groups):
                logging.debug("Backtracking failed for batch, using fallback assignment")
                participants_to_assign_randomly = []

                for participant in batch:
                    placed = False
                    for group in range(1, amount_of_groups + 1):
                        if group not in assigned_groups and can_place_in_group(participant, group):
                            groups[group].append(participant)
                            assigned_groups.add(group)
                            snapshot_delta("add", group, participant)
                            logging.debug(f"Added {participant} to group {group}")
                            placed = True
                            break

                    if not placed:
                        for group in range(1, amount_of_groups + 1):
                            if group not in assigned_groups and can_place_in_group_no_base_conflict(participant, group):
                                groups[group].append(participant)
                                assigned_groups.add(group)
                                snapshot_delta("add", group, participant)
                                logging.debug(f"Added {participant} to group {group}")
                                placed = True
                                break

                    if not placed:
                        participants_to_assign_randomly.append(participant)

                for participant in participants_to_assign_randomly:
                    available_groups = list(all_groups - assigned_groups)
                    random_group = random.choice(available_groups)
                    groups[random_group].append(participant)
                    assigned_groups.add(random_group)
                    snapshot_delta("add", random_group, participant)
                    logging.debug(f"Randomly assigned {participant} to group {random_group}")

        # Return both groups and the delta snapshots
        return groups, snapshots