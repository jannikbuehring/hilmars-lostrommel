"""Bracket draw inputs shared by the drawer tests and the golden fingerprints."""

from models.draw_data import DrawDataRow, seeding_by_start_numbers
from models.player import Player, players_by_start_number, players_list


def build_tiered_rows(
    number_of_groups, positions, competition_class="M1", first_start_number=201, short_groups=(), country_for=None
):
    """Register fresh players and return rows for number_of_groups x positions.

    Unique countries and bases per player so the country/base terms cannot
    manufacture unrelated violations, and strictly descending seedings.

    *short_groups* lists group numbers that omit the LAST position, i.e. an uneven
    class where not every group sent a qualifier for that tier.

    *country_for* optionally overrides that: a ``(group_no, group_pos) -> country
    or None`` callable, so a test can give two participants the SAME country and
    make the country terms actually bite.  Returning None keeps the unique default.
    """
    group_positions = {
        group_no: (positions[:-1] if group_no in short_groups else positions)
        for group_no in range(1, number_of_groups + 1)
    }
    # Countries are decided per (group_no, group_pos), so resolve the layout before
    # registering the players -- start numbers are handed out in that same order.
    layout = [
        (group_no, group_pos) for group_no in range(1, number_of_groups + 1) for group_pos in group_positions[group_no]
    ]
    for offset, (group_no, group_pos) in enumerate(layout):
        sn = first_start_number + offset
        country = country_for(group_no, group_pos) if country_for is not None else None
        Player(sn, f"Last{sn}", f"First{sn}", country or f"C{sn}", f"Base{sn}", "F", 2000 - sn)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    rows = []
    seed = 300
    for offset, (group_no, group_pos) in enumerate(layout):
        sn = first_start_number + offset
        seeding_by_start_numbers[str(sn)] = seed
        rows.append(
            DrawDataRow("S", competition_class, seed, number_of_groups, group_no, group_pos, True, False, sn, None)
        )
        seed -= 1
    return rows


def build_doubles_rows(number_of_groups, positions, competition_class="D1", first_start_number=601):
    """Register fresh players and return doubles rows for number_of_groups x positions.

    Each entry is a team of two players from two different countries, keyed
    "A/B" in seeding_by_start_numbers like read_draw_data does.
    """
    layout = [(group_no, group_pos) for group_no in range(1, number_of_groups + 1) for group_pos in positions]
    rows = []
    seed = 300
    for offset, (group_no, group_pos) in enumerate(layout):
        sn_a = first_start_number + 2 * offset
        sn_b = sn_a + 1
        Player(sn_a, f"Last{sn_a}", f"First{sn_a}", f"C{sn_a % 7}", f"Base{sn_a}", "M", 2000 - sn_a)
        Player(sn_b, f"Last{sn_b}", f"First{sn_b}", f"C{sn_b % 5}", f"Base{sn_b}", "M", 2000 - sn_b)
        seeding_by_start_numbers[f"{sn_a}/{sn_b}"] = seed
        rows.append(
            DrawDataRow("D", competition_class, seed, number_of_groups, group_no, group_pos, True, False, sn_a, sn_b)
        )
        seed -= 1
    for p in players_list:
        players_by_start_number[p.start_number] = p
    return rows
