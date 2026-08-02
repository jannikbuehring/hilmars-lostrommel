"""Tests for viewer/bracket_html_exporter.py."""
import json
import re

import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.bracket_drawer import draw_bracket
from misc.version import APP_NAME, __version__
from viewer.bracket_html_exporter import export_bracket_html, _format_duration

DATA_SCRIPT_RE = re.compile(
    r'<script type="application/json" id="bracket-data">(.*?)</script>', re.DOTALL
)


@pytest.fixture
def eight_players():
    """Create 8 female players (start numbers 1-8) and populate players_by_start_number."""
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


def _draw_eight_player_bracket():
    for i, sn in enumerate([1, 2, 3, 4, 5, 6, 7, 8], start=1):
        seeding_by_start_numbers[str(sn)] = 300 - i

    group_layout = [
        (1, 1, 1), (2, 1, 2), (3, 1, 3), (4, 1, 4),
        (5, 2, 1), (6, 2, 2), (7, 2, 3), (8, 2, 4),
    ]
    rows = [
        DrawDataRow('S', 'M1', seeding_by_start_numbers[str(sn)], 2, group_no, group_pos, True, False, sn, '')
        for sn, group_no, group_pos in group_layout
    ]
    matches, snapshots = draw_bracket(rows)
    return rows, matches, snapshots


def test_export_writes_html_with_valid_embedded_json(eight_players, tmp_path):
    rows, matches, snapshots = _draw_eight_player_bracket()
    bracket = {"main": {"matches": matches, "snapshots": snapshots}}

    paths = export_bracket_html("S", "M1", bracket, str(tmp_path))

    assert len(paths) == 1
    html = open(paths[0], encoding="utf-8").read()

    match = DATA_SCRIPT_RE.search(html)
    assert match is not None, "Expected an embedded <script id=bracket-data> JSON block"
    payload = json.loads(match.group(1))

    assert payload["number_of_matches"] == len(matches)
    assert len(payload["snapshots"]) == len(snapshots)

    final_matches = payload["snapshots"][-1]["matches"]
    exported_start_numbers = set()
    for participants in final_matches.values():
        for p in participants:
            if isinstance(p, dict):
                for name in p["names"]:
                    exported_start_numbers.add(name.get("start_number", name.get("unknown")))

    original_start_numbers = {row.start_number_a for row in rows}
    assert original_start_numbers <= exported_start_numbers


def test_export_skips_missing_bracket_types(eight_players, tmp_path):
    _, matches, snapshots = _draw_eight_player_bracket()
    bracket = {"main": {"matches": matches, "snapshots": snapshots}}

    paths = export_bracket_html("S", "M1", bracket, str(tmp_path))

    assert len(paths) == 1
    assert "consolation" not in paths[0]


def test_every_serialized_match_has_two_slots(eight_players, tmp_path):
    """Guard against the partial/phase-1 crash: matches can be [] or length 1 in
    slots_to_matches; the exporter must pad every match to exactly two slots so
    the JS renderer never indexes past the array."""
    _, matches, snapshots = _draw_eight_player_bracket()
    bracket = {"main": {"matches": matches, "snapshots": snapshots}}

    paths = export_bracket_html("S", "M1", bracket, str(tmp_path))
    html = open(paths[0], encoding="utf-8").read()
    payload = json.loads(DATA_SCRIPT_RE.search(html).group(1))

    for snap in payload["snapshots"]:
        for match_idx, sides in snap["matches"].items():
            assert len(sides) == 2, f"Match {match_idx} has {len(sides)} slots, expected 2"


def test_footer_shows_version_and_timings(eight_players, tmp_path):
    _, matches, snapshots = _draw_eight_player_bracket()
    bracket = {"main": {"matches": matches, "snapshots": snapshots, "draw_seconds": 3.4213}}
    run_meta = {
        "version": __version__,
        "total_seconds": 11.75,
        "generated_at": "2026-08-02 14:31",
        "random_seed": "789123",
    }

    paths = export_bracket_html("S", "M1", bracket, str(tmp_path), run_meta=run_meta)
    html = open(paths[0], encoding="utf-8").read()

    assert f"{APP_NAME} v{__version__}" in html
    assert "drawn in 3.42 s" in html
    assert "total run 11.75 s" in html
    assert "seed 789123" in html
    assert "generated 2026-08-02 14:31" in html

    # The same provenance must also be machine-readable in the embedded JSON.
    payload = json.loads(DATA_SCRIPT_RE.search(html).group(1))
    assert payload["meta"]["version"] == __version__
    assert payload["meta"]["draw_seconds"] == pytest.approx(3.4213)
    assert payload["meta"]["total_seconds"] == pytest.approx(11.75)


def test_export_without_run_meta_still_reports_version(eight_players, tmp_path):
    """The bracket_viewer fallback re-exports after the pipeline has finished and
    passes no run_meta; the footer must degrade instead of failing."""
    _, matches, snapshots = _draw_eight_player_bracket()
    bracket = {"main": {"matches": matches, "snapshots": snapshots}}

    paths = export_bracket_html("S", "M1", bracket, str(tmp_path))
    html = open(paths[0], encoding="utf-8").read()

    assert f"{APP_NAME} v{__version__}" in html
    assert "generated " in html
    assert "total run" not in html
    assert "drawn in" not in html


@pytest.mark.parametrize("seconds, expected", [
    (None, None),
    (0.0, "0.00 s"),
    (3.4213, "3.42 s"),
    (59.994, "59.99 s"),
    (60.0, "1 min 0.0 s"),
    (135.5, "2 min 15.5 s"),
])
def test_format_duration(seconds, expected):
    assert _format_duration(seconds) == expected
