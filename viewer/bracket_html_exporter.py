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

from viewer.bracket_viewer import participant_display_fields


def _match_quarter(match_idx, number_of_matches):
    """Return the quarter index (0-3) for a 1-based first-round match index.

    Mirrors draw/bracket_drawer.py::slot_quarter so the viewer's Q1-Q4 grouping
    matches the quarter geometry the draw algorithm actually used.
    """
    return min(3, (match_idx - 1) // max(1, number_of_matches // 4))


def _participant_key(p):
    """Stable identity key for a participant, independent of object id()/deepcopy."""
    if p is None or p == "BYE":
        return None
    key = str(p.start_number_a)
    if getattr(p, 'start_number_b', None) is not None:
        key += "/" + str(p.start_number_b)
    return key


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
        gp = getattr(p, 'group_pos', None)
        seed = getattr(p, 'seeding', None)
        return (gp if gp is not None else 999, -(seed if seed is not None else 0))

    sorted_participants = sorted(all_participants, key=sort_key)
    return {_participant_key(p) for p in sorted_participants[:top_count]}


def _serialize_participant(p):
    """Serialize one participant slot to a JSON-safe value for the embedded payload."""
    fields = participant_display_fields(p)
    if fields is None or fields in ("BYE", "ERR"):
        return fields
    return {
        "key": "/".join(
            str(name.get("start_number", name.get("unknown")))
            for name in fields["names"]
        ),
        "seeding": fields["seeding"],
        "group_no": fields["group_no"],
        "group_pos": fields["group_pos"],
        "names": fields["names"],
    }


def _serialize_matches(matches):
    """Serialize matches, padding every match to exactly two slots.

    slots_to_matches (draw/bracket_drawer.py) only appends filled slots, so a
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
            state = snapshot.initial_groups if getattr(snapshot, 'initial_groups', None) is not None else matches
            action = snapshot.action
            violations = snapshot.violations
            violation_score = snapshot.violation_score

        snapshot_entries.append({
            "index": index,
            "action": action,
            "violation_score": violation_score,
            "violations": violations,
            "matches": _serialize_matches(state),
        })

    return {
        "bracket_type": bracket_type,
        "number_of_matches": number_of_matches,
        # Top 25% is computed once from the complete (final) bracket and held
        # constant across every snapshot, so the same strongest players stay
        # green even in early snapshots where few are placed yet.
        "top25_keys": sorted(_top25_keys(matches)),
        "snapshots": snapshot_entries,
    }


def _render_bracket_list(number_of_matches):
    """Emit the static first-round list, grouped into Q1-Q4 quarter sections.

    Each slot row has id="slot-{pos}" and an empty .name span; the JS fills text
    and toggles highlight classes per snapshot. Quarter grouping is static
    structure (participants change across snapshots, quarter membership does not).
    """
    if number_of_matches == 0:
        return '<div class="bracket-list"></div>'

    # Group 1-based match indices by quarter, preserving order.
    quarters = {}
    for match_idx in range(1, number_of_matches + 1):
        quarters.setdefault(_match_quarter(match_idx, number_of_matches), []).append(match_idx)

    sections = []
    for quarter in sorted(quarters):
        rows = []
        for match_idx in quarters[quarter]:
            slots = []
            for side in (0, 1):
                pos = (match_idx - 1) * 2 + side + 1
                slots.append(
                    f'<div class="slot-box" id="slot-{pos}">'
                    f'<span class="pos">{pos}</span><span class="name"></span></div>'
                )
            rows.append(
                f'<div class="match"><span class="match-no">#{match_idx}</span>'
                f'<div class="slots">{"".join(slots)}</div></div>'
            )
        sections.append(
            f'<section class="quarter quarter-{quarter}">'
            f'<div class="quarter-label">Q{quarter + 1}</div>'
            f'<div class="quarter-body">{"".join(rows)}</div></section>'
        )

    return f'<div class="bracket-list">{"".join(sections)}</div>'


_CSS = """
body { font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 0; background: #1e1e1e; color: #ddd; }
.controls {
  position: sticky; top: 0; z-index: 10; background: #262626; padding: 10px 16px;
  border-bottom: 1px solid #444; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.controls button { background: #3a3a3a; color: #eee; border: 1px solid #555; border-radius: 4px; padding: 6px 12px; cursor: pointer; }
.controls button:disabled { opacity: 0.4; cursor: default; }
.controls input[type=number] { width: 70px; background: #1e1e1e; color: #eee; border: 1px solid #555; border-radius: 4px; padding: 5px; }
.meta { margin-left: auto; font-size: 13px; color: #aaa; text-align: right; }
.meta .violations { font-size: 12px; color: #e0a; }

.bracket-list { max-width: 1100px; margin: 0 auto; padding: 20px; }
.quarter { display: flex; align-items: stretch; margin-bottom: 26px; border: 1px solid #3a3a3a; border-radius: 6px; overflow: hidden; }
.quarter-label {
  flex: none; width: 34px; display: flex; align-items: center; justify-content: center;
  font-size: 15px; letter-spacing: 1px; font-weight: bold; background: #333;
  border-right: 1px solid #3a3a3a; writing-mode: vertical-rl; transform: rotate(180deg);
}
.quarter-body { flex: 1; padding: 6px 0; }
.quarter-0 .quarter-label { border-right: 5px solid #4f8cff; }
.quarter-1 .quarter-label { border-right: 5px solid #d98a3d; }
.quarter-2 .quarter-label { border-right: 5px solid #b060d0; }
.quarter-3 .quarter-label { border-right: 5px solid #d0b040; }
.match { display: flex; align-items: stretch; gap: 8px; padding: 6px 12px; }
.match-no { flex: none; width: 44px; color: #777; font-size: 12px; align-self: center; text-align: right; }
.slots { flex: 1; display: flex; flex-direction: column; gap: 3px; }
.slot-box {
  box-sizing: border-box; border: 1px solid #555; border-radius: 4px;
  background: #2b2b2b; display: flex; align-items: center; gap: 8px; padding: 7px 10px; font-size: 13px;
  white-space: nowrap;
}
.pos { color: #888; flex: none; min-width: 34px; }
.name { overflow: hidden; text-overflow: ellipsis; }
.slot-box.bye .name { color: #888; font-style: italic; }
.slot-box.empty { border-style: dashed; }
.slot-box.top25 { background: #1f5d33; border-color: #4ec36e; }
.slot-box.top25 .pos { color: #bfe8c9; }
"""

_JS = """
const DATA = JSON.parse(document.getElementById('bracket-data').textContent);
let currentIndex = DATA.snapshots.length - 1;

function displayString(participant) {
  if (participant === null || participant === undefined) return '';
  if (participant === 'BYE') return 'BYE';
  if (participant === 'ERR') return 'ERR';
  const parts = [];
  if (participant.seeding !== null) parts.push('seed:' + participant.seeding);
  if (participant.group_no !== null) parts.push('G:' + participant.group_no);
  if (participant.group_pos !== null) parts.push('gp:' + participant.group_pos);
  const names = participant.names.map(function (n) {
    if ('unknown' in n) return 'Unknown(' + n.unknown + ')';
    return n.last_name + ' (' + n.start_number + ') [' + n.country + '/' + (n.base ? n.base : '-') + ']';
  }).join(' / ');
  return parts.length ? parts.join(' | ') + ' | ' + names : names;
}

function render(index) {
  const snap = DATA.snapshots[index];
  for (let pos = 1; pos <= DATA.number_of_matches * 2; pos++) {
    const matchIdx = Math.floor((pos - 1) / 2) + 1;
    const side = (pos - 1) % 2;
    const row = snap.matches[String(matchIdx)] || [];
    const participant = row[side] === undefined ? null : row[side];
    const el = document.getElementById('slot-' + pos);
    if (!el) continue;
    el.querySelector('.name').textContent = displayString(participant);
    el.classList.toggle('bye', participant === 'BYE');
    el.classList.toggle('empty', participant === null);
    const isTop25 = participant && typeof participant === 'object' && DATA.top25_keys.includes(participant.key);
    el.classList.toggle('top25', !!isTop25);
  }

  document.getElementById('snapshot-label').textContent =
    'Snapshot ' + (index + 1) + '/' + DATA.snapshots.length + (snap.action ? ' (' + snap.action + ')' : '');
  document.getElementById('score-label').textContent =
    snap.violation_score === null ? '' : 'Violation score: ' + snap.violation_score;
  const violationEntries = Object.entries(snap.violations || {})
    .filter(function (kv) { return kv[1] && (Array.isArray(kv[1]) ? kv[1].length : true); })
    .map(function (kv) { return kv[0] + ': ' + JSON.stringify(kv[1]); });
  document.getElementById('violations-label').textContent = violationEntries.join('  |  ');

  document.getElementById('btn-prev').disabled = index === 0;
  document.getElementById('btn-next').disabled = index === DATA.snapshots.length - 1;
  currentIndex = index;
}

document.getElementById('btn-prev').addEventListener('click', function () {
  if (currentIndex > 0) render(currentIndex - 1);
});
document.getElementById('btn-next').addEventListener('click', function () {
  if (currentIndex < DATA.snapshots.length - 1) render(currentIndex + 1);
});
document.getElementById('btn-improvement').addEventListener('click', function () {
  const startScore = DATA.snapshots[currentIndex].violation_score;
  for (let i = currentIndex + 1; i < DATA.snapshots.length; i++) {
    if (DATA.snapshots[i].violation_score !== null && DATA.snapshots[i].violation_score < startScore) {
      render(i);
      return;
    }
  }
  alert('No next improvement found.');
});
document.getElementById('btn-first').addEventListener('click', function () {
  render(0);
});
document.getElementById('btn-final').addEventListener('click', function () {
  render(DATA.snapshots.length - 1);
});
document.getElementById('btn-jump').addEventListener('click', function () {
  const input = document.getElementById('jump-input');
  const num = parseInt(input.value, 10);
  if (Number.isInteger(num) && num >= 1 && num <= DATA.snapshots.length) {
    render(num - 1);
  } else {
    alert('Enter a valid snapshot number (1-' + DATA.snapshots.length + ').');
  }
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'ArrowLeft') document.getElementById('btn-prev').click();
  if (e.key === 'ArrowRight') document.getElementById('btn-next').click();
});

render(currentIndex);
"""


def _render_html_document(title, payload, list_markup):
    # Escape "</script" so embedded participant data (names/bases from CSV input)
    # can never prematurely close the <script> tag it's embedded in.
    payload_json = json.dumps(payload, default=str).replace("</script", "<\\/script")
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="controls">
  <button id="btn-prev">&larr; Prev</button>
  <button id="btn-next">Next &rarr;</button>
  <button id="btn-first">Show first snapshot</button>
  <button id="btn-improvement">Forward to next improvement</button>
  <button id="btn-final">Show final bracket</button>
  <input type="number" id="jump-input" min="1" placeholder="#">
  <button id="btn-jump">Go to snapshot</button>
  <div class="meta">
    <div id="snapshot-label"></div>
    <div id="score-label"></div>
    <div class="violations" id="violations-label"></div>
  </div>
</div>
{list_markup}
<script type="application/json" id="bracket-data">{payload_json}</script>
<script>{_JS}</script>
</body>
</html>
"""


def bracket_html_filename(competition, competition_class, bracket_type):
    """Return the HTML filename for a single bracket type (shared naming convention)."""
    return f"{competition}_{competition_class}_{bracket_type}_bracket.html"


def bracket_html_path(competition, competition_class, bracket_type, output_dir):
    """Return the full HTML path for a single bracket type."""
    filename = bracket_html_filename(competition, competition_class, bracket_type)
    return os.path.join(output_dir, filename)


def export_bracket_html(competition, competition_class, bracket, output_dir):
    """Write one self-contained HTML file per bracket type present in *bracket*.

    Returns the list of file paths written.
    """
    os.makedirs(output_dir, exist_ok=True)
    written = []

    for bracket_type in ('main', 'consolation'):
        selected = bracket.get(bracket_type)
        if not selected or not selected.get('matches'):
            continue

        matches = selected['matches']
        snapshots = selected.get('snapshots', [])
        payload = _build_bracket_payload(bracket_type, matches, snapshots)
        list_markup = _render_bracket_list(payload["number_of_matches"])
        title = f"{competition} {competition_class} {bracket_type.capitalize()} Bracket"
        document = _render_html_document(title, payload, list_markup)

        path = bracket_html_path(competition, competition_class, bracket_type, output_dir)
        with open(path, "w", encoding="utf-8") as f:
            f.write(document)
        written.append(path)

    return written
