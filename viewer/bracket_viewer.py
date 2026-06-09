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
        bracket_type = inquirer.list_input(
            "Choose bracket type to view", choices=bracket_types)

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


def show_bracket_table(first_round_matches, title=None):
    """
    first_round_matches: dict mapping round match index to participant list.
    """
    if title:
        print(title)
    table_data = []

    def participant_lines(p):
        """Return a list of display lines for a participant (single or team).
        For teams, returns two lines (partner A then partner B). For BYE, returns ['BYE'].
        """
        if p is None:
            return ["-"]
        if p == "BYE":
            return ["BYE"]
        try:
            group_info = f" G:{getattr(p, 'group_no', getattr(p, 'group_no', None))}" if getattr(p, 'group_no', None) is not None else ""
            if getattr(p, 'start_number_b', None) is None:
                pl = players_by_start_number.get(p.start_number_a)
                if pl is None:
                    return [f"Unknown({p.start_number_a}){group_info}"]
                meta = []
                if getattr(p, 'seeding', None) is not None:
                    meta.append(f"seed:{p.seeding}")
                if getattr(p, 'group_pos', None) is not None:
                    meta.append(f"gp:{p.group_pos}")
                meta_s = " (" + ",".join(meta) + ")" if meta else ""
                return [f"{pl.last_name} ({pl.start_number}) [{pl.country}/{pl.base if pl.base else '-'}]{meta_s}{group_info}"]
            else:
                pa = players_by_start_number.get(p.start_number_a)
                pb = players_by_start_number.get(p.start_number_b)
                if pa and pb:
                    line_a = f"{pa.last_name} ({pa.start_number}) [{pa.country}/{pa.base if pa.base else '-'}]"
                    line_b = f"{pb.last_name} ({pb.start_number}) [{pb.country}/{pb.base if pb.base else '-'}]"
                else:
                    line_a = f"{p.start_number_a}"
                    line_b = f"{p.start_number_b}"
                meta = []
                if getattr(p, 'seeding', None) is not None:
                    meta.append(f"seed:{p.seeding}")
                if getattr(p, 'group_pos', None) is not None:
                    meta.append(f"gp:{p.group_pos}")
                meta_s = " (" + ",".join(meta) + ")" if meta else ""
                # append group info to first line
                return [f"{line_a}{meta_s} G:{p.group_no if getattr(p, 'group_no', None) is not None else ''}", f"{line_b}"]
        except Exception:
            return ["ERR"]

    items = list(first_round_matches.items())
    for i, (match_idx, participants) in enumerate(items):
        a = participants[0] if len(participants) > 0 else None
        b = participants[1] if len(participants) > 1 else None

        # Ensure BYE is listed second (on the B side) for easier reading
        if a == 'BYE' and b != 'BYE':
            a, b = b, a

        lines_a = participant_lines(a)
        lines_b = participant_lines(b)

        # If one side is BYE and the other is multi-line, put BYE on the bottom line
        if lines_a and lines_a[0] == 'BYE' and len(lines_b) > 1:
            # represent BYE as ['','BYE'] to push it to second line
            lines_a = [''] * (len(lines_b) - 1) + ['BYE']
        if lines_b and lines_b[0] == 'BYE' and len(lines_a) > 1:
            lines_b = [''] * (len(lines_a) - 1) + ['BYE']

        nrows = max(len(lines_a), len(lines_b))
        for r in range(nrows):
            row = [
                match_idx if r == 0 else "",
                lines_a[r] if r < len(lines_a) else "",
                "vs" if r == 0 else "",
                lines_b[r] if r < len(lines_b) else "",
                "YES" if ((a == 'BYE' or b == 'BYE') and r == 0) else ""
            ]
            table_data.append(row)

        # insert a dotted separator row between matches for visual clarity
        if i < len(items) - 1:
            sep = ['', '.' * 12, '', '.' * 12, '']
            table_data.append(sep)

    try:
        print(tabulate(table_data, headers=["Match", "A", "", "B", "BYE"], tablefmt=table_format))
    except UnicodeEncodeError:
        print(tabulate(table_data, headers=["Match", "A", "", "B", "BYE"], tablefmt='simple'))
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
