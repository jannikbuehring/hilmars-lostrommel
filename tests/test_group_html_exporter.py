"""Tests for viewer/group_html_exporter.py."""
import json
import re

import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.group_drawer import draw_groups_monte_carlo
from misc.config import config
from misc.version import APP_NAME, __version__
from viewer.group_html_exporter import export_group_html, group_html_filename

DATA_SCRIPT_RE = re.compile(
    r'<script type="application/json" id="group-data">(.*?)</script>', re.DOTALL
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
    Player(7, 'Gina', 'Golf', 'SWE', 'Base2', 'F', None)
    Player(8, 'Hana', 'Hotel', 'GER', 'Base6', 'F', 950)
    for p in players_list:
        players_by_start_number[p.start_number] = p
    seeding_by_start_numbers.clear()
    yield
    seeding_by_start_numbers.clear()


@pytest.fixture
def group_draw_config():
    """Seed config["group_draw"], which initialize_config never fills under pytest.

    Iteration counts are kept small so the draw (and its snapshot history) stays
    fast; the exporter's behavior does not depend on their size.
    """
    config["group_draw"] = {
        "max_iterations": "200",
        "max_no_improvement_iterations": "50",
        "max_escape_attempts": "2",
        "max_seed_retries": "2",
        "country_violation_weight": "1",
        "team_country_violation_weight": "1",
        "base_violation_weight": "1",
        "qttr_violation_weight": "1",
    }
    yield
    config.remove_section("group_draw")


def _singles_rows(start_numbers, amount_of_groups=2):
    """Build singles group-stage rows (group_no/group_pos empty = not yet drawn)."""
    rows = []
    for i, sn in enumerate(start_numbers, start=1):
        seeding = 300 - i
        seeding_by_start_numbers[str(sn)] = seeding
        rows.append(
            DrawDataRow('S', 'M1', seeding, amount_of_groups, '', '', True, False, sn, '')
        )
    return rows


def _doubles_rows(pairs, amount_of_groups=2):
    """Build doubles group-stage rows from (start_number_a, start_number_b) pairs."""
    rows = []
    for i, (a, b) in enumerate(pairs, start=1):
        seeding = 300 - i
        seeding_by_start_numbers[f"{a}/{b}"] = seeding
        rows.append(
            DrawDataRow('D', 'W1', seeding, amount_of_groups, '', '', True, False, a, b)
        )
    return rows


def _export_and_parse(competition, competition_class, rows, tmp_path, amount_of_groups=2, **kwargs):
    """Draw one class, export it, and return (groups, snapshots, html, payload)."""
    groups, snapshots = draw_groups_monte_carlo(
        class_subset=rows, amount_of_groups=amount_of_groups)
    path = export_group_html(
        competition, competition_class, groups, snapshots, str(tmp_path), **kwargs)
    assert path.endswith(group_html_filename(competition, competition_class))
    html = open(path, encoding="utf-8").read()
    payload = json.loads(DATA_SCRIPT_RE.search(html).group(1))
    return groups, snapshots, html, payload


def _replay(payload, up_to=None):
    """Replay the payload's steps in Python, mirroring the exported page's JS.

    This is the contract the embedded JS implements; if the two ever diverge the
    page would show a state the draw never produced.
    """
    state = {g: list(members) for g, members in payload["initial"].items()}
    steps = payload["steps"] if up_to is None else payload["steps"][:up_to + 1]
    for step in steps:
        if step["a"] not in ("swap", "revert"):
            continue
        g1, g2 = str(step["g"][0]), str(step["g"][1])
        index = step["i"]
        p1, p2 = step["p"]
        if step["a"] == "swap":
            state[g1][index], state[g2][index] = p2, p1
        else:
            state[g1][index], state[g2][index] = p1, p2
    return state


def _keys_from_groups(groups):
    """The drawn groups as {group_no: [participant key, ...]} (empty slots dropped)."""
    keyed = {}
    for group_no, members in groups.items():
        keys = []
        for member in members:
            key = str(member.start_number_a)
            if member.start_number_b is not None:
                key += "/" + str(member.start_number_b)
            keys.append(key)
        keyed[str(group_no)] = keys
    return keyed


def test_export_writes_html_with_valid_embedded_json(eight_players, group_draw_config, tmp_path):
    rows = _singles_rows([1, 2, 3, 4, 5, 6, 7, 8])
    groups, snapshots, _, payload = _export_and_parse('S', 'M1', rows, tmp_path)

    assert payload["amount_of_groups"] == len(groups) == 2
    assert payload["max_group_size"] == 4
    assert len(payload["steps"]) == len(snapshots)
    assert payload["total_snapshots"] == len(snapshots)
    assert payload["first_snapshot_index"] == 0

    # Every participant is in the roster exactly once, with display data attached.
    assert set(payload["roster"]) == {str(row.start_number_a) for row in rows}
    entry = payload["roster"]["1"]
    assert entry["seeding"] == 299
    assert entry["names"][0]["last_name"] == "Alpha"
    assert entry["names"][0]["country"] == "GER"
    assert entry["names"][0]["qttr"] == 1200


def test_replaying_every_step_reproduces_the_drawn_groups(
        eight_players, group_draw_config, tmp_path):
    """The page starts from `initial` and replays deltas, so the last step must
    land exactly on the groups draw_groups_monte_carlo returned."""
    rows = _singles_rows([1, 2, 3, 4, 5, 6, 7, 8])
    groups, _, _, payload = _export_and_parse('S', 'M1', rows, tmp_path)

    assert _replay(payload) == _keys_from_groups(groups)


def test_empty_slots_serialize_as_empty_not_unknown(
        eight_players, group_draw_config, tmp_path):
    """7 participants in 2 groups leaves one EmptySlot; it must be a null key, not
    an "EMPTY" participant (EmptySlot.start_number_a == "EMPTY" would otherwise
    reach participant_display_fields and render as Unknown(EMPTY))."""
    rows = _singles_rows([1, 2, 3, 4, 5, 6, 7])
    groups, _, html, payload = _export_and_parse('S', 'M1', rows, tmp_path)

    assert "EMPTY" not in html
    assert "EMPTY" not in payload["roster"]
    # The padded state carries one empty slot; the drawn groups have it stripped.
    assert sum(1 for m in payload["initial"].values() for k in m if k is None) == 1
    assert sum(len(m) for m in groups.values()) == 7

    replayed = {g: [k for k in members if k is not None]
                for g, members in _replay(payload).items()}
    assert replayed == _keys_from_groups(groups)


def test_doubles_rows_carry_both_players_with_qttr(
        eight_players, group_draw_config, tmp_path):
    rows = _doubles_rows([(1, 2), (3, 4), (5, 6), (7, 8)])
    _, _, _, payload = _export_and_parse('D', 'W1', rows, tmp_path)

    assert set(payload["roster"]) == {"1/2", "3/4", "5/6", "7/8"}
    names = payload["roster"]["1/2"]["names"]
    assert [n["last_name"] for n in names] == ["Alpha", "Bravo"]
    assert [n["qttr"] for n in names] == [1200, 1100]
    # A player without a QTTR rating keeps the key, with a null value.
    assert payload["roster"]["7/8"]["names"][0]["qttr"] is None


def test_max_snapshots_truncates_the_head_and_keeps_the_final_groups(
        eight_players, group_draw_config, tmp_path):
    rows = _singles_rows([1, 2, 3, 4, 5, 6, 7, 8])
    groups, snapshots, _, payload = _export_and_parse(
        'S', 'M1', rows, tmp_path, max_snapshots=5)

    if len(snapshots) <= 5:
        pytest.skip("draw converged in fewer snapshots than the cap")

    assert len(payload["steps"]) == 5
    assert payload["total_snapshots"] == len(snapshots)
    assert payload["first_snapshot_index"] == len(snapshots) - 5
    # The oldest snapshots were collapsed into `initial`, so the replay still
    # ends on the real drawn groups.
    assert _replay(payload) == _keys_from_groups(groups)


def test_footer_shows_version_and_timings(eight_players, group_draw_config, tmp_path):
    rows = _singles_rows([1, 2, 3, 4, 5, 6, 7, 8])
    run_meta = {
        "version": __version__,
        "total_seconds": 11.75,
        "generated_at": "2026-08-02 14:31",
        "random_seed": "789123",
    }
    _, _, html, payload = _export_and_parse(
        'S', 'M1', rows, tmp_path, run_meta=run_meta, draw_seconds=3.4213)

    assert f"{APP_NAME} v{__version__}" in html
    assert "Singles Men 1 Groups drawn in 3.42 s" in html
    assert "total run 11.75 s" in html
    assert "seed 789123" in html
    assert "generated 2026-08-02 14:31" in html

    # The same provenance must also be machine-readable in the embedded JSON.
    assert payload["meta"]["version"] == __version__
    assert payload["meta"]["draw_seconds"] == pytest.approx(3.4213)
    assert payload["meta"]["total_seconds"] == pytest.approx(11.75)


def test_export_without_run_meta_still_reports_version(
        eight_players, group_draw_config, tmp_path):
    """The group_viewer fallback re-exports after the pipeline has finished and
    passes no run_meta; the footer must degrade instead of failing."""
    rows = _singles_rows([1, 2, 3, 4, 5, 6, 7, 8])
    _, _, html, _ = _export_and_parse('S', 'M1', rows, tmp_path)

    assert f"{APP_NAME} v{__version__}" in html
    assert "generated " in html
    assert "total run" not in html
    assert "drawn in" not in html


def test_export_without_snapshots_still_renders_the_groups(eight_players, tmp_path):
    """A history-less export (no snapshots) falls back to the drawn groups."""
    groups = {
        1: _singles_rows([1, 2, 3, 4]),
        2: _singles_rows([5, 6, 7, 8]),
    }
    path = export_group_html('S', 'M1', groups, [], str(tmp_path))
    payload = json.loads(DATA_SCRIPT_RE.search(open(path, encoding="utf-8").read()).group(1))

    assert payload["initial"] == _keys_from_groups(groups)
    assert len(payload["steps"]) == 1
    assert payload["total_snapshots"] == 1


def test_export_returns_none_when_there_is_nothing_to_export(eight_players, tmp_path):
    assert export_group_html('S', 'M1', {}, [], str(tmp_path)) is None
