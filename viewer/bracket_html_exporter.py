"""Export a bracket (with full snapshot history) to a self-contained HTML file.

The exported file renders the bracket's first round as a quarter-grouped
(Q1-Q4) list and embeds every recorded Snapshot as JSON so the page can step
through the draw algorithm's history entirely offline, with no server and no
network requests. Only first-round pairings are real data (this app never
simulates match winners), so no later-round tree is drawn.
"""

import html
import json
import os

from core.version import APP_NAME, __version__
from models.bracket_geometry import BracketGeometry
from viewer.viewer_shared import (
    class_display_name,
    participant_display_fields,
    participant_key,
    read_asset,
    render_footer,
)


def _top25_keys(first_round_matches):
    """Return the set of stable participant keys for the strongest 25% of players.

    Ranking: group_pos ascending (1 = group winner is best), then seeding
    descending. Sized to 25% of bracket slots (including BYE slots), so a
    16-slot bracket always highlights its 4 strongest players regardless of how
    many byes it contains. BYEs are never in the candidate list, so when byes
    are numerous enough that the 25% count exceeds the real-player total, only
    the real players get highlighted (byes are never colored). Keyed by
    start_number instead of id(), so it stays correct across snapshots (each
    snapshot's matches is a separate copy.deepcopy, which invalidates
    id()-based identity).
    """
    all_participants = []
    for participants in first_round_matches.values():
        for p in participants:
            if p is not None and p != "BYE":
                all_participants.append(p)

    top_count = (len(first_round_matches) * 2) // 4

    def sort_key(p):
        gp = getattr(p, "group_pos", None)
        seed = getattr(p, "seeding", None)
        return (gp if gp is not None else 999, -(seed if seed is not None else 0))

    sorted_participants = sorted(all_participants, key=sort_key)
    return {participant_key(p) for p in sorted_participants[:top_count]}


def _serialize_participant(p):
    """Serialize one participant slot to a JSON-safe value for the embedded payload."""
    fields = participant_display_fields(p)
    if fields is None or fields in ("BYE", "ERR"):
        return fields
    return {
        "key": "/".join(str(name.get("start_number", name.get("unknown"))) for name in fields["names"]),
        "seeding": fields["seeding"],
        "group_no": fields["group_no"],
        "group_pos": fields["group_pos"],
        "names": fields["names"],
    }


def _serialize_matches(matches):
    """Serialize matches, padding every match to exactly two slots.

    slots_to_matches (draw/bracket/state.py) only appends filled slots, so a
    partially-drawn match can be [] or length 1. Padding to two None slots
    guarantees the JS renderer always finds both sides and never indexes past
    the array (which would otherwise crash render() on partial/phase-1 draws).
    """
    serialized = {}
    for match_idx, participants in matches.items():
        sides = [_serialize_participant(p) for p in participants]
        while len(sides) < 2:
            sides.append(None)
        serialized[str(match_idx)] = sides
    return serialized


def _build_bracket_payload(bracket_type, matches, snapshots):
    """Build the JSON-serializable payload embedded in the exported HTML."""
    number_of_matches = len(matches)

    snapshot_entries = []
    source_snapshots = snapshots if snapshots else [None]
    for index, snapshot in enumerate(source_snapshots):
        if snapshot is None:
            state = matches
            action = None
            violations = {}
            violation_score = None
        else:
            state = snapshot.state if getattr(snapshot, "state", None) is not None else matches
            action = snapshot.action
            violations = snapshot.violations
            violation_score = snapshot.violation_score

        snapshot_entries.append(
            {
                "index": index,
                "action": action,
                "violation_score": violation_score,
                "violations": violations,
                "matches": _serialize_matches(state),
            }
        )

    return {
        "bracket_type": bracket_type,
        "number_of_matches": number_of_matches,
        # Top 25% is computed once from the complete (final) bracket and held
        # constant across every snapshot, so the same strongest players stay
        # green even in early snapshots where few are placed yet.
        "top25_keys": sorted(_top25_keys(matches)),
        "snapshots": snapshot_entries,
    }


# Brackets bigger than this get a second side bar splitting each quarter into
# fixed-size segments, so long quarters stay easy to navigate.
SEGMENT_THRESHOLD_PLAYERS = 64
SEGMENT_PLAYERS = 16


def _render_match_row(match_idx):
    slots = []
    for side in (0, 1):
        pos = (match_idx - 1) * 2 + side + 1
        slots.append(
            f'<div class="slot-box" id="slot-{pos}"><span class="pos">{pos}</span><span class="name"></span></div>'
        )
    return (
        f'<div class="match"><span class="match-no">#{match_idx}</span><div class="slots">{"".join(slots)}</div></div>'
    )


def _render_bracket_list(number_of_matches):
    """Emit the static first-round list, grouped into Q1-Q4 quarter sections.

    Brackets with more than SEGMENT_THRESHOLD_PLAYERS players additionally get a
    second side bar right of the quarter bar, splitting the bracket into
    segments of SEGMENT_PLAYERS players labelled "k / N" (numbered across the
    whole bracket).

    Each slot row has id="slot-{pos}" and an empty .name span; the JS fills text
    and toggles highlight classes per snapshot. Quarter grouping is static
    structure (participants change across snapshots, quarter membership does not).
    """
    if number_of_matches == 0:
        return '<div class="bracket-list"></div>'

    # Group 1-based match indices by quarter, preserving order.
    # Same quarter geometry the draw algorithm used.
    geo = BracketGeometry(number_of_matches)
    quarters = {}
    for match_idx in range(1, number_of_matches + 1):
        quarters.setdefault(geo.match_quarter(match_idx), []).append(match_idx)

    use_segments = 2 * number_of_matches > SEGMENT_THRESHOLD_PLAYERS
    matches_per_segment = SEGMENT_PLAYERS // 2
    total_segments = -(-number_of_matches // matches_per_segment)

    sections = []
    for quarter in sorted(quarters):
        if use_segments:
            segments = {}
            for match_idx in quarters[quarter]:
                segments.setdefault((match_idx - 1) // matches_per_segment, []).append(match_idx)
            body = "".join(
                f'<div class="segment">'
                f'<div class="segment-label">{segment + 1} / {total_segments}</div>'
                f'<div class="segment-body">{"".join(_render_match_row(m) for m in segments[segment])}</div>'
                f"</div>"
                for segment in sorted(segments)
            )
            body_class = "quarter-body segmented"
        else:
            body = "".join(_render_match_row(m) for m in quarters[quarter])
            body_class = "quarter-body"
        sections.append(
            f'<section class="quarter quarter-{quarter}">'
            f'<div class="quarter-label">Q{quarter + 1}</div>'
            f'<div class="{body_class}">{body}</div></section>'
        )

    return f'<div class="bracket-list">{"".join(sections)}</div>'


def _quality_notice(quality):
    """Operator warning for a degraded or rule-breaking bracket, or None.

    *quality* is `draw.bracket.bracket_quality`'s dict, stored in the bracket
    dict by the pipeline; the viewer's fallback re-export may not carry it.
    """
    if not quality or quality.get("failed"):
        return None
    parts = []
    if quality.get("degraded"):
        parts.append("Best-effort layout (degraded)")
    hard_count = sum(len(v) for v in quality.get("hard", {}).values())
    if hard_count:
        parts.append(f"{hard_count} hard-rule violation{'s' if hard_count != 1 else ''}")
    bye_order_count = len(quality.get("bye_order", []))
    if bye_order_count:
        parts.append(f"byes out of seeding order ({bye_order_count} pair{'s' if bye_order_count != 1 else ''})")
    balance = quality.get("balance", [])
    if balance:
        parts.append(f"unbalanced halves ({', '.join(balance)})")
    forced_count = len(quality.get("forced", {}).get("first_vs_first_forced", []))
    if forced_count:
        parts.append(
            f"{forced_count} unavoidable first-vs-first "
            f"match{'es' if forced_count != 1 else ''} (more group winners than matches)"
        )
    return " · ".join(parts) or None


def _render_html_document(title, heading, payload, list_markup, footer_markup, notice=None):
    # Escape "</script" so embedded participant data (names/bases from CSV input)
    # can never prematurely close the <script> tag it's embedded in.
    payload_json = json.dumps(payload, default=str).replace("</script", "<\\/script")
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="generator" content="{html.escape(f"{APP_NAME} {__version__}")}">
<title>{html.escape(title)}</title>
<style>
{read_asset("bracket.css")}</style>
</head>
<body>
<div class="controls">
  <span class="class-title">{html.escape(heading)}</span>
  {f'<span class="quality-notice">{html.escape(notice)}</span>' if notice else ""}
  <button id="btn-prev">&larr; Prev</button>
  <button id="btn-next">Next &rarr;</button>
  <button id="btn-first">Show first snapshot</button>
  <button id="btn-improvement">Forward to next improvement</button>
  <button id="btn-final">Show final bracket</button>
  <input type="number" id="jump-input" min="1" placeholder="#">
  <button id="btn-jump">Go to snapshot</button>
  <label><input type="checkbox" id="auto-scroll" checked> Scroll to change</label>
  <label><input type="checkbox" id="show-violations"> Show violation details</label>
  <div class="meta">
    <div id="snapshot-label"></div>
    <div id="score-label"></div>
    <div class="violations" id="violations-label"></div>
  </div>
</div>
{list_markup}
{footer_markup}
<script type="application/json" id="bracket-data">{payload_json}</script>
<script>
{read_asset("bracket.js")}</script>
</body>
</html>
"""


def bracket_html_filename(competition: str, competition_class: str, bracket_type: str) -> str:
    """Return the HTML filename for a single bracket type (shared naming convention)."""
    return f"{competition}_{competition_class}_{bracket_type}_bracket.html"


def bracket_html_path(competition: str, competition_class: str, bracket_type: str, output_dir: str) -> str:
    """Return the full HTML path for a single bracket type."""
    filename = bracket_html_filename(competition, competition_class, bracket_type)
    return os.path.join(output_dir, filename)


def export_bracket_html(
    competition: str, competition_class: str, bracket: dict, output_dir: str, run_meta: dict | None = None
) -> list[str]:
    """Write one self-contained HTML file per bracket type present in *bracket*.

    *run_meta* carries the run-wide provenance shown in each file's footer
    (version, total run time, timestamp, seed). It is optional so the on-demand
    re-export in bracket_viewer, which runs after the pipeline has finished,
    still works with whatever metadata the bracket dict itself carries.

    Returns the list of file paths written.
    """
    os.makedirs(output_dir, exist_ok=True)
    written = []

    for bracket_type in ("main", "consolation"):
        selected = bracket.get(bracket_type)
        if not selected or not selected.get("matches"):
            continue

        matches = selected["matches"]
        snapshots = selected.get("snapshots", [])
        draw_seconds = selected.get("draw_seconds")
        payload = _build_bracket_payload(bracket_type, matches, snapshots)
        list_markup = _render_bracket_list(payload["number_of_matches"])
        heading = class_display_name(competition, competition_class, bracket_type)
        title = f"{heading} Bracket"
        # Same provenance as the footer, but machine-readable for anything that
        # parses the embedded JSON instead of the rendered page.
        payload["meta"] = {
            "version": (run_meta or {}).get("version", __version__),
            "draw_seconds": draw_seconds,
            "total_seconds": (run_meta or {}).get("total_seconds"),
            "generated_at": (run_meta or {}).get("generated_at"),
            "random_seed": (run_meta or {}).get("random_seed"),
        }
        notice = _quality_notice(selected.get("quality"))
        if notice:
            payload["meta"]["quality"] = notice
        footer_markup = render_footer(heading, draw_seconds, run_meta)
        document = _render_html_document(title, heading, payload, list_markup, footer_markup, notice=notice)

        path = bracket_html_path(competition, competition_class, bracket_type, output_dir)
        with open(path, "w", encoding="utf-8") as f:
            f.write(document)
        written.append(path)

    return written
