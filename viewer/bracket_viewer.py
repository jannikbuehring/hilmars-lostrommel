"""Module for viewing brackets in either interactive or table mode."""
import os
import inquirer
from tabulate import tabulate
from viewer.view_config import table_format
from models.player import players_by_start_number
from misc.config import config


def clear_screen():
    """Clear the terminal screen in a cross-platform way."""
    os.system("cls" if os.name == "nt" else "clear")


def show_bracket(competition, competition_class, bracket):
    """Display bracket information in either interactive or table mode."""
    if not bracket or ('main' not in bracket and 'consolation' not in bracket):
        print("No bracket information available for this competition class.")
        return

    mode = config["settings"].get("mode", "table")
    if mode == 'interactive':
        show_bracket_menu(competition, competition_class, bracket)
    else:
        show_bracket_tables(competition, competition_class, bracket)


def show_bracket_menu(competition, competition_class, bracket):
    """Interactive bracket viewer: choose main or consolation bracket and step through snapshots."""
    bracket_types = [k for k in ('main', 'consolation') if bracket.get(k) and bracket[k].get('matches')]
    if not bracket_types:
        print("No bracket matches available to display.")
        return

    if len(bracket_types) == 1:
        bracket_type = bracket_types[0]
    else:
        capitalized_choices = [bt.capitalize() for bt in bracket_types]
        bracket_type_choice = inquirer.list_input(
            "Choose bracket type to view", choices=capitalized_choices)
        bracket_type = bracket_type_choice.lower()

    selected = bracket[bracket_type]
    matches = selected.get('matches', {})
    snapshots = selected.get('snapshots', [])

    if not snapshots:
        print(f"Bracket '{bracket_type}' has no replay snapshots available.")
        show_bracket_table(matches, title=f"{competition} {competition_class} {bracket_type.capitalize()} Bracket")
        return

    current_index = 0
    last_action = "Forward"

    while True:
        clear_screen()
        print(f"Competition: {competition} | Class: {competition_class} | Bracket: {bracket_type.capitalize()}")
        display_bracket_snapshot(matches, snapshots, current_index)
        action = prompt_snapshot_action(last_action)

        if action == "Forward":
            if current_index + 1 < len(snapshots):
                current_index += 1
            else:
                print("Already at the last snapshot.")
        elif action == "Backward":
            if current_index > 0:
                current_index -= 1
            else:
                print("Already at the first snapshot.")
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
        elif action == "Show final bracket":
            current_index = len(snapshots) - 1
        elif action == "Quit":
            break
        last_action = action


def show_bracket_tables(competition, competition_class, bracket):
    """Print main and consolation bracket tables if available."""
    print(f"Competition: {competition} | Class: {competition_class}")
    if bracket.get('main') and bracket['main'].get('matches'):
        show_bracket_table(bracket['main']['matches'], title="Main Bracket")
    if bracket.get('consolation') and bracket['consolation'].get('matches'):
        show_bracket_table(bracket['consolation']['matches'], title="Consolation Bracket")


def format_participant_display(p):
    """Format a single participant with metadata for vertical display.
    
    Format: seed:{N} | G:{group_no} | gp:{group_pos} | name [country/base] (for teams: PlayerA / PlayerB [country/base])
    Returns a single formatted string, or 'BYE' for bye matches.
    """
    if p is None:
        return "-"
    if p == "BYE":
        return "BYE"
    
    try:
        # Get player information
        if getattr(p, 'start_number_b', None) is None:
            # Single player
            pl = players_by_start_number.get(p.start_number_a)
            if pl is None:
                return f"Unknown({p.start_number_a})"
            player_name = f"{pl.last_name} ({pl.start_number}) [{pl.country}/{pl.base if pl.base else '-'}]"
        else:
            # Team: format as "PlayerA [country/base] / PlayerB [country/base]"
            pa = players_by_start_number.get(p.start_number_a)
            pb = players_by_start_number.get(p.start_number_b)
            if pa and pb:
                player_name = f"{pa.last_name} ({pa.start_number}) [{pa.country}/{pa.base if pa.base else '-'}] / {pb.last_name} ({pb.start_number}) [{pb.country}/{pb.base if pb.base else '-'}]"
            else:
                player_name = f"{p.start_number_a} / {p.start_number_b}"
        
        # Build metadata prefix: seed | group | position
        meta_parts = []
        if getattr(p, 'seeding', None) is not None:
            meta_parts.append(f"seed:{p.seeding}")
        if getattr(p, 'group_no', None) is not None:
            meta_parts.append(f"G:{p.group_no}")
        if getattr(p, 'group_pos', None) is not None:
            meta_parts.append(f"gp:{p.group_pos}")
        
        if meta_parts:
            return " | ".join(meta_parts) + " | " + player_name
        else:
            return player_name
    except Exception:
        return "ERR"


def show_bracket_table(first_round_matches, title=None):
    """
    Display bracket table with participants stacked vertically and separators between matches.
    first_round_matches: dict mapping round match index to participant list.
    """
    if title:
        print(title)
    table_data = []

    items = list(first_round_matches.items())
    for i, (match_idx, participants) in enumerate(items):
        a = participants[0] if len(participants) > 0 else None
        b = participants[1] if len(participants) > 1 else None

        # Ensure BYE is listed second for easier reading
        if a == 'BYE' and b != 'BYE':
            a, b = b, a

        # Format both participants
        formatted_a = format_participant_display(a)
        formatted_b = format_participant_display(b)

        # Add first participant row with match index
        table_data.append([match_idx, formatted_a])
        
        # Add second participant row
        table_data.append(["", formatted_b])

        # Add filled separator line between matches (unless it's the last match)
        if i < len(items) - 1:
            table_data.append(["", "─" * 80])

    try:
        print(tabulate(table_data, headers=["Match", "Participant"], tablefmt=table_format))
    except UnicodeEncodeError:
        print(tabulate(table_data, headers=["Match", "Participant"], tablefmt='simple'))
    print()


def display_bracket_snapshot(matches, snapshots, index):
    """Display a snapshot for the current bracket assignment."""
    if index < 0 or index >= len(snapshots):
        print("Snapshot index out of range.")
        return

    snapshot = snapshots[index]
    print(f"Snapshot {index + 1}/{len(snapshots)}")
    if getattr(snapshot, 'action', None) is not None:
        print(f"Action: {snapshot.action}")
    if getattr(snapshot, 'groups', None) is not None:
        print(f"Metadata: {snapshot.groups}")
    print(f"Violation score: {snapshot.violation_score}")
    for name, violations in snapshot.violations.items():
        print(f"{name}: {violations}")
    print("")
    state = snapshot.initial_groups if hasattr(snapshot, 'initial_groups') else matches
    show_bracket_table(state, title="Bracket snapshot")
    print("")


def prompt_snapshot_action(last_action):
    questions = [
        inquirer.List(
            "action",
            message="Select action",
            choices=[
                "Forward",
                "Backward",
                "Forward to next improvement",
                "Go to snapshot",
                "Show final bracket",
                "Quit",
            ],
            default=last_action,
        )
    ]
    answer = inquirer.prompt(questions)
    return answer["action"]
