"""Tests for draw/group_drawer.py."""
import random

import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.group_drawer import draw_groups_monte_carlo, EmptySlot
from misc.config import config


@pytest.fixture
def crowded_class():
    """40 singles players in 8 groups; most share a country and a base, so the
    conflicts cannot all be avoided and the search gets stuck in local minima."""
    rng = random.Random(42)
    countries = [rng.choice(['GER'] * 5 + ['SWE'] * 2 + ['NOR', 'FIN']) for _ in range(40)]
    bases = [f'Base{rng.randint(1, 6)}' for _ in range(40)]
    for sn in range(1, 41):
        Player(sn, f'First{sn}', f'Last{sn}', countries[sn - 1], bases[sn - 1], 'M', 2000 - sn * 10)
    for p in players_list:
        players_by_start_number[p.start_number] = p
    seeding_by_start_numbers.clear()
    rows = []
    for sn in range(1, 41):
        seeding = 300 - sn
        seeding_by_start_numbers[str(sn)] = seeding
        rows.append(DrawDataRow('S', 'M1', seeding, 8, '', '', True, False, sn, ''))
    yield rows
    seeding_by_start_numbers.clear()


@pytest.fixture
def escape_heavy_config():
    """One seed, and a short patience so escapes (accepted worse swaps) happen often."""
    config["group_draw"] = {
        "max_iterations": "1500",
        "max_no_improvement_iterations": "20",
        "max_escape_attempts": "10",
        "max_seed_retries": "1",
        "country_violation_weight": "1",
        "team_country_violation_weight": "1",
        "base_violation_weight": "1",
        "qttr_violation_weight": "1",
    }
    yield
    config.remove_section("group_draw")


def _replay(snapshots):
    """Rebuild the final groups from the swap/revert deltas, as the viewers do."""
    groups = {g: list(m) for g, m in snapshots[0].initial_groups.items()}
    for snap in snapshots[1:]:
        g1, g2 = snap.groups
        p1, p2 = snap.participants
        if snap.action == "swap":
            groups[g1][snap.index], groups[g2][snap.index] = p2, p1
        elif snap.action == "revert":
            groups[g1][snap.index], groups[g2][snap.index] = p1, p2
    return {g: [p.start_number_a for p in m if not isinstance(p, EmptySlot)] for g, m in groups.items()}


@pytest.mark.parametrize("rng_seed", range(8))
def test_returns_best_visited_state_not_final_state(crowded_class, escape_heavy_config, rng_seed):
    random.seed(rng_seed)
    groups, snapshots = draw_groups_monte_carlo(crowded_class, 8)

    scores = [s.violation_score for s in snapshots]
    assert scores[-1] == min(scores)
    assert _replay(snapshots) == {g: [p.start_number_a for p in m] for g, m in groups.items()}


def test_one_entry_per_group_does_not_crash(escape_heavy_config):
    """Entries == groups leaves a single seeding batch, which the swap loop never touches."""
    for sn in range(1, 5):
        Player(sn, f'First{sn}', f'Last{sn}', 'GER', 'Base1', 'M', 2000 - sn * 10)
    for p in players_list:
        players_by_start_number[p.start_number] = p
    rows = [DrawDataRow('S', 'M1', 300 - sn, 4, '', '', False, False, sn, '') for sn in range(1, 5)]
    config["group_draw"]["max_seed_retries"] = "5"

    groups, snapshots = draw_groups_monte_carlo(rows, 4)

    assert {g: [p.start_number_a for p in m] for g, m in groups.items()} == {1: [1], 2: [2], 3: [3], 4: [4]}
    assert len(snapshots) == 1  # only the initial placement, no swaps
    seeding_by_start_numbers.clear()
