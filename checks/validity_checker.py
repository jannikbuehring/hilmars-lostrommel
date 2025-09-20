import logging
from models.player import players_by_start_number

def find_missing_players(draw_data) -> set:
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