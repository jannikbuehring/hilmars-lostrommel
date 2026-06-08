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
    """Prepare export data from bracket draw data.

    `draw_data` expected format:
      { 'S': { competition_class: {'main': {'matches': matches_dict, ...}, 'consolation': {'matches': matches_dict, ...}}, ... }, 'D': {...}, 'M': {...} }

    Returns a list of SimpleNamespace objects compatible with `write_to_csv`.
    """
    export = []
    for comp_type, classes in draw_data.items():
        for competition_class, bracket_payload in classes.items():
            for bracket_type in ('main', 'consolation'):
                section = bracket_payload.get(bracket_type)
                if not section:
                    continue
                matches = section.get('matches') if isinstance(section, dict) else section
                if not matches:
                    continue
                for draw_number, participants in matches.items():
                    if len(participants) == 0:
                        continue
                    a = participants[0]
                    b = participants[1] if len(participants) > 1 else None

                    export_line = SimpleNamespace()
                    export_line.S_D_M = comp_type
                    setattr(export_line, "class", competition_class)
                    export_line.seeding = getattr(a, 'seeding', '')
                    export_line.group_no = getattr(a, 'group_no', '')
                    export_line.group_pos = getattr(a, 'group_pos', '')
                    export_line.for_main_round = True if bracket_type == 'main' else False
                    export_line.for_consolation = True if bracket_type == 'consolation' else False
                    export_line.draw_number = draw_number

                    if a == "BYE":
                        export_line.startnumber_A = ''
                        export_line.last_name_A = ''
                        export_line.country_A = ''
                        export_line.PPP_chapter_A = ''
                    else:
                        player_a = players_by_start_number.get(a.start_number_a)
                        export_line.startnumber_A = a.start_number_a
                        export_line.last_name_A = player_a.last_name if player_a is not None else ''
                        export_line.country_A = player_a.country if player_a is not None else ''
                        export_line.PPP_chapter_A = player_a.base if player_a is not None else ''

                    if b is None or b == "BYE":
                        export_line.startnumber_B = ''
                        export_line.last_name_B = ''
                        export_line.country_B = ''
                        export_line.PPP_chapter_B = ''
                    else:
                        player_b = players_by_start_number.get(b.start_number_a)
                        export_line.startnumber_B = b.start_number_a
                        export_line.last_name_B = player_b.last_name if player_b is not None else ''
                        export_line.country_B = player_b.country if player_b is not None else ''
                        export_line.PPP_chapter_B = player_b.base if player_b is not None else ''

                    # BYE marker: True if either side is BYE
                    export_line.is_bye = (a == 'BYE') or (b == 'BYE')

                    export.append(export_line)

    return export

def write_to_csv(draw_data):
    """Write the provided draw data to a CSV file."""
    headers = ["S_D_M","class","seeding","group_no","group_pos","for_main_round","for_consolation","draw_number","startnumber_A","last_name_A","country_A","PPP_chapter_A","startnumber_B","last_name_B","country_B","PPP_chapter_B","is_bye"]
    output_file_path = config["files"]["output_file_path"]
    with open(output_file_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers, delimiter=';')
        writer.writeheader()

        for line in draw_data:
            row_dict = vars(line)  # convert SimpleNamespace → dict
            writer.writerow(row_dict)