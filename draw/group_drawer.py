import math
import random
from models.player import Player
from models.player import players_by_start_number
from models.draw_data import DrawDataRow
import logging

class GroupDrawer:
    def __init__(self, players: list[Player]):
        self.players = players

    def draw_groups(self, class_subset: list[DrawDataRow], amount_of_groups):
        
        def can_place_in_group(participant, group):
            if len(groups[group]) >= max_group_size:
                return False
            
            # Player
            if participant.start_number_b == None:
                # Check if any player in the group is from the same country
                for player_already_in_group in groups[group]:
                    if players_by_start_number[player_already_in_group.start_number_a].country == players_by_start_number[participant.start_number_a].country:
                        logging.debug(f"Player {players_by_start_number[participant.start_number_a].start_number} has same country as someone in group {group}.")
                        return False
            # Team
            else:
                for team_already_in_group in groups[group]:
                    if (
                        players_by_start_number[team_already_in_group.start_number_a].country 
                        == players_by_start_number[participant.start_number_a].country 
                        and players_by_start_number[team_already_in_group.start_number_b].country 
                        == players_by_start_number[participant.start_number_b].country
                    ):
                        logging.debug(f"Team {players_by_start_number[participant.start_number_a].start_number}/{players_by_start_number[participant.start_number_b].start_number} has same country as someone in group {group}.")
                        return False
                
            return True

        def can_place_in_group_no_base_conflict(participant, group):

            # Player
            if participant.start_number_b == None:
                for player_already_in_group in groups[group]:
                    if players_by_start_number[player_already_in_group.start_number_a].base == players_by_start_number[participant.start_number_a].base:
                        logging.debug(f"Player {players_by_start_number[participant.start_number_a].start_number} has same base as someone in group {group}.")
                        return False
            # Team
            else:
                for team_already_in_group in groups[group]:
                    if (
                        players_by_start_number[team_already_in_group.start_number_a].base 
                        == players_by_start_number[participant.start_number_a].base 
                        and players_by_start_number[team_already_in_group.start_number_b].base 
                        == players_by_start_number[participant.start_number_b].base
                    ):
                        logging.debug(f"Team {players_by_start_number[participant.start_number_a].start_number}/{players_by_start_number[participant.start_number_b].start_number} has same base as someone in group {group}.")
                        return False

            return True

        def backtrack(batch, index, assigned_groups):
            if index >= len(batch):
                logging.debug(f"All players of batch {batch} placed successfully")
                return True  # All players placed successfully

            participant = batch[index]

            # Try to place the participant in each available group
            for group in range(1, amount_of_groups + 1):
                if group not in assigned_groups:
                    # Check for country conflict first
                    if can_place_in_group(participant, group):
                        groups[group].append(participant)
                        assigned_groups.add(group)

                        if backtrack(batch, index + 1, assigned_groups):
                            logging.debug(f"Added {participant} to group {group}")
                            return True
                        
                        # Undo the placement (backtrack)
                        groups[group].remove(participant)
                        assigned_groups.remove(group)

            return False  # No valid placement found for this configuration

        def max_group_size(num_participants: int, num_groups: int) -> int:
            if num_groups <= 0:
                raise ValueError("Number of groups must be positive")
            # ceiling division: if players don’t divide evenly, some groups get one extra
            return -(-num_participants // num_groups)

        class_subset.sort(key=lambda draw_data: draw_data.seeding, reverse=True)

        max_group_size = max_group_size(num_participants = len(class_subset), num_groups=amount_of_groups)

        # Create a group dict
        groups = {i + 1: [] for i in range(int(amount_of_groups))}

        # Assign players to groups in batches of size equal to the number of groups
        for i in range(0, len(class_subset), amount_of_groups):
            batch = class_subset[i:i + amount_of_groups]  # Get the current batch
            all_groups = set(range(1, amount_of_groups + 1))
            assigned_groups = set()  # Track assigned groups for this batch

            # Try to place players in this batch using backtracking
            if not backtrack(batch, 0, assigned_groups):
                logging.debug("Failed to place all players in the current batch")

                participants_to_assign_randomly = []
                # If backtracking fails, randomly assign players
                for participant in batch:
                    placed = False
                    for group in range(1, amount_of_groups + 1):
                        if group not in assigned_groups and can_place_in_group(participant, group):
                            groups[group].append(participant)
                            assigned_groups.add(group)
                            placed = True
                            break

                    if not placed:
                        for group in range(1, amount_of_groups + 1):
                            if group not in assigned_groups and can_place_in_group_no_base_conflict(participant, group):
                                groups[group].append(participant)
                                assigned_groups.add(group)
                                placed = True
                                break

                    if not placed:
                        participants_to_assign_randomly.append(participant)
                
                for participant in participants_to_assign_randomly:
                    # If no valid placement found, place randomly
                    available_groups = list(all_groups - assigned_groups)
                    random_group = random.choice(available_groups)
                    logging.debug(f"Could not place participant {players_by_start_number[participant.start_number_a]} in a group. Randomly assigned to group {random_group}.")
                    groups[random_group].append(participant)
                    assigned_groups.add(random_group)

        return groups