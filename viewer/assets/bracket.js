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

// The per-rule violation breakdown is debug output, hidden unless the checkbox is ticked.
// Split out of render() so toggling it repaints only this label -- a full render() would
// clear the 'changed' flash of the step the user just took.
function renderViolations(snap) {
  const show = document.getElementById('show-violations').checked;
  const entries = !show ? [] : Object.entries(snap.violations || {})
    .filter(function (kv) { return kv[1] && (Array.isArray(kv[1]) ? kv[1].length : true); })
    .map(function (kv) { return kv[0] + ': ' + JSON.stringify(kv[1]); });
  document.getElementById('violations-label').textContent = entries.join('  |  ');
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
  renderViolations(snap);

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
document.getElementById('show-violations').addEventListener('change', function () {
  renderViolations(DATA.snapshots[currentIndex]);
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'ArrowLeft') document.getElementById('btn-prev').click();
  if (e.key === 'ArrowRight') document.getElementById('btn-next').click();
});

measureColumnWidths();
render(currentIndex);
