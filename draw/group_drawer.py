from tabulate import tabulate
import math
import random
from models.player import Player
from models.draw_data import DrawData

random.seed(1000)

class GroupDrawer:
    def __init__(self, players):
        self.players = players

    def draw_groups(self, class_subset: DrawData, group_size):
        def can_place_in_group(player, group):
            if len(groups[group]) >= group_size:
                return False
            # Check if any player in the group is from the same country
            for p in groups[group]:
                if p.country == player.country:
                    return False
            return True

        def can_place_in_group_no_base_conflict(player, group):
            for p in groups[group]:
                if p.base == player.base:
                    return False
            return True

        def backtrack(batch, index, assigned_groups):
            if index >= len(batch):
                return True  # All players placed successfully

            player = batch[index]

            # Try to place the player in each available group
            for group in range(1, number_of_groups + 1):
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

        players.sort(key=lambda p: p.rank)
        number_of_groups = math.ceil(len(players) / group_size)
        groups = {i + 1: [] for i in range(int(number_of_groups))}

        # Assign players to groups in batches of size equal to the number of groups
        for i in range(0, len(players), number_of_groups):
            batch = players[i:i + number_of_groups]  # Get the current batch
            all_groups = set(range(1, number_of_groups + 1))
            assigned_groups = set()  # Track assigned groups for this batch

            # Try to place players in this batch using backtracking
            if not backtrack(batch, 0, assigned_groups):
                print("Failed to place all players in the current batch")

                players_to_assign_randomly = []
                # If backtracking fails, randomly assign players
                for player in batch:
                    placed = False
                    for group in range(1, number_of_groups + 1):
                        if group not in assigned_groups and can_place_in_group(player, group):
                            groups[group].append(player)
                            assigned_groups.add(group)
                            placed = True
                            break

                    if not placed:
                        for group in range(1, number_of_groups + 1):
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
                    print(f"Could not place player {player} in a group. Randomly assigned to group {random_group}.")
                    groups[random_group].append(player)
                    assigned_groups.add(random_group)

        print_groups(groups)
        return groups

    def print_groups(groups):
        # Prepare a table for each group
        for group, members in groups.items():
            print(f"\nGroup {group}")

            # Prepare rows for the table
            table_data = []
            for player in members:
                table_data.append([player.rank, player.player_number, player.country, player.base])

            # Print the table using tabulate
            print(tabulate(table_data, headers=["Rank", "Player Number", "Country", "Base"], tablefmt="grid"))