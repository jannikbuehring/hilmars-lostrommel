"""Module for viewing groups and snapshots in either interactive or table mode."""
import os
import inquirer
from tabulate import tabulate
from viewer.view_config import table_format
from models.player import players_by_start_number
from misc.config import config

def clear_screen():
    """Clear the terminal screen in a cross-platform way."""
    os.system("cls" if os.name == "nt" else "clear")


def show_groups(competition, competition_class, groups, snapshots):
    """Display groups in either interactive or table mode."""
    mode = config["settings"]["mode"]
    if mode == 'interactive':
        show_snapshot_viewer(competition, competition_class, groups, snapshots)
    else:
        show_groups_table(competition, competition_class, groups)


def show_groups_table(competition, competition_class, groups):
    """Print all groups in a tabular format."""
    print(f"Competition: {competition} | Class: {competition_class}")
    for number, group in groups.items():
        print(f"Group {number}")
        print_group_table(group)
    print("")

def print_group_table(group):
    """Print a single group in a tabular format."""
    table_data = []
    if group[0].start_number_b is None:
        # Single player group
        for idx, member in enumerate(group):
            player = players_by_start_number[member.start_number_a]
            table_data.append([
                idx + 1,
                member.seeding,
                player.last_name,
                player.first_name,
                player.start_number,
                player.country,
                f"{player.base}",
            ])
        print(tabulate(table_data, headers=["#", "Seeding", "Last Name                  ", "First Name               ",
                                            "Start Number", "Country           ", "Base              "], tablefmt=table_format))
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
        print(tabulate(table_data, headers=["#", "Seeding", "Last Names                                ", "Start Numbers",
                                            "Countries                      ", "Bases                                   "], tablefmt=table_format))



def show_snapshot_viewer(competition, competition_class, groups, snapshots):
    """Interactive viewer for group assignment snapshots."""
    current_index = 0
    last_action = "Forward"

    def is_batch_end(index):
        return bool(snapshots[index].get("batch_end", False))

    while True:
        clear_screen()
        print(f"Competition: {competition} | Class: {competition_class}")
        display_snapshot(groups, snapshots, current_index)
        action = prompt_snapshot_action(last_action)

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
        elif action == "Forward to next batch":
            next_index = current_index + 1
            while next_index < len(snapshots):
                if is_batch_end(next_index):
                    current_index = next_index
                    break
                next_index += 1
            else:
                print("No further batch end found.")
        elif action == "Backward to previous batch":
            prev_index = current_index - 1
            found = False
            batch_indices = [i for i in range(prev_index, -1, -1) if is_batch_end(i)]
            if batch_indices:
                current_index = batch_indices[0]
                found = True
            if not found:
                print("No previous batch end found.")
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
        elif action == "Show final groups":
            current_index = len(snapshots) - 1
        elif action == "Quit":
            break
        last_action = action

def display_snapshot(groups, snapshots, index):
    """Display the current snapshot of group assignments."""
    temp_groups = {g: [] for g in groups.keys()}
    for snap in snapshots[:index + 1]:
        g = snap["group"]
        if snap["action"] == "add":
            temp_groups[g].append(snap["participant"])
        elif snap["action"] == "remove":
            if snap["participant"] in temp_groups[g]:
                temp_groups[g].remove(snap["participant"])

    for number, group in temp_groups.items():
        print(f"\nGroup {number}")
        if not group:
            print("[Empty]")
            continue
        print_group_table(group)

    print("")
    snap = snapshots[index]
    action = 'Added to' if snap["action"] == 'add' else 'Removed from'
    player_a = players_by_start_number[snap['participant'].start_number_a]
    player_b = players_by_start_number[snap['participant'].start_number_b] if snap['participant'].start_number_b is not None else None
    placement = snap.get("placement_method", "?")
    placement_msg = f" (method: {placement})" if placement else ""
    if player_b is None:
        print(f"{action} group {snap['group']}: {player_a}{placement_msg}")
    else:
        print(f"{action} group {snap['group']}: {player_a} / {player_b}{placement_msg}")
    print(f"\nSnapshot {index + 1}/{len(snapshots)}")

def prompt_snapshot_action(last_action):
    """Prompt the user for the next snapshot navigation action."""
    questions = [
        inquirer.List(
            "action",
            message="Select action",
            choices=[
                "Forward",
                "Backward",
                "Forward to next batch",
                "Backward to previous batch",
                "Go to snapshot",
                "Show final groups",
                "Quit",
            ],
            default=last_action,
        )
    ]
    answer = inquirer.prompt(questions)
    return answer["action"]