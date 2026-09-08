"""Module for viewing groups and snapshots in either interactive or table mode."""
import os
import inquirer
from tabulate import tabulate
from viewer.view_config import table_format
from viewer.viewer_shared import clear_screen, open_in_browser
from viewer.group_html_exporter import export_group_html, group_html_path
from models.player import players_by_start_number
from misc.config import config
from draw.group_drawer import EmptySlot


def show_groups(competition, competition_class, groups, snapshots):
    """Choose how to view a class's groups: terminal (table/interactive) or HTML."""
    action = inquirer.list_input("Group view", choices=["View", "View HTML", "Back"])
    if action == "Back":
        return
    if action == "View HTML":
        output_dir = config["files"].get("group_html_output_dir", "output/groups")
        # Groups are pre-exported during initialization; open the existing file.
        path = group_html_path(competition, competition_class, output_dir)
        if not os.path.exists(path):
            # Fallback: export on demand if the pre-exported file is missing.
            path = export_group_html(
                competition, competition_class, groups, snapshots, output_dir)
        if path:
            open_in_browser(path)
        else:
            print("No group draw available to display.")
        return

    mode = config["settings"].get("mode", "table")
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
            if isinstance(participant, EmptySlot):
                continue

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
                if snapshots[next_index].violation_score < snapshots[current_index].violation_score:
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
    print(f"Snapshot {index + 1}/{len(snapshots)}")
    if index > 0:
        print(f"Action: {snap.action}")
        print(f"{snap.participants[0]} has been swapped to group {snap.groups[1] if snap.action == 'swap' else snap.groups[0]}")
        print(f"{snap.participants[1]} has been swapped to group {snap.groups[0] if snap.action == 'swap' else snap.groups[1]}")
    else:
        print("Initial group assignment (no snapshots applied)")
    print(f"Violation score: {snap.violation_score}")
    for violation_name, violations in snap.violations.items():
        print(f"{violation_name} violations: {violations}")
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