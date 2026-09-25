"""Tests for data_io/output_writer.py."""
import csv
from types import SimpleNamespace

import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.bracket_drawer import draw_bracket
from misc.config import config
from data_io.output_writer import (
    HEADERS,
    REPORT_HEADERS,
    archive_previous_outputs,
    prepare_export_from_bracket_draw,
    prepare_export_from_group_draw,
    prepare_report,
    report_file_path,
    write_report_csv,
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

    assert not (output_file_path.parent / "output.csv.tmp").exists()


def test_failed_write_keeps_no_partial_file(output_file_path):
    """A row that cannot be written must not leave a half-written CSV behind."""
    bad = SimpleNamespace(**{h: '' for h in HEADERS}, unexpected='x')

    with pytest.raises(ValueError):
        write_to_csv([bad])

    assert not output_file_path.exists()
    assert not (output_file_path.parent / "output.csv.tmp").exists()


def test_report_has_one_row_per_draw_with_status(output_file_path):
    groups = {'S': {'M1': {}, 'M3': {'violation_count': 2}}, 'D': {}, 'M': {}}
    group_failures = [('D', 'W1', 'boom')]
    brackets = {'S': {'M2': {
        'main': {'quality': {'degraded': False, 'hard': {}, 'soft_count': 3}},
        'consolation': {'quality': {
            'degraded': True,
            'hard': {'half_group_separation': ['g1: positions 4/7 and 5/6 share a half']},
            'soft_count': 1,
        }},
    }, 'W1': {
        'main': {'quality': {'failed': True, 'message': 'no slot'}},
        'consolation': {'quality': {'degraded': False, 'hard': {'first_vs_first': ['x', 'y']}, 'soft_count': 0}},
    }}}

    rows = prepare_report(groups, group_failures, brackets)
    by_key = {(r['S_D_M'], r['class'], r['draw']): r for r in rows}

    assert by_key[('S', 'M1', 'groups')]['status'] == 'ok'
    assert by_key[('S', 'M3', 'groups')]['status'] == 'violations'
    assert by_key[('S', 'M3', 'groups')]['other_violations'] == 2
    assert by_key[('D', 'W1', 'groups')]['status'] == 'failed'
    assert by_key[('D', 'W1', 'groups')]['details'] == 'boom'
    assert by_key[('S', 'M2', 'main')]['status'] == 'ok'
    assert by_key[('S', 'M2', 'main')]['other_violations'] == 3
    consolation = by_key[('S', 'M2', 'consolation')]
    assert consolation['status'] == 'degraded'
    assert consolation['half_group_separation'] == 1
    assert 'positions 4/7 and 5/6' in consolation['details']
    assert by_key[('S', 'W1', 'main')]['status'] == 'failed'
    assert by_key[('S', 'W1', 'consolation')]['status'] == 'violations'
    assert by_key[('S', 'W1', 'consolation')]['first_vs_first'] == 2


    forced_only = {'S': {'W3': {'consolation': {'quality': {
        'degraded': False, 'hard': {},
        'forced': {'first_vs_first_forced': ['a', 'b', 'c', 'd']}, 'soft_count': 0,
    }}}}}
    forced_row = prepare_report({}, [], forced_only)[0]
    assert forced_row['status'] == 'ok'
    assert forced_row['first_vs_first'] == 0
    assert forced_row['details'] == '4 unavoidable first_vs_first'

    written = write_report_csv(rows)

    assert written == str(output_file_path.parent / "output_report.csv") == report_file_path()
    with open(written, newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file, delimiter=';')
        assert next(reader) == REPORT_HEADERS
        assert len(list(reader)) == len(rows)


@pytest.fixture
def output_dirs(output_file_path, tmp_path):
    """Output CSV plus bracket/group HTML directories under one tmp output dir."""
    out = output_file_path.parent
    config["files"]["bracket_html_output_dir"] = str(out / "brackets")
    config["files"]["group_html_output_dir"] = str(out / "groups")
    (out / "brackets").mkdir(parents=True)
    (out / "groups").mkdir(parents=True)
    return out


def test_archive_moves_previous_outputs(output_dirs, output_file_path):
    out = output_dirs
    output_file_path.write_text("old csv")
    (out / "output_report.csv").write_text("old report")
    (out / "brackets" / "S_M1_main_bracket.html").write_text("old bracket")
    (out / "groups" / "S_M1_groups.html").write_text("old groups")
    (out / "brackets" / "notes.html").write_text("not ours")
    (out / "example_output.csv").write_text("reference file")
    (out / "previous").mkdir()
    (out / "previous" / "stale.csv").write_text("from two runs ago")

    moved = archive_previous_outputs()

    assert len(moved) == 4
    assert not output_file_path.exists()
    assert not (out / "brackets" / "S_M1_main_bracket.html").exists()
    assert (out / "previous" / "output.csv").read_text() == "old csv"
    assert (out / "previous" / "output_report.csv").read_text() == "old report"
    assert (out / "previous" / "brackets" / "S_M1_main_bracket.html").read_text() == "old bracket"
    assert (out / "previous" / "groups" / "S_M1_groups.html").read_text() == "old groups"
    # The run before the previous one is dropped; unrelated files stay put.
    assert not (out / "previous" / "stale.csv").exists()
    assert (out / "brackets" / "notes.html").exists()
    assert (out / "example_output.csv").exists()


def test_archive_propagates_a_locked_file(output_dirs, output_file_path, monkeypatch):
    """A file open in Excel must stop the run before drawing, not after."""
    output_file_path.write_text("old csv")

    def locked(src, dst):
        raise PermissionError(13, "Permission denied", src)

    monkeypatch.setattr("data_io.output_writer.os.replace", locked)

    with pytest.raises(PermissionError):
        archive_previous_outputs()
