"""Tests for data_io/output_writer.py."""
import csv

import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.bracket_drawer import draw_bracket
from misc.config import config
from data_io.output_writer import (
    HEADERS,
    prepare_export_from_bracket_draw,
    prepare_export_from_group_draw,
    write_to_csv,
)


@pytest.fixture
def eight_players():
    """Create 8 players (start numbers 1-8) and populate players_by_start_number."""
    Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
    Player(2, 'Betty', 'Bravo', 'SWE', 'Base2', 'F', 1100)
    Player(3, 'Cara', 'Charlie', 'GER', 'Base1', 'F', 1150)
    Player(4, 'Dora', 'Delta', 'SWE', 'Base3', 'F', 1050)
    Player(5, 'Eve', 'Echo', 'NOR', 'Base4', 'F', 1000)
    Player(6, 'Fay', 'Foxtrot', 'FIN', 'Base5', 'F', 980)
    Player(7, 'Gina', 'Golf', 'SWE', 'Base2', 'F', 970)
    Player(8, 'Hana', 'Hotel', 'GER', 'Base6', 'F', 950)
    for p in players_list:
        players_by_start_number[p.start_number] = p
    seeding_by_start_numbers.clear()
    yield
    seeding_by_start_numbers.clear()


@pytest.fixture
def output_file_path(tmp_path):
    """Point config["files"]["output_file_path"] at a temp file.

    initialize_config never runs under pytest, so the singleton ConfigParser has
    no sections at all until a test adds one.
    """
    path = tmp_path / "nested" / "output.csv"
    config["files"] = {"output_file_path": str(path)}
    yield path
    config.remove_section("files")


def _singles_rows(start_numbers):
    """Build singles bracket-stage rows, two groups of four."""
    for i, sn in enumerate(start_numbers, start=1):
        seeding_by_start_numbers[str(sn)] = 300 - i

    rows = []
    for index, sn in enumerate(start_numbers):
        group_no = 1 if index < 4 else 2
        group_pos = index % 4 + 1
        rows.append(
            DrawDataRow('S', 'M1', seeding_by_start_numbers[str(sn)], 2, group_no, group_pos, True, False, sn, '')
        )
    return rows


def _bracket_payload(rows):
    matches, _ = draw_bracket(rows)
    return {'S': {'M1': {'main': {'matches': matches}}}}, matches


def test_bracket_rows_are_one_per_slot_in_rasterzahl_order(eight_players):
    payload, matches = _bracket_payload(_singles_rows([1, 2, 3, 4, 5, 6, 7, 8]))

    export = prepare_export_from_bracket_draw(payload)

    bracket_size = len(matches) * 2
    assert [row.draw_number for row in export] == list(range(1, bracket_size + 1))
    assert all(row.for_main_round is True for row in export)
    assert all(row.for_consolation is False for row in export)


def test_bye_slot_gets_its_own_row_with_empty_player_columns(eight_players):
    # Seven participants in an eight-slot bracket leaves exactly one BYE.
    payload, matches = _bracket_payload(_singles_rows([1, 2, 3, 4, 5, 6, 7]))

    export = prepare_export_from_bracket_draw(payload)

    assert [row.draw_number for row in export] == list(range(1, len(matches) * 2 + 1))

    bye_rows = [row for row in export if row.is_bye]
    assert len(bye_rows) == 1
    bye = bye_rows[0]
    assert bye.startnumber_A == ''
    assert bye.last_name_A == ''
    assert bye.country_A == ''
    assert bye.PPP_chapter_A == ''
    assert bye.startnumber_B == ''
    assert (bye.seeding, bye.group_no, bye.group_pos) == ('', '', '')

    played = [row for row in export if not row.is_bye]
    assert {row.startnumber_A for row in played} == {1, 2, 3, 4, 5, 6, 7}


def test_doubles_bracket_row_carries_the_partner_not_the_opponent(eight_players):
    """The B columns are the doubles pair's second player (output_explainer.md)."""
    pairs = [(1, 2), (3, 4), (5, 6), (7, 8)]
    rows = []
    for index, (sn_a, sn_b) in enumerate(pairs):
        seeding = 300 - index
        seeding_by_start_numbers[f"{sn_a}/{sn_b}"] = seeding
        rows.append(
            DrawDataRow('D', 'M1', seeding, 2, index % 2 + 1, index // 2 + 1, True, False, sn_a, sn_b)
        )
    matches, _ = draw_bracket(rows)

    export = prepare_export_from_bracket_draw({'D': {'M1': {'main': {'matches': matches}}}})

    exported_pairs = {(row.startnumber_A, row.startnumber_B) for row in export if not row.is_bye}
    assert exported_pairs == set(pairs)

    for row in export:
        if row.is_bye:
            continue
        assert row.last_name_B == players_by_start_number[row.startnumber_B].last_name
        assert row.country_B == players_by_start_number[row.startnumber_B].country


def test_group_rows_carry_group_number_and_no_draw_number(eight_players):
    groups = {
        'S': {
            'M1': {
                'group': {
                    1: [DrawDataRow('S', 'M1', 100, 2, '', '', False, False, 1, '')],
                    2: [DrawDataRow('S', 'M1', 90, 2, '', '', False, False, 2, '')],
                }
            }
        }
    }

    export = prepare_export_from_group_draw(groups)

    assert [row.group_no for row in export] == [1, 2]
    assert all(row.draw_number is None for row in export)
    assert all(row.is_bye == '' for row in export)
    assert [row.last_name_A for row in export] == ['Alpha', 'Bravo']
    assert all(row.startnumber_B == '' for row in export)


def test_write_to_csv_emits_the_documented_header_and_rows(eight_players, output_file_path):
    payload, matches = _bracket_payload(_singles_rows([1, 2, 3, 4, 5, 6, 7, 8]))
    export = prepare_export_from_bracket_draw(payload)

    written = write_to_csv(export)

    assert written == str(output_file_path)
    with open(written, newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file, delimiter=';')
        assert next(reader) == HEADERS
        rows = list(reader)

    assert len(rows) == len(matches) * 2
    assert [int(row[HEADERS.index("draw_number")]) for row in rows] == list(range(1, len(rows) + 1))
