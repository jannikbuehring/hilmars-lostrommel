import logging
from models.player import players_by_start_number
from models.player import players_list

def check_all_players_only_exist_once() -> set:
    """Check that all players only exist once in players_list and populate players_by_start_number."""
    wrongful_player_data = []
    for player in players_list:
        if player.start_number in players_by_start_number:
            wrongful_player_data.append(player.start_number)
        else:
            players_by_start_number[player.start_number] = player
    return set(wrongful_player_data)

def find_missing_players(draw_data) -> set:
    """Find players that are referenced in draw_data but not in players_by_start_number."""
    # collect both start_number_a and start_number_b from draw_data
    referenced_players = {
        num
        for d in draw_data
        for num in (d.start_number_a, d.start_number_b)
        if num is not None
    }

    # check missing players
    all_players = set(players_by_start_number.keys())
    missing_players = referenced_players - all_players
    return missing_players

def find_players_not_in_draw_data(draw_data) -> set:
    """Find players that are in players_by_start_number but not referenced in draw_data."""
    # collect both start_number_a and start_number_b from draw_data
    referenced_players = {
        num
        for d in draw_data
        for num in (d.start_number_a, d.start_number_b)
        if num is not None
    }

    all_players = set(players_by_start_number.keys())
    extra_references = referenced_players - all_players
    return extra_references


def find_players_in_wrong_competition(draw_data) -> list:
    """Check if all players are in the correct competition based on their gender."""
    female_players = set({start_number: player for start_number, player in players_by_start_number.items() if player.gender == 'F'})
    male_players = set({start_number: player for start_number, player in players_by_start_number.items() if player.gender == 'M'})

    female_competitions = [row for row in draw_data if 'W' in row.competition_class]
    male_competitions   = [row for row in draw_data if 'M' in row.competition_class]

    errors = []

    # --- Female competitions ---
    for row in female_competitions:
        for sn in (row.start_number_a, row.start_number_b):
            if sn is not None and sn not in female_players:
                errors.append(f"Start number {sn} in {row.competition_class} is not a female player")

    # --- Male competitions ---
    for row in male_competitions:
        for sn in (row.start_number_a, row.start_number_b):
            if sn is not None and sn not in male_players:
                errors.append(f"Start number {sn} in {row.competition_class} is not a male player")

    return errors
