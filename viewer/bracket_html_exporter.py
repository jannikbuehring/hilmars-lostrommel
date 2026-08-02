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
from datetime import datetime

from misc.version import APP_NAME, __version__
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
.class-title { font-size: 15px; font-weight: bold; color: #eee; margin-right: 8px; }
.meta { margin-left: auto; font-size: 13px; color: #aaa; text-align: right; }
.meta .violations { font-size: 12px; color: #e0a; }
.export-meta {
  max-width: 1100px; margin: 0 auto; padding: 12px 20px 24px;
  border-top: 1px solid #333; font-size: 12px; color: #777;
}

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
/* Metadata columns. Their widths are measured once at load (widest value in the
   whole history) and written to --col-* , so every row's columns line up no
   matter how many digits a value has. */
.fld { display: inline-block; }
.fld-seeding { width: var(--col-seeding, auto); }
.fld-group_no { width: var(--col-group_no, auto); }
.fld-group_pos { width: var(--col-group_pos, auto); }
.measure-probe { position: absolute; visibility: hidden; top: -9999px; left: -9999px; white-space: nowrap; }
.slot-box.bye .name { color: #888; font-style: italic; }
.slot-box.empty { border-style: dashed; }
.slot-box.top25 { background: #1f5d33; border-color: #4ec36e; }
.slot-box.top25 .pos { color: #bfe8c9; }
.slot-box.changed { animation: flash 1.1s ease-out; }
@keyframes flash {
  0% { box-shadow: 0 0 0 3px #ffd54a, 0 0 14px 4px #ffd54a; border-color: #ffd54a; }
  100% { box-shadow: 0 0 0 0 rgba(255,213,74,0); }
}
.controls label { font-size: 13px; color: #aaa; display: flex; align-items: center; gap: 4px; }
"""

_JS = """
const DATA = JSON.parse(document.getElementById('bracket-data').textContent);
let currentIndex = DATA.snapshots.length - 1;

const FIELD_LABELS = { seeding: 'Seed: ', group_no: 'G: ', group_pos: 'P: ' };
const COLUMN_GAP_PX = 18;

function fieldText(participant, field) {
  const value = participant[field];
  return (value === null || value === undefined) ? '' : FIELD_LABELS[field] + value;
}

function participantNames(participant) {
  return participant.names.map(function (n) {
    if ('unknown' in n) return 'Unknown(' + n.unknown + ')';
    const full = (n.first_name ? n.first_name + ' ' : '') + n.last_name;
    return '[' + n.country + '/' + (n.base ? n.base : '-') + '] ' + full + ' (' + n.start_number + ')';
  }).join(' / ');
}

// Fields that occur at least once anywhere in the history get a column; a field
// that is always null (e.g. no seeding at all) is dropped entirely.
const ACTIVE_FIELDS = (function () {
  const seen = {};
  DATA.snapshots.forEach(function (snap) {
    Object.keys(snap.matches).forEach(function (matchIdx) {
      snap.matches[matchIdx].forEach(function (p) {
        if (!p || typeof p !== 'object') return;
        Object.keys(FIELD_LABELS).forEach(function (field) {
          if (p[field] !== null && p[field] !== undefined) seen[field] = true;
        });
      });
    });
  });
  return Object.keys(FIELD_LABELS).filter(function (field) { return seen[field]; });
})();

// Measure the widest value each column ever holds and pin the column to that
// width (plus a gap), so a two-digit value can never push the columns after it
// out of line — the tabulated look, but robust for any value length.
function measureColumnWidths() {
  const probe = document.createElement('div');
  probe.className = 'slot-box measure-probe';
  const inner = document.createElement('span');
  inner.className = 'name';
  probe.appendChild(inner);
  document.body.appendChild(probe);

  const widest = {};
  DATA.snapshots.forEach(function (snap) {
    Object.keys(snap.matches).forEach(function (matchIdx) {
      snap.matches[matchIdx].forEach(function (p) {
        if (!p || typeof p !== 'object') return;
        ACTIVE_FIELDS.forEach(function (field) {
          const text = fieldText(p, field);
          inner.textContent = text;
          const width = inner.getBoundingClientRect().width;
          if (!(field in widest) || width > widest[field]) widest[field] = width;
        });
      });
    });
  });

  ACTIVE_FIELDS.forEach(function (field) {
    document.documentElement.style.setProperty(
      '--col-' + field, Math.ceil(widest[field] || 0) + COLUMN_GAP_PX + 'px');
  });
  document.body.removeChild(probe);
}

// Fill a slot's .name with one span per metadata column plus the player span.
// Plain strings (BYE/ERR/empty) are written as-is, without columns.
function renderName(el, participant) {
  el.textContent = '';
  if (participant === null || participant === undefined) return;
  if (typeof participant === 'string') {
    el.textContent = participant;
    return;
  }
  ACTIVE_FIELDS.forEach(function (field) {
    const span = document.createElement('span');
    span.className = 'fld fld-' + field;
    span.textContent = fieldText(participant, field);
    el.appendChild(span);
  });
  const players = document.createElement('span');
  players.className = 'players';
  players.textContent = participantNames(participant);
  el.appendChild(players);
}

function slotParticipant(snap, pos) {
  const matchIdx = Math.floor((pos - 1) / 2) + 1;
  const side = (pos - 1) % 2;
  const row = snap.matches[String(matchIdx)] || [];
  return row[side] === undefined ? null : row[side];
}

function slotIdentity(participant) {
  if (participant === null || participant === undefined) return '';
  if (typeof participant === 'string') return participant;
  return participant.key;
}

// Positions whose occupant differs between two snapshots. Newly-filled slots
// (an empty/BYE side that now holds a real participant) are listed first, so
// stepping forward jumps straight to the insert the step introduced.
function changedSlots(fromSnap, toSnap) {
  const inserts = [];
  const others = [];
  for (let pos = 1; pos <= DATA.number_of_matches * 2; pos++) {
    const before = slotIdentity(slotParticipant(fromSnap, pos));
    const after = slotIdentity(slotParticipant(toSnap, pos));
    if (before === after) continue;
    const afterP = slotParticipant(toSnap, pos);
    if (afterP && typeof afterP === 'object') inserts.push(pos);
    else others.push(pos);
  }
  return inserts.concat(others);
}

function render(index) {
  const prevSnap = DATA.snapshots[currentIndex];
  const snap = DATA.snapshots[index];
  const changed = index === currentIndex ? [] : changedSlots(prevSnap, snap);
  for (let pos = 1; pos <= DATA.number_of_matches * 2; pos++) {
    const matchIdx = Math.floor((pos - 1) / 2) + 1;
    const side = (pos - 1) % 2;
    const row = snap.matches[String(matchIdx)] || [];
    const participant = row[side] === undefined ? null : row[side];
    const el = document.getElementById('slot-' + pos);
    if (!el) continue;
    renderName(el.querySelector('.name'), participant);
    el.classList.toggle('bye', participant === 'BYE');
    el.classList.toggle('empty', participant === null);
    const isTop25 = participant && typeof participant === 'object' && DATA.top25_keys.includes(participant.key);
    el.classList.toggle('top25', !!isTop25);
    el.classList.remove('changed');
  }

  if (changed.length) {
    // Re-trigger the flash animation reliably by forcing a reflow first.
    changed.forEach(function (pos) {
      const el = document.getElementById('slot-' + pos);
      if (!el) return;
      void el.offsetWidth;
      el.classList.add('changed');
    });
    if (document.getElementById('auto-scroll').checked) {
      const target = document.getElementById('slot-' + changed[0]);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
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

measureColumnWidths();
render(currentIndex);
"""


_COMPETITION_NAMES = {"S": "Singles", "D": "Doubles", "M": "Mixed"}
_CLASS_GENDER_NAMES = {"M": "Men", "W": "Women", "X": "Mixed"}


def _class_display_name(competition, competition_class, bracket_type):
    """Human-readable class heading, e.g. ("S", "M1", "main") -> "Singles Men 1 Main".

    Falls back to the raw codes for any competition/class shape not covered by
    the maps, so an unexpected class code still produces a usable heading.
    """
    competition_name = _COMPETITION_NAMES.get(competition, competition)
    class_name = competition_class
    if len(competition_class) >= 2 and competition_class[0] in _CLASS_GENDER_NAMES:
        gender_name = _CLASS_GENDER_NAMES[competition_class[0]]
        # Mixed classes ("X") inside the Mixed competition would read
        # "Mixed Mixed 1"; drop the redundant repetition.
        prefix = "" if gender_name == competition_name else f"{gender_name} "
        class_name = f"{prefix}{competition_class[1:]}"
    return f"{competition_name} {class_name} {bracket_type.capitalize()}"


def _format_duration(seconds):
    """Human-readable duration, or None if no duration was recorded."""
    if seconds is None:
        return None
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)} min {remainder:.1f} s"


def _render_footer(heading, draw_seconds, run_meta):
    """Provenance line below the bracket: which build produced this file, when,
    and how long it took.

    *run_meta* is absent when the exporter runs outside the initialization
    pipeline (the on-demand re-export in bracket_viewer), so every part is
    optional and simply omitted when its value is missing.
    """
    meta = run_meta or {}
    version = meta.get('version', __version__)

    parts = [f"{APP_NAME} v{version}"]

    draw_text = _format_duration(draw_seconds)
    if draw_text:
        parts.append(f"{heading} drawn in {draw_text}")

    total_text = _format_duration(meta.get('total_seconds'))
    if total_text:
        parts.append(f"total run {total_text}")

    seed = meta.get('random_seed')
    if seed:
        parts.append(f"seed {seed}")

    parts.append(f"generated {meta.get('generated_at') or datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return f'<footer class="export-meta">{html.escape(" · ".join(str(p) for p in parts))}</footer>'


def _render_html_document(title, heading, payload, list_markup, footer_markup):
    # Escape "</script" so embedded participant data (names/bases from CSV input)
    # can never prematurely close the <script> tag it's embedded in.
    payload_json = json.dumps(payload, default=str).replace("</script", "<\\/script")
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="generator" content="{html.escape(f'{APP_NAME} {__version__}')}">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="controls">
  <span class="class-title">{html.escape(heading)}</span>
  <button id="btn-prev">&larr; Prev</button>
  <button id="btn-next">Next &rarr;</button>
  <button id="btn-first">Show first snapshot</button>
  <button id="btn-improvement">Forward to next improvement</button>
  <button id="btn-final">Show final bracket</button>
  <input type="number" id="jump-input" min="1" placeholder="#">
  <button id="btn-jump">Go to snapshot</button>
  <label><input type="checkbox" id="auto-scroll" checked> Scroll to change</label>
  <div class="meta">
    <div id="snapshot-label"></div>
    <div id="score-label"></div>
    <div class="violations" id="violations-label"></div>
  </div>
</div>
{list_markup}
{footer_markup}
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


def export_bracket_html(competition, competition_class, bracket, output_dir, run_meta=None):
    """Write one self-contained HTML file per bracket type present in *bracket*.

    *run_meta* carries the run-wide provenance shown in each file's footer
    (version, total run time, timestamp, seed). It is optional so the on-demand
    re-export in bracket_viewer, which runs after the pipeline has finished,
    still works with whatever metadata the bracket dict itself carries.

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
        draw_seconds = selected.get('draw_seconds')
        payload = _build_bracket_payload(bracket_type, matches, snapshots)
        list_markup = _render_bracket_list(payload["number_of_matches"])
        heading = _class_display_name(competition, competition_class, bracket_type)
        title = f"{heading} Bracket"
        # Same provenance as the footer, but machine-readable for anything that
        # parses the embedded JSON instead of the rendered page.
        payload["meta"] = {
            "version": (run_meta or {}).get('version', __version__),
            "draw_seconds": draw_seconds,
            "total_seconds": (run_meta or {}).get('total_seconds'),
            "generated_at": (run_meta or {}).get('generated_at'),
            "random_seed": (run_meta or {}).get('random_seed'),
        }
        footer_markup = _render_footer(heading, draw_seconds, run_meta)
        document = _render_html_document(title, heading, payload, list_markup, footer_markup)

        path = bracket_html_path(competition, competition_class, bracket_type, output_dir)
        with open(path, "w", encoding="utf-8") as f:
            f.write(document)
        written.append(path)

    return written
