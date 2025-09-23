import os
import inquirer
from tabulate import tabulate
from viewer.view_config import table_format
from models.player import players_by_start_number
from hilmars_lostrommel import *

def clear_screen():
    """Cross-platform clear screen"""
    os.system("cls" if os.name == "nt" else "clear")

def show_groups(groups, snapshots):
    if mode == 'interactive':
        show_snapshot_viewer(groups, snapshots)
    else: 
        show_groups_table(groups)

def show_groups_table(groups):
    for number, group in groups.items():
        table_data = []

        print(f"Group {number}")

        # Single Group
        if group[0].start_number_b == None:
            for index, member in enumerate(group):
                player = players_by_start_number[member.start_number_a]
                table_data.append([index + 1, member.seeding, player.first_name, player.last_name, player.start_number, player.country, player.base])
            print(tabulate(table_data, headers=["#", "Seeding", "First Name", "Last Name", "Start Number", "Country", "Base"], tablefmt=table_format))
       # Team Group
        else:
            for index, participant in enumerate(group):
                player_a = players_by_start_number[participant.start_number_a]
                player_b = players_by_start_number[participant.start_number_b]
                table_data.append([index + 1, participant.seeding, player_a.last_name + "/" + player_b.last_name, str(player_a.start_number) + "/" + str(player_b.start_number), player_a.country + "/" + player_b.country, str(player_a.base) + "/" + str(player_b.base)])
            print(tabulate(table_data, headers=["#", "Seeding", "Last Names", "Start Numbers", "Countries", "Bases"], tablefmt=table_format))

    print("")


def show_snapshot_viewer(groups, snapshots):
    current_index = 0

    def display_snapshot(index):
        temp_groups = {g: [] for g in groups.keys()}
        for snap in snapshots[:index + 1]:
            g = snap["group"]
            if snap["action"] == "add":
                temp_groups[g].append(snap["participant"])
            elif snap["action"] == "remove":
                if snap["participant"] in temp_groups[g]:
                    temp_groups[g].remove(snap["participant"])

        # Clear the terminal before displaying
        clear_screen()

        for number, group in temp_groups.items():
            table_data = []
            print(f"\nGroup {number}")
            if not group:
                print("[Empty]")
                continue

            if group[0].start_number_b is None:
                # Single player group
                for idx, member in enumerate(group):
                    player = players_by_start_number[member.start_number_a]
                    table_data.append([
                        idx + 1,
                        member.seeding,
                        player.first_name,
                        player.last_name,
                        player.start_number,
                        player.country,
                        player.base,
                    ])
                print(tabulate(table_data, headers=["#", "Seeding", "First Name", "Last Name",
                                                    "Start Number", "Country", "Base"], tablefmt=table_format))
            else:
                # Team group
                for idx, participant in enumerate(group):
                    player_a = players_by_start_number[participant.start_number_a]
                    player_b = players_by_start_number[participant.start_number_b]
                    table_data.append([
                        idx + 1,
                        participant.seeding,
                        f"{player_a.last_name}/{player_b.last_name}",
                        f"{player_a.start_number}/{player_b.start_number}",
                        f"{player_a.country}/{player_b.country}",
                        f"{player_a.base}/{player_b.base}",
                    ])
                print(tabulate(table_data, headers=["#", "Seeding", "Last Names", "Start Numbers",
                                                    "Countries", "Bases"], tablefmt=table_format))

        print("")
        action = 'Added to' if snapshots[index]["action"] == 'add' else 'Removed from'
        player_a = players_by_start_number[snapshots[index]['participant'].start_number_a]
        player_b = players_by_start_number[snapshots[index]['participant'].start_number_b] if snapshots[index]['participant'].start_number_b != None else None
        if player_b == None:
            print(f"{action} group {snapshots[index]['group']}: {player_a}")
        else:
            print(f"{action} group {snapshots[index]['group']}: {player_a} / {player_b}")
        print(f"\nSnapshot {index + 1}/{len(snapshots)}")

    last_action = "Forward"  # start with "Forward" as default

    while True:
        display_snapshot(current_index)

        # Prompt user with menu, defaulting to last action
        questions = [
            inquirer.List(
                "action",
                message="Select action",
                choices=["Forward", "Backward", "Go to snapshot", "Quit"],
                default=last_action
            )
        ]
        answer = inquirer.prompt(questions)
        action = answer["action"]

        if action == "Forward":
            if current_index + 1 < len(snapshots):
                current_index += 1
            else:
                print("Already at last snapshot.")
        elif action == "Backward":
            if current_index > 0:
                current_index -= 1
            else:
                print("Already at first snapshot.")
        elif action == "Go to snapshot":
            snapshot_number = inquirer.text(message=f"Enter snapshot number (1–{len(snapshots)}):")
            try:
                num = int(snapshot_number)
                if 1 <= num <= len(snapshots):
                    current_index = num - 1
                else:
                    print("Invalid snapshot number.")
            except ValueError:
                print("Please enter a valid integer.")
        elif action == "Quit":
            break

        # remember this action for next loop
        last_action = action