from tabulate import tabulate
from viewer.view_config import table_format
from models.player import players_by_start_number
from misc.initializer import config

def show_bracket(first_round_matches):
    """Display bracket in either interactive or table mode."""
    mode = config["settings"]["mode"]
    if mode == 'interactive':
        return
    else: 
        show_bracket_table(first_round_matches)

def show_bracket_table(first_round_matches):
    """
    first_round_matches: list of Match objects (entry point into the bracket tree).
    Walks round by round until final.
    """

    round_number = 1
    current_round = first_round_matches

    table_data = []

    for idx, match in enumerate(current_round, start=1):
        def format_participant(p):
            if p is None:
                return "-"
            if p == "BYE":
                return "BYE"

            # Single player
            if getattr(p, "start_number_b", None) is None:
                player = players_by_start_number[p.start_number_a]
                return f"[{p.seeding}] {player.first_name} {player.last_name} ({player.country}, {player.base})"
            # Team
            else:
                player_a = players_by_start_number[p.start_number_a]
                player_b = players_by_start_number[p.start_number_b]
                return f"[{p.seeding}] {player_a.last_name}/{player_b.last_name} ({player_a.country}/{player_b.country}, {player_a.base}/{player_b.base})"

        table_data.append([
            idx,
            format_participant(match.slot_a),
            "vs",
            format_participant(match.slot_b)
        ])

    print(tabulate(table_data, headers=["Match", "Player A", "", "Player B"], tablefmt=table_format))

    print("")