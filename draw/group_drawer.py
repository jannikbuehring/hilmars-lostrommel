import math
import random
from models.player import Player
from models.draw_data import DrawDataRow
import logging

random.seed(1000)

class GroupDrawer:
    def __init__(self, players: list[Player]):
        self.players = players

    def draw_groups(self, class_subset: list[DrawDataRow], amount_of_groups):
        def can_place_in_group(player_to_set, group):
            if len(groups[group]) >= max_group_size:
                return False
            # Check if any player in the group is from the same country
            for player_in_group in groups[group]:
                if players_by_start_number[player_in_group.start_number_a].country == players_by_start_number[player_to_set.start_number_a].country:
                    return False
            return True

        def can_place_in_group_no_base_conflict(player_to_set, group):
            for player_in_group in groups[group]:
                if players_by_start_number[player_in_group.start_number_a].base == players_by_start_number[player_to_set.start_number_a].base:
                    return False
            return True

        def backtrack(batch, index, assigned_groups):
            if index >= len(batch):
                return True  # All players placed successfully

            player = batch[index]

            # Try to place the player in each available group
            for group in range(1, amount_of_groups + 1):
                if group not in assigned_groups:
                    # Check for country conflict first
                    if can_place_in_group(player, group):
                        groups[group].append(player)
                        assigned_groups.add(group)

                        if backtrack(batch, index + 1, assigned_groups):
                            return True
                        
                        # Undo the placement (backtrack)
                        groups[group].remove(player)
                        assigned_groups.remove(group)

            return False  # No valid placement found for this configuration

        def max_group_size(num_players: int, num_groups: int) -> int:
            if num_groups <= 0:
                raise ValueError("Number of groups must be positive")
            # ceiling division: if players don’t divide evenly, some groups get one extra
            return -(-num_players // num_groups)

        players_by_start_number = {p.start_number: p for p in self.players}
        class_subset.sort(key=lambda draw_data: draw_data.seeding, reverse=True)

        max_group_size = max_group_size(num_players = len(class_subset), num_groups=amount_of_groups)
        groups = {i + 1: [] for i in range(int(amount_of_groups))}

        # Assign players to groups in batches of size equal to the number of groups
        for i in range(0, len(class_subset), amount_of_groups):
            batch = class_subset[i:i + amount_of_groups]  # Get the current batch
            all_groups = set(range(1, amount_of_groups + 1))
            assigned_groups = set()  # Track assigned groups for this batch

            # Try to place players in this batch using backtracking
            if not backtrack(batch, 0, assigned_groups):
                logging.debug("Failed to place all players in the current batch")

                players_to_assign_randomly = []
                # If backtracking fails, randomly assign players
                for player in batch:
                    placed = False
                    for group in range(1, amount_of_groups + 1):
                        if group not in assigned_groups and can_place_in_group(player, group):
                            groups[group].append(player)
                            assigned_groups.add(group)
                            placed = True
                            break

                    if not placed:
                        for group in range(1, amount_of_groups + 1):
                            if group not in assigned_groups and can_place_in_group_no_base_conflict(player, group):
                                groups[group].append(player)
                                assigned_groups.add(group)
                                placed = True
                                break

                    if not placed:
                        players_to_assign_randomly.append(player)
                
                for player in players_to_assign_randomly:
                    # If no valid placement found, place randomly
                    available_groups = list(all_groups - assigned_groups)
                    random_group = random.choice(available_groups)
                    logging.debug(f"Could not place player {players_by_start_number[player.start_number_a]} in a group. Randomly assigned to group {random_group}.")
                    groups[random_group].append(player)
                    assigned_groups.add(random_group)

        #print_groups(groups)
        return groups