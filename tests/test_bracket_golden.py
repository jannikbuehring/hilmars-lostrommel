"""Golden tests that pin the bracket drawer's exact output.

They guard behaviour-preserving refactors of draw/bracket: every case must give
the same bracket, the same snapshot trail and leave the shared RNG at the same
position as the code the goldens were recorded from.  A change that is MEANT to
alter draws re-records them:

    UPDATE_GOLDEN=1 pytest tests/test_bracket_golden.py

and the diff of tests/golden/ then shows which shapes moved.
"""

import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from draw.bracket import draw_bracket
from models.draw_data import DrawDataRow
from tests.bracket_shapes import build_doubles_rows, build_tiered_rows

GOLDEN_DIR = Path(__file__).parent / "golden"
FINGERPRINTS = GOLDEN_DIR / "bracket_fingerprints.json"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"

# name -> (rows builder, rng seed, draw_bracket kwargs).  Together they reach
# every phase: the deterministic and joint winner batches (exhaustive and
# hill-climb), Phase 1b byes, the Phase 1c swap and move, Phase 2 with 4th
# places, the Phase 5 Monte Carlo, the degrade fill with its half_balance=False
# redraw, phase1_only, consolation tiers and doubles.
CASES = {
    "singles_5x3": (lambda: build_tiered_rows(5, (1, 2, 3)), 0, {}),
    "singles_11x3_byes": (lambda: build_tiered_rows(11, (1, 2, 3)), 0, {}),
    "singles_11x3_phase1_only": (lambda: build_tiered_rows(11, (1, 2, 3)), 2, {"phase1_only": True}),
    "singles_4x4_short_degrade": (lambda: build_tiered_rows(4, (1, 2, 3, 4), short_groups=(1,)), 0, {}),
    "singles_4x3_short_degrade": (lambda: build_tiered_rows(4, (1, 2, 3), short_groups=(2,)), 0, {}),
    "singles_6x4_short_bye_move": (lambda: build_tiered_rows(6, (1, 2, 3, 4), short_groups=(2, 5)), 0, {}),
    "singles_6x3_shared_countries": (
        lambda: build_tiered_rows(6, (1, 2, 3), country_for=lambda g, p: f"K{(g * 3 + p) % 3}"),
        0,
        {},
    ),
    "singles_3x2_short": (lambda: build_tiered_rows(3, (3, 4), short_groups=(1,)), 0, {}),
    "singles_8x1_thirds": (lambda: build_tiered_rows(8, (3,), competition_class="W4"), 0, {}),
    "consolation_10x3_short": (lambda: build_tiered_rows(10, (4, 5, 6), short_groups=(6, 7, 8, 10)), 1, {}),
    "consolation_15x3_short": (lambda: build_tiered_rows(15, (4, 5, 6), short_groups=(3, 7, 11, 15)), 0, {}),
    "doubles_10x2": (lambda: build_doubles_rows(10, (1, 2)), 0, {}),
}


def _canon(value):
    """JSON-ready, order-stable form of a snapshot field (participants by start number)."""
    if isinstance(value, DrawDataRow):
        return f"#{value.start_number_a}/{value.start_number_b}"
    if isinstance(value, dict):
        return sorted(([_canon(k), _canon(v)] for k, v in value.items()), key=repr)
    if isinstance(value, (set, frozenset)):
        return sorted((_canon(v) for v in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, float):
        return repr(value)
    return value


def fingerprint(rows, matches, snapshots):
    payload = {
        # draw_bracket sorts and seeds its input in place.
        "rows": [(_canon(r), r.seeding) for r in rows],
        "matches": _canon(matches),
        "snapshots": [
            _canon([s.action, s.groups, s.index, s.participants, s.violations, s.violation_score, s.state])
            for s in snapshots
        ],
        # Pins how much randomness the draw consumed.
        "rng_next": repr(random.random()),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _load_fingerprints():
    return json.loads(FINGERPRINTS.read_text()) if FINGERPRINTS.exists() else {}


@pytest.mark.parametrize("name", list(CASES))
def test_bracket_fingerprint_unchanged(name):
    build, rng_seed, kwargs = CASES[name]
    random.seed(rng_seed)
    rows = build()
    matches, snapshots = draw_bracket(rows, **kwargs)
    actual = fingerprint(rows, matches, snapshots)

    if UPDATE:
        stored = _load_fingerprints()
        stored[name] = actual
        GOLDEN_DIR.mkdir(exist_ok=True)
        FINGERPRINTS.write_text(json.dumps(dict(sorted(stored.items())), indent=2) + "\n")
        return
    assert actual == _load_fingerprints().get(name), f"{name}: the drawn bracket or its snapshot trail changed."


E2E_SEED = "4711"
E2E_GOLDEN = GOLDEN_DIR / f"output_example_seed{E2E_SEED}.csv"


@pytest.mark.slow
def test_example_input_output_unchanged(tmp_path):
    """The whole pipeline on the shipped example input (two 250-500 player brackets)."""
    root = Path(__file__).parent.parent
    output = tmp_path / "output.csv"
    subprocess.run(
        [
            sys.executable,
            str(root / "hilmars_lostrommel.py"),
            "--config",
            str(root / "config" / "config_template.ini"),
            "--draw-input",
            str(root / "input" / "draw_input_example.csv"),
            "--players",
            str(root / "input" / "players_example.csv"),
            "--seed",
            E2E_SEED,
            "--output",
            str(output),
            "--no-html",
            "--no-menu",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    if UPDATE:
        E2E_GOLDEN.write_bytes(output.read_bytes())
        return
    assert output.read_bytes() == E2E_GOLDEN.read_bytes()
