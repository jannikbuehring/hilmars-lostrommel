"""Tests for draw/bracket_drawer.py, converted from the original run_bracket_smoke.py script."""
import random

import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.bracket_drawer import draw_bracket
from checks.bracket_checker import check_half_group_separation


def participant_slots(match_map):
    slot_by_start_number = {}
    for bracket_match_idx, bracket_participants in match_map.items():
        for side_idx, participant in enumerate(bracket_participants):
            if participant in (None, 'BYE'):
                continue
            slot = ((bracket_match_idx - 1) * 2) + side_idx + 1
            slot_by_start_number[participant.start_number_a] = slot
    return slot_by_start_number


def assert_group_half_relations(match_map, top_group_pos):
    group_pos_halves = {}
    number_of_matches = len(match_map)

    for rel_match_idx, rel_participants in match_map.items():
        rel_half = 0 if rel_match_idx <= (number_of_matches // 2) else 1
        for participant in rel_participants:
            if participant in (None, 'BYE'):
                continue
            rel_group_no = getattr(participant, 'group_no', None)
            rel_group_pos = getattr(participant, 'group_pos', None)
            if rel_group_no is None or rel_group_pos is None:
                continue
            group_pos_halves.setdefault(rel_group_no, {}).setdefault(rel_group_pos, set()).add(rel_half)

    for rel_group_no, positions in group_pos_halves.items():
        top_halves = positions.get(top_group_pos)
        if not top_halves:
            continue
        assert len(top_halves) == 1, f'Group {rel_group_no} top position {top_group_pos} split across halves: {top_halves}'

        top_half = next(iter(top_halves))
        checks = {
            top_group_pos + 1: 'opposite',
            top_group_pos + 2: 'opposite',
            top_group_pos + 3: 'same',
        }

        for rel_group_pos, relation in checks.items():
            halves = positions.get(rel_group_pos)
            if not halves:
                continue
            assert len(halves) == 1, f'Group {rel_group_no} position {rel_group_pos} split across halves: {halves}'

            pos_half = next(iter(halves))
            if relation == 'opposite':
                assert pos_half != top_half, (
                    f'Group {rel_group_no} position {rel_group_pos} should be opposite half to top position {top_group_pos}.'
                )
            if relation == 'same':
                assert pos_half == top_half, (
                    f'Group {rel_group_no} position {rel_group_pos} should be in same half as top position {top_group_pos}.'
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
    Player(7, 'Gina', 'Golf', 'SWE', 'Base2', 'F', 970)
    Player(8, 'Hana', 'Hotel', 'GER', 'Base6', 'F', 950)
    for p in players_list:
        players_by_start_number[p.start_number] = p
    seeding_by_start_numbers.clear()
    yield
    seeding_by_start_numbers.clear()


def test_group_qualifiers_bracket_half_separation_and_seeding(eight_players):
    for i, sn in enumerate([1, 2, 3, 4, 5, 6, 7, 8], start=1):
        seeding_by_start_numbers[str(sn)] = 300 - i

    group_layout = [
        (1, 1, 1),
        (2, 1, 2),
        (3, 1, 3),
        (4, 1, 4),
        (5, 2, 1),
        (6, 2, 2),
        (7, 2, 3),
        (8, 2, 4),
    ]
    rows = [
        DrawDataRow('S', 'M1', seeding_by_start_numbers[str(sn)], 2, group_no, group_pos, True, False, sn, '')
        for sn, group_no, group_pos in group_layout
    ]

    matches, snapshots = draw_bracket(rows)

    assert_group_half_relations(matches, min(r.group_pos for r in rows if r.group_pos is not None))

    half_sep_violations = check_half_group_separation(matches, len(matches))
    assert not half_sep_violations, f'Half-group-separation violations in main bracket: {half_sep_violations}'

    top_rows = sorted([row for row in rows if row.group_pos == min(r.group_pos for r in rows)], key=lambda row: -row.seeding)
    final_slots = participant_slots(matches)
    expected_top_slots = {top_rows[0].start_number_a: 1, top_rows[1].start_number_a: 8}
    for start_number, expected_slot in expected_top_slots.items():
        assert final_slots.get(start_number) == expected_slot, (
            f'Top seeded participant {start_number} expected in slot {expected_slot}, got {final_slots.get(start_number)}.'
        )

    locked_top_ids = {row.start_number_a for row in top_rows}
    seeded_snapshot_slots = None
    for snapshot in snapshots:
        state = snapshot.initial_groups
        if not state:
            continue
        current_slots = participant_slots(state)
        current_top_slots = {start_number: current_slots.get(start_number) for start_number in locked_top_ids}
        if seeded_snapshot_slots is None and snapshot.action == 'top_seed_complete':
            seeded_snapshot_slots = current_top_slots
        elif seeded_snapshot_slots is not None and snapshot.action in (
            'initial_fill',
            'quarter0_mc_start', 'quarter1_mc_start', 'quarter2_mc_start', 'quarter3_mc_start',
            'improvement', 'progress', 'final',
        ):
            assert current_top_slots == seeded_snapshot_slots, (
                f'Top seeded participants moved after anchoring: {seeded_snapshot_slots} -> {current_top_slots}'
            )


def test_bye_distribution_is_balanced_and_separates_group_top_two(eight_players):
    small_rows = [
        DrawDataRow('S', 'M1', 100, 2, 1, 1, True, False, 1, ''),
        DrawDataRow('S', 'M1', 95, 2, 2, 1, True, False, 2, ''),
        DrawDataRow('S', 'M1', 90, 2, 1, 2, True, False, 3, ''),
        DrawDataRow('S', 'M1', 85, 2, 2, 5, True, False, 4, ''),
        DrawDataRow('S', 'M1', 80, 2, 1, 5, True, False, 5, ''),
    ]

    for row in small_rows:
        seeding_by_start_numbers[str(row.start_number_a)] = row.seeding

    bye_matches, _ = draw_bracket(small_rows)

    bye_half_counts = {0: 0, 1: 0}
    byes_in_half = {}
    for match_idx, participants in bye_matches.items():
        if 'BYE' in participants:
            half = 0 if match_idx <= (len(bye_matches) // 2) else 1
            bye_half_counts[half] += 1
            byes_in_half[match_idx] = half

    assert abs(bye_half_counts[0] - bye_half_counts[1]) <= 1, f'Byes are not evenly distributed across halves: {bye_half_counts}'

    bye_positions = {}
    for match_idx, participants in bye_matches.items():
        for p in participants:
            if p != 'BYE' and getattr(p, 'group_no', None) == 1 and p.group_pos in (1, 2):
                bye_positions[p.group_pos] = 0 if match_idx <= (len(bye_matches) // 2) else 1

    assert bye_positions.get(1) != bye_positions.get(2), 'Group 1 first and second bye recipients ended up in the same half.'


def test_relative_top_half_relation_for_consolation_like_bracket(eight_players):
    relative_rows = [
        DrawDataRow('S', 'M1', 400, 2, 1, 2, True, False, 1, ''),
        DrawDataRow('S', 'M1', 390, 2, 1, 3, True, False, 2, ''),
        DrawDataRow('S', 'M1', 380, 2, 1, 4, True, False, 3, ''),
        DrawDataRow('S', 'M1', 370, 2, 1, 5, True, False, 4, ''),
        DrawDataRow('S', 'M1', 360, 2, 2, 2, True, False, 5, ''),
        DrawDataRow('S', 'M1', 350, 2, 2, 3, True, False, 6, ''),
        DrawDataRow('S', 'M1', 340, 2, 2, 4, True, False, 7, ''),
        DrawDataRow('S', 'M1', 330, 2, 2, 5, True, False, 8, ''),
    ]

    for row in relative_rows:
        seeding_by_start_numbers[str(row.start_number_a)] = row.seeding

    relative_matches, _ = draw_bracket(relative_rows)
    assert_group_half_relations(relative_matches, 2)


def test_five_groups_three_positions_no_capacity_degrade():
    """Regression for the S W1 main case: 5 groups x pos {1,2,3} = 15 players.

    Bracket size 16, 1 bye (attached to the #1 seed).  The bye must pull the
    half split toward the half holding it (tops - byes balance), otherwise the
    final group winner lands in the wrong half and the bracket degrades even
    though a perfect placement exists.
    """
    seeding_by_start_numbers.clear()
    # Fresh players so country/base don't manufacture unrelated violations.
    for sn in range(101, 116):
        Player(sn, f'Last{sn}', f'First{sn}', f'C{sn}', f'Base{sn}', 'F', 1500 - sn)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    def build_rows():
        start_numbers = list(range(101, 116))  # 15 players
        rows = []
        seed = 300
        # 5 groups, positions 1..3, seedings strictly descending.
        for group_no in range(1, 6):
            for group_pos in range(1, 4):
                sn = start_numbers.pop(0)
                seeding_by_start_numbers[str(sn)] = seed
                rows.append(DrawDataRow('S', 'W1', seed, 5, group_no, group_pos, True, False, sn, ''))
                seed -= 1
        return rows

    try:
        # The misplacement is a random tiebreak, so a single draw is flaky; the
        # fix guarantees feasibility for EVERY RNG state, so no seed may degrade.
        for rng_seed in range(50):
            random.seed(rng_seed)
            matches, snapshots = draw_bracket(build_rows())

            assert not any(s.action == 'quarter_capacity_degrade' for s in snapshots), \
                f'Bracket degraded (rng_seed={rng_seed}) despite a placeable 15-player / 1-bye layout.'

            half_sep_violations = check_half_group_separation(matches, len(matches))
            assert not half_sep_violations, \
                f'Half-group-separation violations (rng_seed={rng_seed}): {half_sep_violations}'

            assert_group_half_relations(matches, 1)
    finally:
        seeding_by_start_numbers.clear()


def test_over_constrained_layout_degrades_to_best_effort(eight_players):
    """A layout too tight for hard quarter separation must not abort the draw.

    Instead of raising, draw_bracket degrades gracefully: it fills every slot
    with a score-minimising best-effort bracket and records the degrade path in
    the snapshots (half/quarter separation become soft, heavily weighted goals).
    """
    over_constrained_rows = [
        DrawDataRow('S', 'M1', 500, 1, 1, 1, True, False, 1, ''),
        DrawDataRow('S', 'M1', 490, 1, 1, 2, True, False, 2, ''),
        DrawDataRow('S', 'M1', 480, 1, 1, 2, True, False, 3, ''),
        DrawDataRow('S', 'M1', 470, 1, 1, 3, True, False, 4, ''),
    ]

    for row in over_constrained_rows:
        seeding_by_start_numbers[str(row.start_number_a)] = row.seeding

    matches, snapshots = draw_bracket(over_constrained_rows)

    # Every participant is placed — the draw is never aborted.
    placed = sorted(
        p.start_number_a
        for participants in matches.values()
        for p in participants
        if p is not None and p != 'BYE'
    )
    assert placed == [1, 2, 3, 4]

    # The graceful-degradation path was taken and a final bracket produced.
    assert any(s.action == 'quarter_capacity_degrade' for s in snapshots)
    assert snapshots[-1].action == 'final'
