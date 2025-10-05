"""Module for writing output data to CSV files."""
import csv
from types import SimpleNamespace
from models.player import players_by_start_number
from misc.config import config

def prepare_export_from_group_draw(groups):
    """Prepare export data from group draw data."""
    export = []

    for _, competition_classes in groups.items():
        for _, items in sorted(competition_classes.items()):
            for group_number, members in items["group"].items():
               for member in members:
                    player_a = players_by_start_number[member.start_number_a]
                    player_b = players_by_start_number[member.start_number_b] if member.start_number_b is not None else None

                    export_line_to_add = SimpleNamespace()
                    export_line_to_add.S_D_M = member.competition
                    setattr(export_line_to_add, "class", member.competition_class)                    
                    export_line_to_add.seeding = member.seeding
                    export_line_to_add.group_no = group_number
                    export_line_to_add.group_pos = None
                    export_line_to_add.for_main_round = None
                    export_line_to_add.for_consolation = None
                    export_line_to_add.draw_number = None
                    export_line_to_add.startnumber_A = member.start_number_a
                    export_line_to_add.startnumber_B = member.start_number_b if member.start_number_b is not None else ''
                    export_line_to_add.last_name_A = player_a.last_name
                    export_line_to_add.last_name_B = player_b.last_name if player_b is not None else ''
                    export_line_to_add.country_A = player_a.country
                    export_line_to_add.country_B = player_b.country if player_b is not None else ''
                    export_line_to_add.PPP_chapter_A = player_a.base
                    export_line_to_add.PPP_chapter_B = player_b.base if player_b is not None else ''


                    export.append(export_line_to_add)

    return export

def prepare_export_from_bracket_draw(draw_data):
    """Prepare export data from bracket draw data."""
    return

def write_to_csv(draw_data):
    """Write the provided draw data to a CSV file."""
    headers = ["S_D_M","class","seeding","group_no","group_pos","for_main_round","for_consolation","draw_number","startnumber_A","last_name_A","country_A","PPP_chapter_A","startnumber_B","last_name_B","country_B","PPP_chapter_B"]
    output_file_path = config["files"]["output_file_path"]
    with open(output_file_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers, delimiter=';')
        writer.writeheader()

        for line in draw_data:
            row_dict = vars(line)  # convert SimpleNamespace → dict
            writer.writerow(row_dict)