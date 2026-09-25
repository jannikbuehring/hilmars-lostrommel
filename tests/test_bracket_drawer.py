"""Tests for draw/bracket_drawer.py, converted from the original run_bracket_smoke.py script."""
import random

import pytest

from models.player import Player, players_list, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.bracket_drawer import draw_bracket, bracket_quality, HARD_BRACKET_RULES, TIER_QUARTER_BALANCE_WEIGHT
from checks.bracket_checker import (
    check_bye_balance_halves,
    check_half_group_separation,
    check_quarter_group_separation,
    check_top_easy_first_round,
    check_no_bottom_vs_bottom,
    check_placement_balance_quarters,
    check_round_two_matchups,
    score_bracket,
    score_round_two,
)
from misc.config import config


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


def test_uneven_consolation_layout_no_capacity_degrade():
    """Regression for the S W1 consolation case: groups 1-4 give pos {4,5,6} but
    group 5 only pos {4,5} = 14 players, bracket size 16, 2 byes.

    Group 5's winner demands only ONE opposite-half player (it has no 3rd), so a
    raw winner count over-weights it and mis-balances the halves.  Weighting each
    winner by its actual opposite-load (top_reverse_weight) keeps the halves
    feasible so the structured draw never falls back to the degrade path.
    """
    seeding_by_start_numbers.clear()
    for sn in range(101, 115):  # 14 players
        Player(sn, f'Last{sn}', f'First{sn}', f'C{sn}', f'Base{sn}', 'F', 1500 - sn)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    # groups 1-4 -> positions 4,5,6 ; group 5 -> positions 4,5 (missing its 3rd).
    layout = [(g, pos) for g in range(1, 5) for pos in (4, 5, 6)] + [(5, 4), (5, 5)]

    def build_rows():
        rows = []
        seed = 300
        sn = 101
        for group_no, group_pos in layout:
            seeding_by_start_numbers[str(sn)] = seed
            rows.append(DrawDataRow('S', 'W1', seed, 5, group_no, group_pos, True, False, sn, ''))
            seed -= 1
            sn += 1
        return rows

    try:
        for rng_seed in range(50):
            random.seed(rng_seed)
            matches, snapshots = draw_bracket(build_rows())

            assert not any(s.action == 'quarter_capacity_degrade' for s in snapshots), \
                f'Bracket degraded (rng_seed={rng_seed}) despite a placeable uneven consolation layout.'

            half_sep_violations = check_half_group_separation(matches, len(matches))
            assert not half_sep_violations, \
                f'Half-group-separation violations (rng_seed={rng_seed}): {half_sep_violations}'

            assert_group_half_relations(matches, 4)
    finally:
        seeding_by_start_numbers.clear()


def test_phase_1c_keeps_consolation_half_separation():
    """Regression for review finding C1: 3 full consolation groups (pos 4/5/6),
    9 players, 16 slots, 7 byes.

    The half-separation check used to bucket absolute positions 1/4 vs 2/3, so
    in a consolation bracket it never saw the 5th and 6th.  Phase 1c gates its
    bye swaps on that check and moved two groups' 5th/6th into their winner's
    half on every seed.  Some seeds of this layout still take the degrade path
    (see ARCHITECTURE.md known issues), so only the structured draws must be clean.
    """
    seeding_by_start_numbers.clear()
    for sn in range(101, 110):
        Player(sn, f'Last{sn}', f'First{sn}', f'C{sn}', f'Base{sn}', 'F', 1500 - sn)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    def build_rows():
        rows = []
        seed = 300
        sn = 101
        for group_no in range(1, 4):
            for group_pos in (4, 5, 6):
                seeding_by_start_numbers[str(sn)] = seed
                rows.append(DrawDataRow('S', 'M1', seed, 3, group_no, group_pos, False, True, sn, ''))
                seed -= 1
                sn += 1
        return rows

    try:
        structured_draws = 0
        for rng_seed in range(11):
            random.seed(rng_seed)
            matches, snapshots = draw_bracket(build_rows())
            if any(s.action == 'quarter_capacity_degrade' for s in snapshots):
                continue
            structured_draws += 1

            half_sep_violations = check_half_group_separation(matches, len(matches))
            assert not half_sep_violations, \
                f'Half-group-separation violations (rng_seed={rng_seed}): {half_sep_violations}'
            assert_group_half_relations(matches, 4)
        assert structured_draws > 0, 'Every seed degraded; the test no longer covers Phase 1c.'
    finally:
        seeding_by_start_numbers.clear()


def test_degrade_fill_keeps_the_hard_rules_and_the_winners():
    """Review finding H4: 11 full groups of 3, 33 players, 64 slots, 31 byes.

    Every seed of this layout takes the degrade path, but a layout without any
    hard violation exists.  The old fill scored random reshuffles of all free
    slots and ended with 1-2 half/quarter separation violations on every seed.
    The local search must find a clean layout, and it must not move a group
    winner out of its seeded slot.
    """
    seeding_by_start_numbers.clear()
    for sn in range(401, 434):
        Player(sn, f'Last{sn}', f'First{sn}', f'C{sn % 4}', f'Base{sn}', 'F', 1500)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    def build_rows():
        rows = []
        seed = 300
        sn = 401
        for group_pos in (1, 2, 3):
            for group_no in range(1, 12):
                seeding_by_start_numbers[str(sn)] = seed
                rows.append(DrawDataRow('S', 'M1', seed, 11, group_no, group_pos, True, False, sn, ''))
                seed -= 1
                sn += 1
        return rows

    def winner_slots(match_map):
        return {
            sn: slot for sn, slot in participant_slots(match_map).items()
            if sn - 401 < 11
        }

    try:
        for rng_seed in range(5):
            random.seed(rng_seed)
            matches, snapshots = draw_bracket(build_rows())
            degrade = next((s for s in snapshots if s.action == 'quarter_capacity_degrade'), None)
            assert degrade is not None, f'rng_seed={rng_seed} no longer degrades; the test lost its subject.'

            quality = bracket_quality(snapshots)
            assert not quality['hard'], f'rng_seed={rng_seed}: {quality["hard"]}'
            assert winner_slots(matches) == winner_slots(degrade.initial_groups), f'rng_seed={rng_seed}'
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

    # Review finding C2: the degrade and the broken separations are surfaced.
    quality = bracket_quality(snapshots)
    assert quality['degraded']
    assert quality['hard'], 'Two 2nd places of one group cannot both be separated from each other.'
    assert set(quality['hard']) <= set(HARD_BRACKET_RULES)


def test_bracket_quality_reads_the_returned_state(eight_players):
    """bracket_quality relies on draw_bracket's last snapshot being the returned
    state; a clean structured draw must report nothing."""
    rows = []
    for index, sn in enumerate(range(1, 9)):
        seeding_by_start_numbers[str(sn)] = 300 - index
        rows.append(DrawDataRow('S', 'M1', 300 - index, 2, 1 if index < 4 else 2, index % 4 + 1, True, False, sn, ''))

    random.seed(0)
    matches, snapshots = draw_bracket(rows)

    def keys(match_map):
        return {
            idx: [p if p in (None, 'BYE') else p.start_number_a for p in participants]
            for idx, participants in match_map.items()
        }

    assert keys(snapshots[-1].initial_groups) == keys(matches)
    quality = bracket_quality(snapshots)
    assert not quality['degraded']
    assert quality['hard'] == {}


def _quarter_of(match_idx, number_of_matches):
    return min(3, (match_idx - 1) // max(1, number_of_matches // 4))


def _winner_quarters_by_country(matches, country):
    """Quarters holding a group winner (top group_pos) of *country*."""
    quarters = []
    for match_idx, participants in matches.items():
        for p in participants:
            if p in (None, 'BYE') or p.group_pos != 1:
                continue
            if players_by_start_number[p.start_number_a].country == country:
                quarters.append(_quarter_of(match_idx, len(matches)))
    return quarters


def test_group_winner_countries_spread_across_quarters():
    """open_questions.md: 4 GER group winners must land one per quarter.

    Phase 1 assigns each seeding batch jointly and scores it with score_bracket,
    which includes the quarter-level country term — so among slot assignments
    that tie on the structural (tops+byes) balance penalties, the winners spread
    across the quarters by country.  Halves stay the stronger signal
    (country_half outweighs country_quarter).
    """
    seeding_by_start_numbers.clear()
    # 8 groups x pos {1,2} = 16 players in a 16-slot bracket.
    # Winners alternate GER/SWE; the rest get unique countries so they add no noise.
    winner_countries = ['GER', 'SWE', 'GER', 'SWE', 'GER', 'SWE', 'GER', 'SWE']
    for group_no in range(1, 9):
        Player(group_no, f'W{group_no}', f'Win{group_no}', winner_countries[group_no - 1], f'B{group_no}', 'F', 1500)
    for sn in range(9, 17):
        Player(sn, f'R{sn}', f'Rest{sn}', f'C{sn}', f'B{sn}', 'F', 1000)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    def build_rows():
        rows = []
        seed = 300
        for group_pos in (1, 2):
            for group_no in range(1, 9):
                sn = group_no if group_pos == 1 else group_no + 8
                seeding_by_start_numbers[str(sn)] = seed
                rows.append(DrawDataRow('S', 'M1', seed, 8, group_no, group_pos, True, False, sn, ''))
                seed -= 1
        return rows

    try:
        for rng_seed in range(20):
            random.seed(rng_seed)
            matches, _ = draw_bracket(build_rows())

            for country in ('GER', 'SWE'):
                quarters = sorted(_winner_quarters_by_country(matches, country))
                assert quarters == [0, 1, 2, 3], (
                    f'{country} group winners should sit one per quarter, got {quarters} (rng_seed={rng_seed}).'
                )
    finally:
        seeding_by_start_numbers.clear()


def test_batch_is_assigned_jointly_not_player_by_player():
    """Each seeding batch is optimised as a whole, beating player-by-player placement.

    12 group winners + 5 runners-up fill a 32-slot bracket, so batch 4 places its
    last four winners into the eight slots of its hierarchy level — 1680
    assignments, small enough to solve exactly.  Placing those four one at a time
    lets an early player take a slot that forces a worse assignment on the rest;
    the joint search finds the better whole-batch assignment every time.

    joint_batch_max_evaluations = 0 reproduces the old player-by-player behaviour
    (the enumeration budget is never met, and the hill-climb runs zero iterations
    on top of its greedy seed), which makes the two strategies directly comparable.

    Compared on the objective place_batch actually minimises, which is score_bracket
    PLUS the two terms deliberately kept out of it (tier-quarter balance and
    round-two matchup quality).  Comparing score_bracket alone reported the joint
    search as *better* on a layout where it had in fact bought its 10-point country
    edge with a tier imbalance — the trade TIER_QUARTER_BALANCE_WEIGHT now forbids.

    Three winner countries, not two: with only two the tier-balance term pins the
    assignment tightly enough that player-by-player reaches the joint optimum on
    its own, and the fixture stops discriminating.
    """
    countries = ('GER', 'SWE', 'NOR')

    def phase1_objective(budget, rng_seed):
        players_list.clear()
        players_by_start_number.clear()
        seeding_by_start_numbers.clear()
        for sn in range(1, 13):
            Player(sn, f'W{sn}', f'Win{sn}', countries[(sn - 1) % 3], f'B{sn}', 'F', 1500 - sn)
        for sn in range(13, 18):
            Player(sn, f'R{sn}', f'Rest{sn}', 'FIN', f'B{sn}', 'F', 1000)
        for p in players_list:
            players_by_start_number[p.start_number] = p

        rows = []
        seed = 300
        for group_no in range(1, 13):
            seeding_by_start_numbers[str(group_no)] = seed
            rows.append(DrawDataRow('S', 'M1', seed, 12, group_no, 1, True, False, group_no, ''))
            seed -= 1
        for offset, group_no in enumerate((1, 2, 3, 4, 5)):
            sn = 13 + offset
            seeding_by_start_numbers[str(sn)] = seed
            rows.append(DrawDataRow('S', 'M1', seed, 12, group_no, 2, True, False, sn, ''))
            seed -= 1

        config.read_dict({'bracket_draw': {
            'joint_batch_max_evaluations': str(budget),
            'max_draw_phase': '1',
        }})
        random.seed(rng_seed)
        # max_draw_phase = 1 returns the bracket with only the winners placed.
        matches, _snapshots = draw_bracket(rows)
        number_of_matches = len(matches)
        tier_units = sum(
            v[-1] for v in check_placement_balance_quarters(matches, number_of_matches)
        )
        return (
            score_bracket(matches, number_of_matches)
            + tier_units * TIER_QUARTER_BALANCE_WEIGHT
            + score_round_two(matches, bounds=(1, 2))
        )

    try:
        for rng_seed in range(10):
            player_by_player = phase1_objective(0, rng_seed)
            joint = phase1_objective(5000, rng_seed)
            assert joint < player_by_player, (
                f'Joint batch assignment scored {joint}, no better than the player-by-player '
                f'{player_by_player} (rng_seed={rng_seed}).'
            )
    finally:
        config.remove_section('bracket_draw')
        seeding_by_start_numbers.clear()


def test_phase_1b_continues_the_seeded_slot_hierarchy():
    """Phase 1b picks up the seeded-slot hierarchy where Phase 1 stopped.

    10 group winners in a 32-slot bracket fill hierarchy batches 0-3 (slots 1, 32,
    16, 17, 8, 9, 24, 25) and two of batch 4's eight slots {4,5,12,13,20,21,28,29}.
    With 12 byes against 10 winners, two runners-up also receive byes and must take
    leftover batch-4 slots rather than arbitrary free ones.

    Every phase-1b player is a bye recipient and therefore occupies a whole match,
    so this pins the canonical *seeded side* of the match rather than the match
    itself (the balance penalties already drive the match choice).  What the
    continuation really buys is the batch structure that lets phase 1b assign its
    recipients jointly, the same way phase 1 does.
    """
    seeding_by_start_numbers.clear()
    for sn in range(1, 21):
        Player(sn, f'P{sn}', f'L{sn}', f'C{sn}', f'B{sn}', 'F', 1500 - sn)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    # 10 groups x pos {1,2} = 20 players -> 32-slot bracket, 12 byes vs 10 winners.
    def build_rows():
        rows = []
        seed = 300
        for group_pos in (1, 2):
            for group_no in range(1, 11):
                sn = group_no if group_pos == 1 else group_no + 10
                seeding_by_start_numbers[str(sn)] = seed
                rows.append(DrawDataRow('S', 'M1', seed, 10, group_no, group_pos, True, False, sn, ''))
                seed -= 1
        return rows

    batch4_slots = {4, 5, 12, 13, 20, 21, 28, 29}

    try:
        for rng_seed in range(10):
            random.seed(rng_seed)
            _matches, snapshots = draw_bracket(build_rows())

            bye_assign_slots = [
                slot
                for snapshot in snapshots
                if snapshot.action == 'bye_assign'
                for slot in (snapshot.groups or [])
            ]
            assert bye_assign_slots, 'Phase 1b did not run — the fixture no longer exercises it.'

            for slot in bye_assign_slots:
                assert slot in batch4_slots, (
                    f'Phase 1b placed a bye recipient in slot {slot}, outside the leftover '
                    f'hierarchy batch {sorted(batch4_slots)} (rng_seed={rng_seed}).'
                )
    finally:
        seeding_by_start_numbers.clear()


# ---------------------------------------------------------------------------
# Round-one matchup quality (open_questions.md 17/19/20 + the 29.07 addendum):
# a group winner earned a BYE or a lowest-placed opponent.
#
# These are end-to-end regressions for the Phase-2 rebalance_bottom_tier_quarters
# post-pass, NOT for the score alone: the phase-5 Monte Carlo only shuffles within
# a quarter, so a winner can only be paired with a bottom-tier player that Phase 2
# already assigned to its quarter.  Before the post-pass the real input produced 22
# rule-A violations across the singles draws; after it, zero.
# ---------------------------------------------------------------------------

def build_tiered_rows(number_of_groups, positions, competition_class='M1', first_start_number=201,
                      short_groups=(), country_for=None):
    """Register fresh players and return rows for number_of_groups x positions.

    Unique countries and bases per player so the country/base terms cannot
    manufacture unrelated violations, and strictly descending seedings.

    *short_groups* lists group numbers that omit the LAST position, i.e. an uneven
    class where not every group sent a qualifier for that tier.

    *country_for* optionally overrides that: a ``(group_no, group_pos) -> country
    or None`` callable, so a test can give two participants the SAME country and
    make the country terms actually bite.  Returning None keeps the unique default.
    """
    group_positions = {
        group_no: (positions[:-1] if group_no in short_groups else positions)
        for group_no in range(1, number_of_groups + 1)
    }
    # Countries are decided per (group_no, group_pos), so resolve the layout before
    # registering the players -- start numbers are handed out in that same order.
    layout = [
        (group_no, group_pos)
        for group_no in range(1, number_of_groups + 1)
        for group_pos in group_positions[group_no]
    ]
    for offset, (group_no, group_pos) in enumerate(layout):
        sn = first_start_number + offset
        country = country_for(group_no, group_pos) if country_for is not None else None
        Player(sn, f'Last{sn}', f'First{sn}', country or f'C{sn}', f'Base{sn}', 'F', 2000 - sn)
    for p in players_list:
        players_by_start_number[p.start_number] = p

    rows = []
    seed = 300
    for offset, (group_no, group_pos) in enumerate(layout):
        sn = first_start_number + offset
        seeding_by_start_numbers[str(sn)] = seed
        rows.append(
            DrawDataRow('S', competition_class, seed, number_of_groups, group_no, group_pos, True, False, sn, '')
        )
        seed -= 1
    return rows


def test_group_winners_get_bye_or_bottom_opponent():
    """The live S M1 main layout: 10 groups x pos {1,2,3} = 30 players, bracket 32.

    Phase 2's capacity tie-break used to split the 3rd places 2/3 across the two
    quarters that needed 3 and 2, stranding one group winner per half with no
    lowest-placed opponent available in its quarter -- unreachable for phase 5.
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(20):
            random.seed(rng_seed)
            matches, snapshots = draw_bracket(build_tiered_rows(10, (1, 2, 3)))

            violations = check_top_easy_first_round(matches)
            assert not violations, (
                f'Group winner without a BYE or lowest-placed opponent '
                f'(rng_seed={rng_seed}): {[(v[0], v[1].group_pos, v[2].group_pos) for v in violations]}'
            )
            assert not any(s.action == 'quarter_capacity_degrade' for s in snapshots), \
                f'Bracket degraded (rng_seed={rng_seed}) despite a placeable 30-player layout.'
            assert not check_half_group_separation(matches, len(matches))
            assert not check_quarter_group_separation(matches, len(matches))
    finally:
        seeding_by_start_numbers.clear()


def test_small_bracket_group_winners_get_bottom_opponents():
    """5 groups x pos {1,2,3} = 15 players, bracket 16, 1 bye.

    The tightest 3-tier layout: 4 non-bye winners and only 5 residual slots per
    half, so every quarter's bottom-tier supply has to be exactly right.
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(50):
            random.seed(rng_seed)
            matches, _ = draw_bracket(build_tiered_rows(5, (1, 2, 3), competition_class='W1'))
            violations = check_top_easy_first_round(matches)
            assert not violations, (
                f'Group winner without a BYE or lowest-placed opponent '
                f'(rng_seed={rng_seed}): {[(v[0], v[1].group_pos, v[2].group_pos) for v in violations]}'
            )
    finally:
        seeding_by_start_numbers.clear()


def test_consolation_tiers_are_relative():
    """A consolation-style draw runs pos {4,5,6}; the rule follows the bracket's own bounds."""
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(20):
            random.seed(rng_seed)
            matches, _ = draw_bracket(build_tiered_rows(5, (4, 5, 6), competition_class='W2'))
            violations = check_top_easy_first_round(matches)
            assert not violations, (
                f'4th place without a BYE or 6th-place opponent '
                f'(rng_seed={rng_seed}): {[(v[0], v[1].group_pos, v[2].group_pos) for v in violations]}'
            )
    finally:
        seeding_by_start_numbers.clear()


def test_two_tier_draw_reports_no_new_placement_violations():
    """Doubles/mixed layouts have only 2 tiers, so both placement rules are exempt.

    Without the tier guard the arithmetically forced runner-up pairings here would
    score a permanent penalty and defeat the score==0 early exits.
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(10):
            random.seed(rng_seed)
            matches, _ = draw_bracket(build_tiered_rows(7, (1, 2), competition_class='M3'))
            assert check_top_easy_first_round(matches) == []
            assert check_no_bottom_vs_bottom(matches) == []
    finally:
        seeding_by_start_numbers.clear()


def test_byes_split_evenly_across_halves_in_uneven_class():
    """The live S M1 consolation layout: 10 groups x pos {4,5,6}, four of them
    without a 6th -> 26 players, 32 slots, 6 byes.

    The exact blind spot of the two older placement_penalty terms: the half term
    balances the NET load, and a full group's winner placed together with its bye
    is net-neutral, so a half with 4 winners + 4 byes and one with 2 winners + 2
    byes both scored 0 -- with a perfect 4/4/4/4 per-quarter count on top, which
    is all the combined-quarter term looks at.  Byes then came out 4/2.
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(20):
            random.seed(rng_seed)
            rows = build_tiered_rows(10, (4, 5, 6), short_groups=(6, 7, 8, 10))
            assert len(rows) == 26
            matches, snapshots = draw_bracket(rows)

            bye_half_counts = {0: 0, 1: 0}
            for match_idx, participants in matches.items():
                if 'BYE' in participants:
                    bye_half_counts[0 if match_idx <= (len(matches) // 2) else 1] += 1
            assert sum(bye_half_counts.values()) == 6
            assert not check_bye_balance_halves(matches, len(matches)), (
                f'Byes unevenly spread across the halves (rng_seed={rng_seed}): {bye_half_counts}'
            )
            # Bye balance is ranked below both feasibility penalties, so it must
            # never be what pushes a placeable layout onto the degrade path.
            assert not any(s.action == 'quarter_capacity_degrade' for s in snapshots), \
                f'Bracket degraded (rng_seed={rng_seed}) despite a placeable 26-player layout.'
    finally:
        seeding_by_start_numbers.clear()


def winner_country_halves(matches, top_group_pos=1):
    """{country: [count_half0, count_half1]} for the top placement tier only."""
    number_of_matches = len(matches)
    counts = {}
    for match_idx, participants in matches.items():
        half = 0 if match_idx <= (number_of_matches // 2) else 1
        for participant in participants:
            if participant in (None, 'BYE') or participant.group_pos != top_group_pos:
                continue
            country = players_by_start_number[participant.start_number_a].country
            counts.setdefault(country, [0, 0])[half] += 1
    return counts


def test_group_winners_are_country_balanced_across_the_halves():
    """The live S M2 main layout and its real winner countries: 11 groups x pos
    {1,2,3} = 33 players, 64 slots, 31 byes, with GER on four group winners, CRO
    and SLO on two each.

    Phase 1's last winner batch places 3 winners into an 8-slot hierarchy level
    with the byes standing 4/4, so EVERY assignment ends on the same legal 6/5
    split.  bye_half_excess was accumulated per placement, though, so it charged
    5000 whenever the first two movers went to the same half -- on nothing but
    participant order.  Here the country-clean assignment needs exactly that: SLO
    is 0/1 and GER 1/2 going into the batch, so both of the first two movers have
    to take the upper half.  At 250x country_half (20) the phantom cost decided
    the batch and the two Slovenian winners ended up together, in 10 of the 20
    seeds below.

    The 2nd/3rd tiers keep unique countries, so what is asserted here is the
    winners' spread alone -- which is the thing no aggregate country check can
    see once the lower tiers arrive and cancel it out.
    """
    winner_countries = {1: 'GER', 5: 'GER', 7: 'GER', 9: 'GER',
                        2: 'CRO', 6: 'CRO',
                        4: 'SLO', 10: 'SLO',
                        8: 'ENG', 11: 'CZE', 3: 'ISR'}

    def country_for(group_no, group_pos):
        return winner_countries.get(group_no) if group_pos == 1 else None

    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(20):
            random.seed(rng_seed)
            rows = build_tiered_rows(11, (1, 2, 3), country_for=country_for)
            assert len(rows) == 33
            matches, _snapshots = draw_bracket(rows)

            counts = winner_country_halves(matches)
            assert sum(sum(v) for v in counts.values()) == 11
            lopsided = {c: v for c, v in counts.items() if abs(v[0] - v[1]) > 1}
            assert not lopsided, (
                f'Group winners of one country piled into a half '
                f'(rng_seed={rng_seed}): {lopsided} of {counts}'
            )
    finally:
        seeding_by_start_numbers.clear()


def quarter_tier_counts(matches):
    """{group_pos: [count per quarter]} for a finished bracket."""
    number_of_matches = len(matches)
    matches_per_quarter = max(1, number_of_matches // 4)
    counts = {}
    for match_idx, participants in matches.items():
        quarter = min(3, (match_idx - 1) // matches_per_quarter)
        for participant in participants:
            if participant in (None, 'BYE'):
                continue
            counts.setdefault(participant.group_pos, [0, 0, 0, 0])[quarter] += 1
    return counts


def test_tiers_spread_evenly_across_the_quarters_of_each_half():
    """The live S M2 main layout: 11 groups x pos {1,2,3} = 33 players, 64 slots.

    31 byes, so every group winner AND every runner-up is placed by Phase 1/1b --
    and those two tiers are therefore fully decided before Phase 2 runs.  Both used
    to come out lopsided (runners-up 4/2 across the quarters of one half), because
    placement_penalty only ever balanced tops+byes per quarter, which is blind to
    the tier MIX: a quarter with 3 winners + 1 runner-up and one with 1 winner +
    2 runners-up score identically there.

    The 3rd places are deliberately not asserted: 9 of them get byes but the last
    2 are placed by Phase 2, so the tier is still incomplete while Phase 1c runs
    (which is exactly why assignment_quality_cost ignores unfinished tiers).
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(6):
            random.seed(rng_seed)
            rows = build_tiered_rows(11, (1, 2, 3))
            assert len(rows) == 33
            matches, _snapshots = draw_bracket(rows)

            counts = quarter_tier_counts(matches)
            for group_pos in (1, 2):
                per_quarter = counts[group_pos]
                assert sum(per_quarter) == 11
                for half_start in (0, 2):
                    low, high = sorted(per_quarter[half_start:half_start + 2])
                    assert high - low <= 1, (
                        f'group_pos {group_pos} split {per_quarter} across the quarters '
                        f'(rng_seed={rng_seed}).'
                    )
    finally:
        seeding_by_start_numbers.clear()


def test_group_winners_get_an_easy_round_two_opponent_when_byes_dominate():
    """With 31 of 32 first-round matches a walkover, round two is the real first round.

    11 winners, 11 runners-up and 11 third places into 64 slots: byes go to every
    winner, every runner-up and 9 thirds, leaving one real match of 3rd-vs-3rd.
    Ignoring every other rule, round two could serve the 11 winners with 9
    third-place walkovers plus the one undetermined match -- 10 harmless partners
    -- leaving exactly ONE winner on a runner-up.  Before round two was scored at
    all, five were.

    Two, not one, is the achievable bound: the layout that reaches one leaves the
    runners-up split 4/2 across the quarters of a half, and Phase 1c will not buy
    a round-two unit (42) with a tier unit (2500).  That ranking is deliberate --
    even distribution is a level-1 rule in open_questions.md, the round-two
    preference a level-2 one -- and it is stable, not incidental: every rng seed
    lands on exactly 2.

    Round-two 1-vs-1 is structurally impossible here (hierarchy levels 0-3 supply
    one match to each round-two pair and level 4 the other, so it needs
    n_top > bracket_size / 4), and 3-vs-3 is avoidable, so both must be clean.
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(6):
            random.seed(rng_seed)
            matches, _snapshots = draw_bracket(build_tiered_rows(11, (1, 2, 3)))
            round_two = check_round_two_matchups(matches, bounds=(1, 3))
            assert len(round_two['top_easy_opponent']) <= 2, (
                f'{len(round_two["top_easy_opponent"])} group winners meet a runner-up in '
                f'round two (rng_seed={rng_seed}); at most two are forced.'
            )
            assert round_two['first_vs_first'] == []
            assert round_two['bottom_vs_bottom'] == []
    finally:
        seeding_by_start_numbers.clear()


def test_phase_1c_repairs_without_conceding_a_separation_or_the_bye_balance():
    """The repair pass swaps bye recipients, which must stay feasibility-neutral.

    Both slots are (player, BYE) matches before and after, so every per-quarter and
    per-half bye count is invariant; group winners are not swap candidates at all,
    so the group anchors -- and Phase 2's dependence on them -- stay fixed by
    construction (see test_phase_1c_never_moves_a_group_winner).  Separations are a
    hard gate, since at 2500 a tier unit would otherwise outweigh both split weights.
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(6):
            random.seed(rng_seed)
            matches, snapshots = draw_bracket(build_tiered_rows(11, (1, 2, 3)))
            swaps = [s for s in snapshots if s.action == 'bye_swap']
            before = next(s for s in snapshots if s.action == 'top_seed_complete')
            after = next(s for s in snapshots if s.action == 'seeded_byes')

            for key in ('half_group_separation', 'quarter_group_separation'):
                assert len(after.violations[key]) <= max(
                    len(before.violations[key]),
                    max((len(s.violations[key]) for s in swaps), default=0),
                ), f'{key} grew across Phase 1c (rng_seed={rng_seed}).'
            assert not check_bye_balance_halves(matches, len(matches)), (
                f'Phase 1c unbalanced the byes across the halves (rng_seed={rng_seed}).'
            )
            # Every accepted swap must strictly improve, so none may repeat a state.
            assert len({tuple(s.groups) for s in swaps}) == len(swaps)
    finally:
        seeding_by_start_numbers.clear()


def test_phase_1c_never_moves_a_group_winner():
    """Phase 1 decides where the group winners sit; Phase 1c may not undo that.

    The pass exists to repair the spread of the players Phase 1b placed, and it does
    that by swapping bye recipients.  Only NON-top ones are candidates: a swap moves
    both of its participants, so admitting a winner as either side would relocate it
    and drag its group anchor -- and with it every separation rule and Phase 2
    quarter choice that reads group_top_quarter -- along.

    The 33-player S M2 layout alone would not catch a regression here (its winners
    happen never to be the cheapest swap), so the layouts that did move a winner
    under the old different-quarter rule are covered too: 13 and 6 groups x {1,2,3}.
    """
    seeding_by_start_numbers.clear()
    try:
        for group_count in (11, 13, 6):
            for rng_seed in range(4):
                random.seed(rng_seed)
                rows = build_tiered_rows(group_count, (1, 2, 3))
                top_group_pos = min(r.group_pos for r in rows)
                matches, snapshots = draw_bracket(rows)
                case = f'{group_count} groups, rng_seed={rng_seed}'

                for snapshot in (s for s in snapshots if s.action == 'bye_swap'):
                    assert all(
                        getattr(p, 'group_pos', None) != top_group_pos
                        for p in snapshot.participants
                    ), f'Phase 1c swapped a group winner ({case}).'

                # Structural check on the result rather than the trace: a swap always
                # changes a candidate's match, so every winner must still sit in the
                # match Phase 1 gave it.
                after_phase_1 = next(s for s in snapshots if s.action == 'top_seed_complete')

                def winner_matches(match_dict):
                    return {
                        p.start_number_a: index
                        for index, participants in match_dict.items()
                        for p in participants
                        if p not in (None, 'BYE') and p.group_pos == top_group_pos
                    }

                assert winner_matches(matches) == winner_matches(after_phase_1.initial_groups), (
                    f'A group winner changed match after Phase 1 ({case}).'
                )
                seeding_by_start_numbers.clear()
    finally:
        seeding_by_start_numbers.clear()


def test_phase_1c_is_deterministic_and_consumes_no_randomness():
    """Drawing the same layout twice under one seed must give one bracket.

    The pass deliberately takes no numbers from the shared RNG stream: doing so
    would shift every downstream random outcome, so a change in a drawn bracket
    would no longer be attributable to the rules rather than to the pass running.
    """
    seeding_by_start_numbers.clear()
    try:
        drawn = []
        for _ in range(2):
            random.seed(4)
            matches, snapshots = draw_bracket(build_tiered_rows(11, (1, 2, 3)))
            drawn.append((
                {i: [p if p == 'BYE' else p.start_number_a for p in ps if p is not None]
                 for i, ps in matches.items()},
                sum(1 for s in snapshots if s.action == 'bye_swap'),
            ))
            seeding_by_start_numbers.clear()
        assert drawn[0] == drawn[1]
    finally:
        seeding_by_start_numbers.clear()


def test_residual_third_avoids_the_quarter_its_runner_up_already_took():
    """Phase 2 must see the quarters Phase 1b already used for a group's 2nd.

    12 groups x pos {1,2,3} = 36 players into 64 slots: 28 byes cover every winner,
    every runner-up and 4 thirds, so 8 third places are residual.  assign_quarter_
    buckets built its group_opposite_half_used map from the residual players alone,
    so for those 8 groups it had no record of where Phase 1b had put the runner-up
    and picked on capacity alone -- landing in the very same quarter, 8 times over.
    "Darf eigentlich nicht verletzt werden" (open_questions.md).
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(4):
            random.seed(rng_seed)
            matches, _snapshots = draw_bracket(build_tiered_rows(12, (1, 2, 3)))
            violations = check_quarter_group_separation(matches, len(matches))
            assert not violations, (
                f'2nd/3rd of a group share a quarter (rng_seed={rng_seed}): {violations}'
            )
    finally:
        seeding_by_start_numbers.clear()


def test_bottom_players_not_paired_when_avoidable():
    """3rd-vs-3rd must be avoided whenever the geometry allows it.

    Soft rule: with very many byes it is structurally forced ("Bei ganz vielen
    freilosen dritter gegen dritter"), which is why this uses the 30-player /
    2-bye layout where every 3rd place can be spent on a group winner.
    """
    seeding_by_start_numbers.clear()
    try:
        for rng_seed in range(20):
            random.seed(rng_seed)
            matches, _ = draw_bracket(build_tiered_rows(10, (1, 2, 3)))
            violations = check_no_bottom_vs_bottom(matches)
            assert not violations, \
                f'Avoidable lowest-vs-lowest pairing (rng_seed={rng_seed}): {[v[0] for v in violations]}'
    finally:
        seeding_by_start_numbers.clear()
