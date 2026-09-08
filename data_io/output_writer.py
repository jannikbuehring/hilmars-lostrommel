"""Module for writing output data to CSV files."""
import csv
import os
from types import SimpleNamespace
from models.player import players_by_start_number
from misc.config import config

HEADERS = ["S_D_M","class","seeding","group_no","group_pos","for_main_round","for_consolation","draw_number","startnumber_A","last_name_A","country_A","PPP_chapter_A","startnumber_B","last_name_B","country_B","PPP_chapter_B","is_bye"]

def _set_pair_fields(row, start_number_a, start_number_b):
    """Fill the eight A/B player columns on `row` from `players_by_start_number`.

    `start_number_b` is the doubles/mixed *partner* (None in singles), per
    `output/output_explainer.md` -- never the opponent. Unknown start numbers
    degrade to empty strings rather than raising, so a partially validated run
    still produces a readable file.
    """
    for suffix, start_number in (("A", start_number_a), ("B", start_number_b)):
        player = players_by_start_number.get(start_number) if start_number is not None else None
        setattr(row, f"startnumber_{suffix}", start_number if start_number is not None else '')
        setattr(row, f"last_name_{suffix}", player.last_name if player is not None else '')
        setattr(row, f"country_{suffix}", player.country if player is not None else '')
        setattr(row, f"PPP_chapter_{suffix}", player.base if player is not None else '')

def _clear_pair_fields(row):
    """Blank all eight A/B player columns (used for BYE slots)."""
    _set_pair_fields(row, None, None)

def _iter_bracket_slots(matches):
    """Yield (slot_number, participant_or_None) for every slot in Rasterzahl order.

    Inverse of `bracket_drawer.slot_to_match`: match `m` owns slots `2m-1` and
    `2m`. `slots_to_matches` can leave a match with 0 or 1 entries (partially
    drawn brackets), so missing sides are yielded as None -- the same padding
    `bracket_html_exporter._serialize_matches` applies.
    """
    for match_index in sorted(matches):
        participants = matches[match_index]
        for side in (0, 1):
            value = participants[side] if side < len(participants) else None
            yield 2 * match_index - 1 + side, value

def prepare_export_from_group_draw(groups):
    """Prepare export data from group draw data."""
    export = []

    for _, competition_classes in groups.items():
            for _, items in sorted(competition_classes.items()):
                for group_number, members in items["group"].items():
                    for member in members:
                        # group_drawer strips its EmptySlot placeholders before
                        # returning, so this only guards against a leak.
                        if member.start_number_a == "EMPTY":
                            continue

                        export_line_to_add = SimpleNamespace()
                        export_line_to_add.S_D_M = member.competition
                        setattr(export_line_to_add, "class", member.competition_class)
                        export_line_to_add.seeding = member.seeding
                        export_line_to_add.group_no = group_number
                        export_line_to_add.group_pos = None
                        export_line_to_add.for_main_round = None
                        export_line_to_add.for_consolation = None
                        export_line_to_add.draw_number = None
                        export_line_to_add.is_bye = ''
                        _set_pair_fields(export_line_to_add, member.start_number_a, member.start_number_b)

                        export.append(export_line_to_add)

    return export

def prepare_export_from_bracket_draw(draw_data):
    """Prepare export data from bracket draw data.

    `draw_data` expected format:
      { 'S': { competition_class: {'main': {'matches': matches_dict, ...}, 'consolation': {'matches': matches_dict, ...}}, ... }, 'D': {...}, 'M': {...} }

    One row per bracket *slot*, not per match: `draw_number` is the Rasterzahl
    of the KO field (1..bracket_size, ascending), and the A/B columns carry the
    two players of that slot's pair.

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
                for draw_number, participant in _iter_bracket_slots(matches):
                    if participant is None:
                        # Slot never filled (bracket abandoned mid-draw).
                        continue

                    export_line = SimpleNamespace()
                    export_line.S_D_M = comp_type
                    setattr(export_line, "class", competition_class)
                    export_line.for_main_round = bracket_type == 'main'
                    export_line.for_consolation = bracket_type == 'consolation'
                    export_line.draw_number = draw_number

                    if participant == "BYE":
                        export_line.seeding = ''
                        export_line.group_no = ''
                        export_line.group_pos = ''
                        export_line.is_bye = True
                        _clear_pair_fields(export_line)
                    else:
                        export_line.seeding = getattr(participant, 'seeding', '')
                        export_line.group_no = getattr(participant, 'group_no', '')
                        export_line.group_pos = getattr(participant, 'group_pos', '')
                        export_line.is_bye = False
                        _set_pair_fields(export_line, participant.start_number_a, participant.start_number_b)

                    export.append(export_line)

    return export

def write_to_csv(draw_data):
    """Write the provided draw data to a CSV file and return the path written."""
    output_file_path = config["files"]["output_file_path"]
    output_dir = os.path.dirname(output_file_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # utf-8-sig so the German names survive a double-click into Excel, matching
    # the BOM the input files are written with.
    with open(output_file_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS, delimiter=';')
        writer.writeheader()

        for line in draw_data:
            row_dict = vars(line)  # convert SimpleNamespace → dict
            writer.writerow(row_dict)

    return output_file_path
