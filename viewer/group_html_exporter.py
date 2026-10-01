"""Export a group draw (with full snapshot history) to a self-contained HTML file.

The exported file renders every group as a card and embeds the draw's Snapshot
history as JSON, so the page can step through the Monte Carlo optimization
entirely offline, with no server and no network requests.

Unlike the bracket export, which stores a full state per snapshot, the group
payload is **delta-encoded**: draw/group_drawer.py records only the initial
state plus one swap/revert per snapshot, and a single class can produce tens of
thousands of them (max_iterations = 20000, up to two snapshots per iteration).
Storing a full state each time would produce hundred-megabyte files, so the
page embeds the roster once, the state the history starts from, and one small
step object per snapshot, replaying them in JS exactly the way
_apply_snapshot replays them in Python.
"""

import html
import json
import os

from core.version import APP_NAME, __version__
from draw.group_drawer import EmptySlot
from models.snapshot import Snapshot
from viewer.viewer_shared import (
    class_display_name,
    participant_display_fields,
    participant_key,
    read_asset,
    render_footer,
)


def _slot_key(p):
    """Stable identity key for a group slot, or None for an empty slot.

    EmptySlot carries start_number_a == "EMPTY" (draw/group_drawer.py), which
    participant_display_fields would render as "Unknown(EMPTY)", so empty slots
    are filtered out here instead. All empty slots share the key None, which is
    correct: they are interchangeable, so swapping two of them is a no-op.
    """
    if p is None or isinstance(p, EmptySlot):
        return None
    if getattr(p, "start_number_a", None) == "EMPTY":
        return None
    return participant_key(p)


def _roster_entry(p):
    """Serialize one participant for the roster (stored once, not per snapshot)."""
    fields = participant_display_fields(p, include_qttr=True)
    if fields is None or fields in ("BYE", "ERR"):
        return {"seeding": None, "names": []}
    return {"seeding": fields["seeding"], "names": fields["names"]}


def _apply_snapshot(state, snapshot, forward=True):
    """Apply one snapshot's delta to *state* (dict of group_no -> list of keys).

    A "swap" put p2 where p1
    was and vice versa, a "revert" put them back. Going backward is the inverse
    assignment. Used here to fast-forward the truncated head of a long history;
    the exported JS applies the identical rule.
    """
    action = getattr(snapshot, "action", None)
    if action not in ("swap", "revert"):
        return
    g1, g2 = snapshot.groups
    index = snapshot.index
    key1, key2 = (_slot_key(p) for p in snapshot.participants)
    if (action == "swap") == forward:
        state[g1][index], state[g2][index] = key2, key1
    else:
        state[g1][index], state[g2][index] = key1, key2


def _build_group_payload(competition, competition_class, groups, snapshots, max_snapshots=None):
    """Build the JSON-serializable payload embedded in the exported HTML."""
    # snapshots[0] holds the padded initial state (empty slots included); the
    # drawn groups are only the fallback for a history-less export.
    initial_groups = getattr(snapshots[0], "state", None) if snapshots else None
    if initial_groups is None:
        initial_groups = groups

    roster = {}

    def register(p):
        key = _slot_key(p)
        if key is not None and key not in roster:
            roster[key] = _roster_entry(p)
        return key

    state = {}
    for group_no, members in initial_groups.items():
        state[group_no] = [register(p) for p in members]

    max_group_size = max((len(members) for members in state.values()), default=0)
    # A partially filled group would otherwise render fewer rows than its
    # neighbours and misalign the cards.
    for members in state.values():
        while len(members) < max_group_size:
            members.append(None)

    total_snapshots = len(snapshots)
    first_index = 0
    if max_snapshots and total_snapshots > max_snapshots:
        # Collapse the oldest snapshots into the start state instead of dropping
        # the newest ones, so the page always ends on the real drawn groups.
        first_index = total_snapshots - max_snapshots
        for snapshot in snapshots[1 : first_index + 1]:
            _apply_snapshot(state, snapshot, forward=True)

    steps = []
    for snapshot in snapshots[first_index:]:
        for p in snapshot.participants or []:
            register(p)
        step = {
            "a": getattr(snapshot, "action", None),
            "s": snapshot.violation_score,
            "v": snapshot.violations,
        }
        if step["a"] in ("swap", "revert"):
            step["g"] = list(snapshot.groups)
            step["i"] = snapshot.index
            step["p"] = [_slot_key(p) for p in snapshot.participants]
        steps.append(step)

    if not steps:
        # No history at all: show the drawn groups as a single "snapshot".
        steps.append({"a": None, "s": None, "v": {}})
        total_snapshots = 1

    return {
        "competition": competition,
        "competition_class": competition_class,
        "amount_of_groups": len(state),
        "max_group_size": max_group_size,
        "roster": roster,
        "initial": {str(group_no): members for group_no, members in state.items()},
        "steps": steps,
        "total_snapshots": total_snapshots,
        "first_snapshot_index": first_index,
    }


def _render_group_cards(group_numbers, max_group_size):
    """Emit the static group cards.

    Every slot row has id="slot-{group}-{index}" and empty value spans; the JS
    fills them per snapshot. The structure is static because only *which*
    participant sits in a slot changes across the history, never the layout.
    """
    if not group_numbers:
        return '<div class="groups"></div>'

    cards = []
    for group_no in group_numbers:
        rows = [
            '<div class="row head">'
            '<span class="pos">#</span><span class="seed">Seed</span>'
            '<span class="names">Name</span><span class="country">Country</span>'
            '<span class="base">Base</span><span class="qttr">QTTR</span></div>'
        ]
        for index in range(max_group_size):
            rows.append(
                f'<div class="row" id="slot-{group_no}-{index}">'
                f'<span class="pos">{index + 1}</span><span class="seed"></span>'
                f'<span class="names"></span><span class="country"></span>'
                f'<span class="base"></span><span class="qttr"></span></div>'
            )
        cards.append(
            f'<section class="group-card">'
            f'<div class="group-label">Group {html.escape(str(group_no))}</div>'
            f"{''.join(rows)}</section>"
        )

    return f'<div class="groups">{"".join(cards)}</div>'


def _render_html_document(heading, payload, cards_markup, footer_markup):
    """Assemble the page. The heading doubles as the <title>, since a group page
    covers one competition class as a whole (the bracket page's title adds the
    bracket type on top of its heading)."""
    # Escape "</script" so embedded participant data (names/bases from CSV input)
    # can never prematurely close the <script> tag it's embedded in.
    payload_json = json.dumps(payload, default=str).replace("</script", "<\\/script")
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="generator" content="{html.escape(f"{APP_NAME} {__version__}")}">
<title>{html.escape(heading)}</title>
<style>
{read_asset("groups.css")}</style>
</head>
<body>
<div class="controls">
  <span class="class-title">{html.escape(heading)}</span>
  <button id="btn-prev">&larr; Prev</button>
  <button id="btn-next">Next &rarr;</button>
  <button id="btn-first">Show first snapshot</button>
  <button id="btn-improvement">Forward to next improvement</button>
  <button id="btn-final">Show final groups</button>
  <input type="number" id="jump-input" min="1" placeholder="#">
  <button id="btn-jump">Go to snapshot</button>
  <label><input type="checkbox" id="auto-scroll" checked> Scroll to change</label>
  <label><input type="checkbox" id="show-violations"> Show violation details</label>
  <div class="meta">
    <div id="snapshot-label"></div>
    <div id="score-label"></div>
    <div class="truncated" id="truncated-label"></div>
    <div class="violations" id="violations-label"></div>
  </div>
</div>
{cards_markup}
{footer_markup}
<script type="application/json" id="group-data">{payload_json}</script>
<script>
{read_asset("groups.js")}</script>
</body>
</html>
"""


def group_html_filename(competition: str, competition_class: str) -> str:
    """Return the HTML filename for one competition class's groups (shared naming convention)."""
    return f"{competition}_{competition_class}_groups.html"


def group_html_path(competition: str, competition_class: str, output_dir: str) -> str:
    """Return the full HTML path for one competition class's groups."""
    return os.path.join(output_dir, group_html_filename(competition, competition_class))


def export_group_html(
    competition: str,
    competition_class: str,
    groups: dict[int, list],
    snapshots: list[Snapshot],
    output_dir: str,
    run_meta: dict | None = None,
    max_snapshots: int | None = None,
    draw_seconds: float | None = None,
) -> str | None:
    """Write one self-contained HTML file for a competition class's group draw.

    *run_meta* carries the run-wide provenance shown in the footer (version,
    total run time, timestamp, seed), *draw_seconds* the time this one class's
    draw took. Both are optional so the on-demand re-export in group_viewer,
    which runs after the pipeline has finished, still works.

    *max_snapshots* caps the embedded history: the oldest snapshots are
    collapsed into the start state, so the final groups always survive.

    Returns the path written, or None if there was nothing to export.
    """
    if not groups and not snapshots:
        return None

    os.makedirs(output_dir, exist_ok=True)

    payload = _build_group_payload(competition, competition_class, groups, snapshots, max_snapshots=max_snapshots)
    heading = class_display_name(competition, competition_class, "groups")
    # Same provenance as the footer, but machine-readable for anything that
    # parses the embedded JSON instead of the rendered page.
    payload["meta"] = {
        "version": (run_meta or {}).get("version", __version__),
        "draw_seconds": draw_seconds,
        "total_seconds": (run_meta or {}).get("total_seconds"),
        "generated_at": (run_meta or {}).get("generated_at"),
        "random_seed": (run_meta or {}).get("random_seed"),
        "total_snapshots": payload["total_snapshots"],
        "first_snapshot_index": payload["first_snapshot_index"],
    }
    cards_markup = _render_group_cards(list(payload["initial"].keys()), payload["max_group_size"])
    footer_markup = render_footer(heading, draw_seconds, run_meta)
    document = _render_html_document(heading, payload, cards_markup, footer_markup)

    path = group_html_path(competition, competition_class, output_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(document)
    return path
