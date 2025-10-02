"""Module for viewing groups and snapshots in either interactive or table mode."""
import os
import inquirer
from tabulate import tabulate
from viewer.view_config import table_format
from models.player import players_by_start_number
from misc.config import config
from draw.group_drawer import EmptySlot

def clear_screen():
    """Clear the terminal screen in a cross-platform way."""
    os.system("cls" if os.name == "nt" else "clear")


def show_groups(competition, competition_class, groups, snapshots):
    """Display groups in either interactive or table mode."""
    mode = config["settings"]["mode"]
    if mode == 'interactive':
        show_snapshot_viewer(competition, competition_class, snapshots)
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
            if isinstance(member, EmptySlot):
                continue
            else:
                player = players_by_start_number[member.start_number_a]
                table_data.append([
                    idx + 1,
                    member.seeding,
                    player.last_name,
                    player.first_name,
                    player.start_number,
                    player.country,
                    f"{player.base}",
                    player.qttr
                ])
        print(tabulate(table_data, headers=["#", "Seeding", "Last Name                  ", "First Name               ",
                                            "Start Number", "Country           ", "Base                   ", "QTTR"], tablefmt=table_format))
    else:
        # Team group
        for idx, participant in enumerate(group):
            player_a = players_by_start_number[participant.start_number_a]
            player_b = players_by_start_number[participant.start_number_b]
            table_data.append([
                idx + 1,
                f"{participant.seeding}",
                f"{player_a.last_name}/{player_b.last_name}",
                f"{player_a.start_number}/{player_b.start_number}",
                f"{player_a.country}/{player_b.country}",
                f"{player_a.base}/{player_b.base}",
                f"{player_a.qttr}/{player_b.qttr}",
            ])
        print(tabulate(table_data, headers=["#", "Seeding", "Last Names                                ", "Start Numbers",
                                            "Countries                      ", "Bases                                     ", "QTTR values    "], tablefmt=table_format))



def show_snapshot_viewer(competition, competition_class, snapshots):
    """Interactive viewer for group assignment snapshots."""
    current_index = 0
    last_action = "Forward"

    def is_batch_end(index):
        return bool(snapshots[index].get("batch_end", False))

    while True:
        clear_screen()
        print(f"Competition: {competition} | Class: {competition_class}")
        display_snapshot(snapshots, current_index)
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
        elif action == "Forward to next improvement":
            next_index = current_index + 1
            while next_index < len(snapshots):
                if snapshots[next_index].violation_count < snapshots[current_index].violation_count:
                    current_index = next_index
                    break
                next_index += 1
            else:
                print("No next improvement found.")
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

def display_snapshot(snapshots, index):
    """Display the current snapshot of group assignments."""
    # Start from initial_groups in snapshots[0]
    if not hasattr(snapshots[0], 'initial_groups') and not isinstance(snapshots[0].initial_groups, dict):
        print("Invalid snapshot format: missing initial_groups.")

    temp_groups = {g: list(members) for g, members in snapshots[0].initial_groups.items()}
    # Apply all actions up to the current index
    for i in range(1, index + 1):
        snap = snapshots[i]
        if hasattr(snap, 'action') and hasattr(snap, 'groups') and hasattr(snap, 'participants'):
            if snap.action == "swap":
                g1, g2 = snap.groups
                p1, p2 = snap.participants
                temp_groups[g1][snap.index], temp_groups[g2][snap.index] = p2, p1
            elif snap.action == "revert":
                g1, g2 = snap.groups
                p1, p2 = snap.participants
                temp_groups[g1][snap.index], temp_groups[g2][snap.index] = p1, p2
    # Display reconstructed groups
    for number, group in temp_groups.items():
        print(f"\nGroup {number}")
        print_group_table(group)
    print("")
    snap = snapshots[index]
    if index > 0:
        print(f"Snapshot {index + 1}/{len(snapshots)}")
        print(f"Action: {snap.action}")
        print(f"{snap.participants[0]} has been swapped to group {snap.groups[1] if snap.action == 'swap' else snap.groups[0]}")
        print(f"{snap.participants[1]} has been swapped to group {snap.groups[0] if snap.action == 'swap' else snap.groups[1]}")
        print(f"New violation count: {snap.violation_count}")
    else:
        print("Initial group assignment (no snapshots applied)")
        print(f"Violation count: {snap.violation_count}")

def prompt_snapshot_action(last_action):
    """Prompt the user for the next snapshot navigation action."""
    questions = [
        inquirer.List(
            "action",
            message="Select action",
            choices=[
                "Forward",
                "Backward",
                "Forward to next improvement",
                "Go to snapshot",
                "Show final groups",
                "Quit",
            ],
            default=last_action,
        )
    ]
    answer = inquirer.prompt(questions)
    return answer["action"]