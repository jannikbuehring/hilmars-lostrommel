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
viewer/group_viewer.py::display_snapshot replays them in Python.
"""
import html
import json
import os

from misc.version import APP_NAME, __version__
from draw.group_drawer import EmptySlot
from viewer.viewer_shared import participant_display_fields
# Shared with the bracket export so both files carry an identical heading and
# provenance footer.
from viewer.bracket_html_exporter import (
    _class_display_name,
    _participant_key,
    _render_footer,
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
    if getattr(p, 'start_number_a', None) == "EMPTY":
        return None
    return _participant_key(p)


def _roster_entry(p):
    """Serialize one participant for the roster (stored once, not per snapshot)."""
    fields = participant_display_fields(p, include_qttr=True)
    if fields is None or fields in ("BYE", "ERR"):
        return {"seeding": None, "names": []}
    return {"seeding": fields["seeding"], "names": fields["names"]}


def _apply_snapshot(state, snapshot, forward=True):
    """Apply one snapshot's delta to *state* (dict of group_no -> list of keys).

    Mirrors viewer/group_viewer.py::display_snapshot: a "swap" put p2 where p1
    was and vice versa, a "revert" put them back. Going backward is the inverse
    assignment. Used here to fast-forward the truncated head of a long history;
    the exported JS applies the identical rule.
    """
    action = getattr(snapshot, 'action', None)
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
    initial_groups = getattr(snapshots[0], 'initial_groups', None) if snapshots else None
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
        for snapshot in snapshots[1:first_index + 1]:
            _apply_snapshot(state, snapshot, forward=True)

    steps = []
    for snapshot in snapshots[first_index:]:
        for p in (snapshot.participants or []):
            register(p)
        step = {
            "a": getattr(snapshot, 'action', None),
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
            f'{"".join(rows)}</section>'
        )

    return f'<div class="groups">{"".join(cards)}</div>'


_CSS = """
body { font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 0; background: #1e1e1e; color: #ddd; }
.controls {
  position: sticky; top: 0; z-index: 10; background: #262626; padding: 10px 16px;
  border-bottom: 1px solid #444; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.controls button { background: #3a3a3a; color: #eee; border: 1px solid #555; border-radius: 4px; padding: 6px 12px; cursor: pointer; }
.controls button:disabled { opacity: 0.4; cursor: default; }
.controls input[type=number] { width: 70px; background: #1e1e1e; color: #eee; border: 1px solid #555; border-radius: 4px; padding: 5px; }
.controls label { font-size: 13px; color: #aaa; display: flex; align-items: center; gap: 4px; }
.class-title { font-size: 15px; font-weight: bold; color: #eee; margin-right: 8px; }
.meta { margin-left: auto; font-size: 13px; color: #aaa; text-align: right; }
.meta .violations { font-size: 12px; color: #e0a; }
.meta .truncated { font-size: 12px; color: #d9a441; }
.export-meta {
  max-width: 1400px; margin: 0 auto; padding: 12px 20px 24px;
  border-top: 1px solid #333; font-size: 12px; color: #777;
}

/* One card per row: scrolling down is preferable to columns being cut off. */
.groups {
  max-width: 1400px; margin: 0 auto; padding: 20px;
  display: grid; grid-template-columns: 1fr; gap: 22px;
}
.group-card { border: 1px solid #3a3a3a; border-radius: 6px; overflow-x: auto; background: #242424; }
.group-label {
  font-size: 14px; font-weight: bold; letter-spacing: 0.5px;
  background: #333; padding: 7px 12px; border-bottom: 1px solid #3a3a3a;
}
/* One shared grid template for the header and every slot row, so the columns
   line up down the whole card whatever the values are. The two text-heavy
   columns are fr tracks, whose implicit auto minimum means they never shrink
   below their content: a very long value widens the row (and the card scrolls)
   instead of being truncated. */
.row {
  display: grid; grid-template-columns: 34px 60px 3fr 110px 2fr 70px;
  gap: 22px; align-items: center; padding: 7px 16px; font-size: 13px;
  border-top: 1px solid #2f2f2f; white-space: nowrap;
}
.row:first-of-type { border-top: none; }
.row.head { color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; background: #2a2a2a; }
.row .pos { color: #888; }
.row .seed, .row .qttr { color: #bbb; }
.row.empty { color: #666; font-style: italic; }
.row.changed { animation: flash 1.1s ease-out; }
@keyframes flash {
  0% { box-shadow: inset 0 0 0 2px #ffd54a; background: #4a3f18; }
  100% { box-shadow: inset 0 0 0 0 rgba(255,213,74,0); background: transparent; }
}
"""

_JS = """
const DATA = JSON.parse(document.getElementById('group-data').textContent);
const GROUP_NUMBERS = Object.keys(DATA.initial);

// Live state: group -> array of roster keys (or null for an empty slot).
// Steps are applied one at a time on top of it, never recomputed from scratch.
let state = {};
GROUP_NUMBERS.forEach(function (g) { state[g] = DATA.initial[g].slice(); });
let currentIndex = 0;

// Apply one step's delta. Mirrors group_html_exporter._apply_snapshot (and the
// terminal viewer): a "swap" put p2 where p1 was, a "revert" put them back;
// going backward is the inverse assignment. Returns the touched slots.
function applyStep(step, forward) {
  if (step.a !== 'swap' && step.a !== 'revert') return [];
  const g1 = String(step.g[0]);
  const g2 = String(step.g[1]);
  const i = step.i;
  const first = (step.a === 'swap') === forward ? [step.p[1], step.p[0]] : [step.p[0], step.p[1]];
  state[g1][i] = first[0];
  state[g2][i] = first[1];
  return [g1 + '-' + i, g2 + '-' + i];
}

function goTo(index) {
  const touched = [];
  while (currentIndex < index) {
    currentIndex++;
    applyStep(DATA.steps[currentIndex], true).forEach(function (s) { touched.push(s); });
  }
  while (currentIndex > index) {
    applyStep(DATA.steps[currentIndex], false).forEach(function (s) { touched.push(s); });
    currentIndex--;
  }
  return touched;
}

function joinField(participant, pick) {
  return participant.names.map(pick).join(' / ');
}

function playerLabel(n) {
  if ('unknown' in n) return 'Unknown(' + n.unknown + ')';
  const name = n.first_name ? n.last_name + ', ' + n.first_name : n.last_name;
  return name + ' (' + n.start_number + ')';
}

function renderSlot(group, index) {
  const el = document.getElementById('slot-' + group + '-' + index);
  if (!el) return;
  const key = state[group][index];
  const participant = key === null || key === undefined ? null : DATA.roster[key];
  el.classList.toggle('empty', !participant);
  const set = function (cls, text) { el.querySelector('.' + cls).textContent = text; };
  if (!participant) {
    set('seed', ''); set('names', '-'); set('country', ''); set('base', ''); set('qttr', '');
    return;
  }
  set('seed', participant.seeding === null || participant.seeding === undefined ? '' : participant.seeding);
  set('names', joinField(participant, playerLabel));
  set('country', joinField(participant, function (n) { return n.country || '-'; }));
  set('base', joinField(participant, function (n) { return n.base ? n.base : '-'; }));
  set('qttr', joinField(participant, function (n) {
    return (n.qttr === null || n.qttr === undefined || n.qttr === '') ? '-' : n.qttr;
  }));
}

function renderAll() {
  GROUP_NUMBERS.forEach(function (g) {
    for (let i = 0; i < DATA.max_group_size; i++) renderSlot(g, i);
  });
}

// The per-rule violation breakdown is debug output, hidden unless the checkbox is
// ticked. Split out of render() so toggling it repaints only this label -- a full
// render() would clear the 'changed' flash of the step the user just took.
function renderViolations(step) {
  const show = document.getElementById('show-violations').checked;
  const entries = !show ? [] : Object.entries(step.v || {})
    .filter(function (kv) { return kv[1] && (Array.isArray(kv[1]) ? kv[1].length : true); })
    .map(function (kv) { return kv[0] + ': ' + JSON.stringify(kv[1]); });
  document.getElementById('violations-label').textContent = entries.join('  |  ');
}

function snapshotNumber(index) {
  return DATA.first_snapshot_index + index + 1;
}

function render(index, silent) {
  const changed = goTo(index);
  const touched = silent ? [] : changed;
  renderAll();
  document.querySelectorAll('.row.changed').forEach(function (el) { el.classList.remove('changed'); });

  if (touched.length) {
    // Re-trigger the flash animation reliably by forcing a reflow first.
    touched.forEach(function (slot) {
      const el = document.getElementById('slot-' + slot);
      if (!el) return;
      void el.offsetWidth;
      el.classList.add('changed');
    });
    if (document.getElementById('auto-scroll').checked) {
      const target = document.getElementById('slot-' + touched[0]);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  const step = DATA.steps[index];
  document.getElementById('snapshot-label').textContent =
    'Snapshot ' + snapshotNumber(index) + '/' + DATA.total_snapshots + (step.a ? ' (' + step.a + ')' : '');
  document.getElementById('score-label').textContent =
    step.s === null || step.s === undefined ? '' : 'Violation score: ' + step.s;
  renderViolations(step);

  document.getElementById('btn-prev').disabled = index === 0;
  document.getElementById('btn-next').disabled = index === DATA.steps.length - 1;
}

document.getElementById('btn-prev').addEventListener('click', function () {
  if (currentIndex > 0) render(currentIndex - 1);
});
document.getElementById('btn-next').addEventListener('click', function () {
  if (currentIndex < DATA.steps.length - 1) render(currentIndex + 1);
});
document.getElementById('btn-improvement').addEventListener('click', function () {
  const startScore = DATA.steps[currentIndex].s;
  for (let i = currentIndex + 1; i < DATA.steps.length; i++) {
    if (DATA.steps[i].s !== null && DATA.steps[i].s < startScore) {
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
  render(DATA.steps.length - 1);
});
document.getElementById('btn-jump').addEventListener('click', function () {
  const input = document.getElementById('jump-input');
  const num = parseInt(input.value, 10);
  const lowest = snapshotNumber(0);
  if (Number.isInteger(num) && num >= lowest && num <= DATA.total_snapshots) {
    render(num - 1 - DATA.first_snapshot_index);
  } else {
    alert('Enter a valid snapshot number (' + lowest + '-' + DATA.total_snapshots + ').');
  }
});
document.getElementById('show-violations').addEventListener('change', function () {
  renderViolations(DATA.steps[currentIndex]);
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'ArrowLeft') document.getElementById('btn-prev').click();
  if (e.key === 'ArrowRight') document.getElementById('btn-next').click();
});

if (DATA.first_snapshot_index > 0) {
  document.getElementById('truncated-label').textContent =
    'History truncated to the last ' + DATA.steps.length + ' of ' + DATA.total_snapshots + ' snapshots';
}

// Open on the final groups - the drawn result is what most readers want first.
// Silent, because walking the whole history at load would otherwise flash (and
// scroll to) every slot the draw ever touched.
render(DATA.steps.length - 1, true);
"""


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
<meta name="generator" content="{html.escape(f'{APP_NAME} {__version__}')}">
<title>{html.escape(heading)}</title>
<style>{_CSS}</style>
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
<script>{_JS}</script>
</body>
</html>
"""


def group_html_filename(competition, competition_class):
    """Return the HTML filename for one competition class's groups (shared naming convention)."""
    return f"{competition}_{competition_class}_groups.html"


def group_html_path(competition, competition_class, output_dir):
    """Return the full HTML path for one competition class's groups."""
    return os.path.join(output_dir, group_html_filename(competition, competition_class))


def export_group_html(competition, competition_class, groups, snapshots, output_dir,
                      run_meta=None, max_snapshots=None, draw_seconds=None):
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

    payload = _build_group_payload(
        competition, competition_class, groups, snapshots, max_snapshots=max_snapshots)
    heading = _class_display_name(competition, competition_class, "groups")
    # Same provenance as the footer, but machine-readable for anything that
    # parses the embedded JSON instead of the rendered page.
    payload["meta"] = {
        "version": (run_meta or {}).get('version', __version__),
        "draw_seconds": draw_seconds,
        "total_seconds": (run_meta or {}).get('total_seconds'),
        "generated_at": (run_meta or {}).get('generated_at'),
        "random_seed": (run_meta or {}).get('random_seed'),
        "total_snapshots": payload["total_snapshots"],
        "first_snapshot_index": payload["first_snapshot_index"],
    }
    cards_markup = _render_group_cards(list(payload["initial"].keys()), payload["max_group_size"])
    footer_markup = _render_footer(heading, draw_seconds, run_meta)
    document = _render_html_document(heading, payload, cards_markup, footer_markup)

    path = group_html_path(competition, competition_class, output_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(document)
    return path
