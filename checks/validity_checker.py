import logging
from collections import defaultdict
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
    unreferenced_players = all_players - referenced_players
    return unreferenced_players


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


def _entry_label(row) -> str:
    """Human-readable label of a draw data row for error messages."""
    entry = str(row.start_number_a)
    if row.start_number_b is not None:
        entry += f"/{row.start_number_b}"
    return f"{row.competition} {row.competition_class} entry {entry}"


def find_invalid_round_flags(draw_data) -> list:
    """Check that bracket rows go to exactly one bracket and group-stage rows to none."""
    errors = []
    for row in draw_data:
        flag_count = int(row.main_round) + int(row.consolation_round)
        if row.group_pos is not None and flag_count != 1:
            errors.append(f"{_entry_label(row)} must be flagged for exactly one of main round / consolation (has {flag_count})")
        elif row.group_pos is None and flag_count != 0:
            errors.append(f"{_entry_label(row)} has no group_pos but is flagged for a bracket")
    return errors


def find_group_no_pos_mismatch(draw_data) -> list:
    """Check that group_no and group_pos are either both set or both blank."""
    errors = []
    for row in draw_data:
        if (row.group_no is None) != (row.group_pos is None):
            errors.append(f"{_entry_label(row)} has group_no={row.group_no} but group_pos={row.group_pos}; both must be set or both blank")
    return errors


def find_duplicate_players_in_class(draw_data) -> list:
    """Check that no player appears more than once per competition class and stage."""
    seen = defaultdict(set)
    errors = []
    for row in draw_data:
        stage = "group stage" if row.group_pos is None else "bracket stage"
        key = (row.competition, row.competition_class, stage)
        for sn in (row.start_number_a, row.start_number_b):
            if sn is None:
                continue
            if sn in seen[key]:
                errors.append(f"Start number {sn} appears more than once in {row.competition} {row.competition_class} ({stage})")
            seen[key].add(sn)
    return errors


def find_duplicate_group_positions(draw_data) -> list:
    """Check that every group_pos is used only once per group in the bracket stage."""
    seen = set()
    errors = []
    for row in draw_data:
        if row.group_no is None or row.group_pos is None:
            continue
        key = (row.competition, row.competition_class, row.group_no, row.group_pos)
        if key in seen:
            errors.append(f"{row.competition} {row.competition_class} group {row.group_no} has group_pos {row.group_pos} more than once")
        seen.add(key)
    return errors


def find_invalid_pairs(draw_data) -> list:
    """Check that doubles/mixed rows have a partner, singles rows have none, and nobody is paired with themselves."""
    errors = []
    for row in draw_data:
        if row.competition in ('D', 'M') and row.start_number_b is None:
            errors.append(f"{_entry_label(row)} has no partner")
        elif row.competition == 'S' and row.start_number_b is not None:
            errors.append(f"{_entry_label(row)} is a singles entry with a partner")
        if row.start_number_a == row.start_number_b:
            errors.append(f"{_entry_label(row)} pairs a player with themselves")
    return errors


def find_invalid_mixed_pairs(draw_data) -> list:
    """Check that every mixed pair consists of one male and one female player."""
    errors = []
    for row in draw_data:
        if row.competition != 'M' or row.start_number_b is None:
            continue
        genders = sorted(players_by_start_number[sn].gender for sn in (row.start_number_a, row.start_number_b))
        if genders != ['F', 'M']:
            errors.append(f"{_entry_label(row)} is not a male/female pair (genders: {'/'.join(genders)})")
    return errors


def find_inconsistent_group_counts(draw_data) -> list:
    """Check that all group-stage rows of a competition class share one #groups value."""
    counts = defaultdict(set)
    for row in draw_data:
        if row.group_pos is None:
            counts[(row.competition, row.competition_class)].add(row.amount_of_groups)
    errors = []
    for (competition, competition_class), values in sorted(counts.items()):
        if None in values:
            errors.append(f"{competition} {competition_class} has group-stage rows without #groups")
        elif len(values) > 1:
            errors.append(f"{competition} {competition_class} has inconsistent #groups values: {sorted(values)}")
    return errors


def find_missing_group_seedings(draw_data) -> list:
    """Check that every group-stage row has a seeding, which the group draw sorts by."""
    return [
        f"{_entry_label(row)} has no seeding"
        for row in draw_data
        if row.group_pos is None and row.seeding is None
    ]


def find_too_few_group_entries(draw_data) -> list:
    """Check that #groups is at least 1 and no larger than the number of group-stage entries of its class."""
    entries = defaultdict(list)
    for row in draw_data:
        if row.group_pos is None:
            entries[(row.competition, row.competition_class)].append(row)
    errors = []
    for (competition, competition_class), rows in sorted(entries.items()):
        values = {row.amount_of_groups for row in rows}
        if len(values) != 1 or None in values:
            continue  # reported by find_inconsistent_group_counts
        amount_of_groups = values.pop()
        if amount_of_groups < 1:
            errors.append(f"{competition} {competition_class} has #groups={amount_of_groups}; it must be at least 1")
        elif len(rows) < amount_of_groups:
            errors.append(f"{competition} {competition_class} has {len(rows)} group-stage entries for {amount_of_groups} groups; at least one group would be empty")
    return errors


def find_draw_data_errors(draw_data) -> list:
    """Run all structural draw data checks. Requires players_by_start_number to be populated and all referenced players to exist."""
    return (
        find_invalid_round_flags(draw_data)
        + find_group_no_pos_mismatch(draw_data)
        + find_duplicate_players_in_class(draw_data)
        + find_duplicate_group_positions(draw_data)
        + find_invalid_pairs(draw_data)
        + find_invalid_mixed_pairs(draw_data)
        + find_inconsistent_group_counts(draw_data)
        + find_missing_group_seedings(draw_data)
        + find_too_few_group_entries(draw_data)
    )
