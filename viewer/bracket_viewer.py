"""Module for viewing brackets in either interactive or table mode."""
from tabulate import tabulate
from viewer.view_config import table_format
from models.player import players_by_start_number
from misc.config import config

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

    table_data = []

    for idx, match in first_round_matches.items():
        for i, participant in enumerate(match):
            if participant != "BYE" and participant.start_number_b is None:
                player = players_by_start_number.get(participant.start_number_a)
                table_data.append([
                    idx*2 + i - 1,
                    player.last_name,
                    player.start_number,
                    player.country,
                    player.base
                ])
            elif participant != "BYE" and participant.start_number_b is not None:
                player_a = players_by_start_number.get(participant.start_number_a)
                player_b = players_by_start_number.get(participant.start_number_b)
                table_data.append([
                    idx*2 + i - 1,
                    f"{player_a.last_name} / {player_b.last_name}",
                    f"{player_a.start_number} / {player_b.start_number}",
                    f"{player_a.country} / {player_b.country}",
                    f"{player_a.base} / {player_b.base}"
                ])
            else:
                table_data.append([
                    idx*2 + i -1,
                    "-",
                    "-",
                    "-",
                    "-"
                ])


    print(tabulate(table_data, headers=["#", "Last Name", "Start Number", "Country", "Base"], tablefmt=table_format))

    print("")