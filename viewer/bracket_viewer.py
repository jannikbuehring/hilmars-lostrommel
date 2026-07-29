"""Module for viewing brackets in either interactive or table mode."""
import os
import webbrowser
from pathlib import Path
import inquirer
from tabulate import tabulate
from viewer.view_config import table_format
from models.player import players_by_start_number
from misc.config import config

_GREEN = "\033[92m"
_RESET = "\033[0m"


def clear_screen():
    """Clear the terminal screen in a cross-platform way."""
    os.system("cls" if os.name == "nt" else "clear")


def _open_in_browser(path):
    """Open an exported HTML file in the default browser (best-effort)."""
    try:
        webbrowser.open(Path(path).resolve().as_uri())
    except Exception as exc:  # pragma: no cover - depends on desktop environment
        print(f"Could not open {path} automatically: {exc}")


def show_bracket(competition, competition_class, bracket):
    """Choose a bracket type, then view it (table/interactive) or export it to HTML."""
    if not bracket or ('main' not in bracket and 'consolation' not in bracket):
        print("No bracket information available for this competition class.")
        return

    bracket_types = [
        k
        for k in ('main', 'consolation')
        if bracket.get(k) and (bracket[k].get('matches') or bracket[k].get('snapshots'))
    ]
    if not bracket_types:
        print("No bracket matches available to display.")
        return

    if len(bracket_types) == 1:
        bracket_type = bracket_types[0]
    else:
        choice = inquirer.list_input(
            "Choose bracket type", choices=[bt.capitalize() for bt in bracket_types])
        bracket_type = choice.lower()

    # Restrict the downstream viewers/exporter to the single chosen bracket type.
    single = {bracket_type: bracket[bracket_type]}

    action = inquirer.list_input("Bracket view", choices=["View", "View HTML", "Back"])
    if action == "Back":
        return
    if action == "View HTML":
        # Imported lazily to avoid a circular import (bracket_html_exporter reuses
        # participant_display_fields from this module).
        from viewer.bracket_html_exporter import bracket_html_path, export_bracket_html
        output_dir = config["files"].get("bracket_html_output_dir", "output/brackets")
        # Brackets are pre-exported during initialization; open the existing file.
        path = bracket_html_path(competition, competition_class, bracket_type, output_dir)
        if os.path.exists(path):
            _open_in_browser(path)
        else:
            # Fallback: export on demand if the pre-exported file is missing.
            paths = export_bracket_html(competition, competition_class, single, output_dir)
            if paths:
                for p in paths:
                    _open_in_browser(p)
            else:
                print("No bracket matches available to display.")
        return

    mode = config["settings"].get("mode", "table")
    if mode == 'interactive':
        show_bracket_menu(competition, competition_class, single)
    else:
        show_bracket_tables(competition, competition_class, single)


def show_bracket_menu(competition, competition_class, bracket):
    """Interactive bracket viewer: choose main or consolation bracket and step through snapshots."""
    bracket_types = [
        k
        for k in ('main', 'consolation')
        if bracket.get(k) and (bracket[k].get('matches') or bracket[k].get('snapshots'))
    ]
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


def participant_display_fields(p):
    """Extract structured display data for a participant.

    Returns None for an empty slot, the string "BYE" for a bye, the string
    "ERR" if extraction failed, or a dict:
      {"seeding": int|None, "group_no": int|None, "group_pos": int|None,
       "names": [{"first_name", "last_name", "start_number", "country", "base"}, ...]}
    "names" has one entry for a single player, two for a team. If a player
    can't be resolved via players_by_start_number, its entry is instead
    {"unknown": start_number}.
    Consumed by both format_participant_display (terminal) and the HTML
    exporter, so both renderers stay in sync with a single source of truth.
    """
    if p is None:
        return None
    if p == "BYE":
        return "BYE"

    try:
        names = []
        for start_number in (p.start_number_a, getattr(p, 'start_number_b', None)):
            if start_number is None:
                continue
            pl = players_by_start_number.get(start_number)
            if pl is None:
                names.append({"unknown": start_number})
            else:
                names.append({
                    "first_name": pl.first_name,
                    "last_name": pl.last_name,
                    "start_number": pl.start_number,
                    "country": pl.country,
                    "base": pl.base,
                })

        return {
            "seeding": getattr(p, 'seeding', None),
            "group_no": getattr(p, 'group_no', None),
            "group_pos": getattr(p, 'group_pos', None),
            "names": names,
        }
    except Exception:
        return "ERR"


def format_participant_display(p):
    """Format a single participant with metadata for vertical display.

    Format: seed:{N} | G:{group_no} | gp:{group_pos} | name [country/base] (for teams: PlayerA / PlayerB [country/base])
    Returns a single formatted string, or 'BYE' for bye matches.
    """
    fields = participant_display_fields(p)
    if fields is None:
        return "-"
    if fields in ("BYE", "ERR"):
        return fields

    names = fields["names"]
    if len(names) < 2:
        # Single player.
        name = names[0]
        if "unknown" in name:
            return f"Unknown({name['unknown']})"
        player_name = f"{name['last_name']} ({name['start_number']}) [{name['country']}/{name['base'] if name['base'] else '-'}]"
    else:
        # Team: format as "PlayerA [country/base] / PlayerB [country/base]"
        pa, pb = names
        if "unknown" not in pa and "unknown" not in pb:
            player_name = (
                f"{pa['last_name']} ({pa['start_number']}) [{pa['country']}/{pa['base'] if pa['base'] else '-'}] / "
                f"{pb['last_name']} ({pb['start_number']}) [{pb['country']}/{pb['base'] if pb['base'] else '-'}]"
            )
        else:
            player_name = f"{p.start_number_a} / {p.start_number_b}"

    meta_parts = []
    if fields["seeding"] is not None:
        meta_parts.append(f"seed:{fields['seeding']}")
    if fields["group_no"] is not None:
        meta_parts.append(f"G:{fields['group_no']}")
    if fields["group_pos"] is not None:
        meta_parts.append(f"gp:{fields['group_pos']}")

    if meta_parts:
        return " | ".join(meta_parts) + " | " + player_name
    else:
        return player_name


def _get_top_quarter_ids(first_round_matches):
    """Return set of id()s for participants in the top quarter of the bracket.

    Ranking: group_pos ascending (1 = group winner is best), seeding descending (higher = better).
    Top quarter = total bracket slots // 4 best participants.
    """
    all_participants = []
    for participants in first_round_matches.values():
        for p in participants:
            if p is not None and p != "BYE":
                all_participants.append(p)

    total_slots = len(first_round_matches) * 2
    top_count = total_slots // 4

    def sort_key(p):
        gp = getattr(p, 'group_pos', None)
        seed = getattr(p, 'seeding', None)
        return (gp if gp is not None else 999, -(seed if seed is not None else 0))

    sorted_participants = sorted(all_participants, key=sort_key)
    return set(id(p) for p in sorted_participants[:top_count])


def show_bracket_table(first_round_matches, title=None):
    """
    Display bracket table with participants stacked vertically and separators between matches.
    first_round_matches: dict mapping round match index to participant list.
    The best quarter of players (by group placement then seed) is highlighted in green.
    """
    if title:
        print(title)
    table_data = []

    top_quarter_ids = _get_top_quarter_ids(first_round_matches)
    # Map plain display string -> needs green highlight (collect before building table)
    highlighted_strings = set()

    items = list(first_round_matches.items())
    for i, (match_idx, participants) in enumerate(items):
        a = participants[0] if len(participants) > 0 else None
        b = participants[1] if len(participants) > 1 else None

        # Ensure BYE is listed second for easier reading
        if a == 'BYE' and b != 'BYE':
            a, b = b, a

        # Format both participants (plain strings for correct tabulate alignment)
        formatted_a = format_participant_display(a)
        formatted_b = format_participant_display(b)

        if a is not None and a != "BYE" and id(a) in top_quarter_ids:
            highlighted_strings.add(formatted_a)
        if b is not None and b != "BYE" and id(b) in top_quarter_ids:
            highlighted_strings.add(formatted_b)

        # Add first participant row with position number
        pos_a = i * 2 + 1
        pos_b = i * 2 + 2
        table_data.append([pos_a, formatted_a])

        # Add second participant row
        table_data.append([pos_b, formatted_b])

        # Add filled separator line between matches (unless it's the last match)
        if i < len(items) - 1:
            table_data.append(["", "─" * 80])

    try:
        output = tabulate(table_data, headers=["Pos.", "Participant"], tablefmt=table_format, colalign=("right", "left"))
    except UnicodeEncodeError:
        output = tabulate(table_data, headers=["Pos.", "Participant"], tablefmt='simple', colalign=("right", "left"))

    # Post-process: wrap highlighted participant strings in green ANSI codes
    for s in highlighted_strings:
        output = output.replace(s, _GREEN + s + _RESET)

    print(output)
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
