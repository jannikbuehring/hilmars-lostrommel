"""Smoke test for bracket drawing.
Creates minimal players and draw rows and runs `draw_bracket`.
"""
from models.player import Player, players_by_start_number
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
        if len(top_halves) != 1:
            raise AssertionError(f'Group {rel_group_no} top position {top_group_pos} split across halves: {top_halves}')

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
            if len(halves) != 1:
                raise AssertionError(f'Group {rel_group_no} position {rel_group_pos} split across halves: {halves}')

            pos_half = next(iter(halves))
            if relation == 'opposite' and pos_half == top_half:
                raise AssertionError(
                    f'Group {rel_group_no} position {rel_group_pos} should be opposite half to top position {top_group_pos}.'
                )
            if relation == 'same' and pos_half != top_half:
                raise AssertionError(
                    f'Group {rel_group_no} position {rel_group_pos} should be in same half as top position {top_group_pos}.'
                )

# Create minimal players
players_by_start_number.clear()
Player(1, 'Alice', 'Alpha', 'GER', 'Base1', 'F', 1200)
Player(2, 'Betty', 'Bravo', 'SWE', 'Base2', 'F', 1100)
Player(3, 'Cara', 'Charlie', 'GER', 'Base1', 'F', 1150)
Player(4, 'Dora', 'Delta', 'SWE', 'Base3', 'F', 1050)
Player(5, 'Eve', 'Echo', 'NOR', 'Base4', 'F', 1000)
Player(6, 'Fay', 'Foxtrot', 'FIN', 'Base5', 'F', 980)
Player(7, 'Gina', 'Golf', 'SWE', 'Base2', 'F', 970)
Player(8, 'Hana', 'Hotel', 'GER', 'Base6', 'F', 950)
from models.player import players_list

# Populate players_by_start_number mapping expected by other modules
players_by_start_number.clear()
for p in players_list:
    players_by_start_number[p.start_number] = p

# Prepare draw rows (simulate group qualifiers)
seeding_by_start_numbers.clear()
rows = []
# Seeded by start number mapping
for i, sn in enumerate([1,2,3,4,5,6,7,8], start=1):
    seeding_by_start_numbers[str(sn)] = 300 - i

# Create DrawDataRow objects with a valid group-position layout (2 groups x positions 1..4).
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
for sn, group_no, group_pos in group_layout:
    row = DrawDataRow('S', 'M1', seeding_by_start_numbers[str(sn)], 2, group_no, group_pos, True, False, sn, '')
    rows.append(row)

# Run the bracket draw
from viewer import bracket_viewer

# Run draw_bracket and display the first-round matches using the viewer
matches, snapshots = draw_bracket(rows)
print('Generated matches:')
for k, v in matches.items():
    print(k, [type(x).__name__ if x is not None else None for x in v])

assert_group_half_relations(matches, min(r.group_pos for r in rows if r.group_pos is not None))

# Direct checker assertion: half-group-separation must have zero violations.
half_sep_violations = check_half_group_separation(matches, len(matches))
if half_sep_violations:
    raise AssertionError(f'Half-group-separation violations in main bracket: {half_sep_violations}')
print('Half-group-separation check passed.')

top_rows = sorted([row for row in rows if row.group_pos == min(r.group_pos for r in rows)], key=lambda row: -row.seeding)
final_slots = participant_slots(matches)
expected_top_slots = {top_rows[0].start_number_a: 1, top_rows[1].start_number_a: 8}
for start_number, expected_slot in expected_top_slots.items():
    actual_slot = final_slots.get(start_number)
    if actual_slot != expected_slot:
        raise AssertionError(f'Top seeded participant {start_number} expected in slot {expected_slot}, got {actual_slot}.')

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
    elif seeded_snapshot_slots is not None and snapshot.action in ('initial_fill', 'half0_mc_start', 'half1_mc_start', 'improvement', 'progress', 'final'):
        if current_top_slots != seeded_snapshot_slots:
            raise AssertionError(f'Top seeded participants moved after anchoring: {seeded_snapshot_slots} -> {current_top_slots}')

print('\nBracket display:')
bracket_viewer.show_bracket_table(matches, title='Smoke Test Bracket')

# Bye distribution regression: verify byes are balanced across halves and that group 1st/2nd bye recipients are separated.
small_rows = [
    DrawDataRow('S', 'M1', 100, 2, 1, 1, True, False, 1, ''),
    DrawDataRow('S', 'M1', 95, 2, 2, 1, True, False, 2, ''),
    DrawDataRow('S', 'M1', 90, 2, 1, 2, True, False, 3, ''),
    DrawDataRow('S', 'M1', 85, 2, 2, 5, True, False, 4, ''),
    DrawDataRow('S', 'M1', 80, 2, 1, 5, True, False, 5, ''),
]

# Use the same players_by_start_number mapping already prepared above.
seeding_by_start_numbers.clear()
for row in small_rows:
    key = str(row.start_number_a)
    seeding_by_start_numbers[key] = row.seeding

bye_matches, bye_snapshots = draw_bracket(small_rows)
bye_half_counts = {0: 0, 1: 0}
byes_in_half = {}
for match_idx, participants in bye_matches.items():
    if 'BYE' in participants:
        half = 0 if match_idx <= (len(bye_matches) // 2) else 1
        bye_half_counts[half] += 1
        byes_in_half[match_idx] = half

print('\nBye distribution check:')
print('Half counts:', bye_half_counts)
print('Bye slots:', sorted(byes_in_half.items()))
if abs(bye_half_counts[0] - bye_half_counts[1]) > 1:
    raise AssertionError(f'Byes are not evenly distributed across halves: {bye_half_counts}')

# Confirm group 1st and 2nd bye recipients from group 1 are in opposite halves.
bye_positions = {}
for match_idx, participants in bye_matches.items():
    for p in participants:
        if p != 'BYE' and getattr(p, 'group_no', None) == 1 and p.group_pos in (1, 2):
            bye_positions[p.group_pos] = 0 if match_idx <= (len(bye_matches) // 2) else 1

if bye_positions.get(1) == bye_positions.get(2):
    raise AssertionError('Group 1 first and second bye recipients ended up in the same half.')

print('Bye distribution test passed.')

# Relative-top half relation regression (consolation-like: top group_pos is 2)
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

seeding_by_start_numbers.clear()
for row in relative_rows:
    seeding_by_start_numbers[str(row.start_number_a)] = row.seeding

relative_matches, _ = draw_bracket(relative_rows)
assert_group_half_relations(relative_matches, 2)
print('Relative-top half relation test passed.')

# Impossible strict layout regression: verify failure snapshot is attached.
impossible_rows = [
    DrawDataRow('S', 'M1', 500, 1, 1, 1, True, False, 1, ''),
    DrawDataRow('S', 'M1', 490, 1, 1, 2, True, False, 2, ''),
    DrawDataRow('S', 'M1', 480, 1, 1, 2, True, False, 3, ''),
    DrawDataRow('S', 'M1', 470, 1, 1, 3, True, False, 4, ''),
]

seeding_by_start_numbers.clear()
for row in impossible_rows:
    seeding_by_start_numbers[str(row.start_number_a)] = row.seeding

try:
    draw_bracket(impossible_rows)
    raise AssertionError('Expected strict slotting failure for impossible fixture, but draw_bracket succeeded.')
except ValueError as exc:
    failure_snapshots = getattr(exc, 'snapshots', None)
    if not failure_snapshots:
        raise AssertionError('Strict slotting failure did not expose snapshots on exception.') from exc
    last_snapshot = failure_snapshots[-1]
    if last_snapshot.action not in ('seed_slot_failure', 'permutation_failure'):
        raise AssertionError(f'Unexpected failure snapshot action: {last_snapshot.action}') from exc
    failure_info = last_snapshot.violations.get('failure', {})
    if failure_info.get('type') not in (
        'seed_slot_failure',
        'permutation_failure',
        'capacity_impossible',
        'unconstrained_distribution_impossible',
        'permutation_internal_inconsistency',
    ):
        raise AssertionError(f'Unexpected failure type metadata: {failure_info}') from exc

print('Failure snapshot test passed.')


# --- Additional custom test: teams and BYE ordering ---

team1 = DrawDataRow('S', 'D', 100, 1, 1, 1, True, False, 1, 2)
team2 = DrawDataRow('S', 'D', 90, 1, 1, 2, True, False, 3, 4)
team3 = DrawDataRow('S', 'D', 80, 1, 1, 3, True, False, 5, 6)
single1 = DrawDataRow('S', 'D', 70, 1, 1, 1, True, False, 7, '')

custom_matches = {
    1: [team1, 'BYE'],      # team vs BYE -> BYE should appear second
    2: ['BYE', team2],      # BYE vs team -> viewer should place team left, BYE right and on second line
    3: [team3, team2],      # team vs team
    4: [single1, team1],    # single vs team
}

print('\nCustom team bracket display:')
bracket_viewer.show_bracket_table(custom_matches, title='Team Test Bracket')
