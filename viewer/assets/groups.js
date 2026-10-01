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
