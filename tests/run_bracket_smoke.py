"""Smoke test for bracket drawing.
Creates minimal players and draw rows and runs `draw_bracket`.
"""
from models.player import Player, players_by_start_number
from models.draw_data import DrawDataRow, seeding_by_start_numbers
from draw.bracket_drawer import draw_bracket

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

# Create DrawDataRow objects: competition 'S', class 'M1', seeding set, amount_of_groups=1, group_no maybe None, group_pos maybe 1..
for i, sn in enumerate([1,2,3,4,5,6,7,8], start=1):
    row = DrawDataRow('S', 'M1', seeding_by_start_numbers[str(sn)], 1, 1, (i%3)+1, True, False, sn, '')
    rows.append(row)

# Run the bracket draw
from viewer import bracket_viewer

# Run draw_bracket and display the first-round matches using the viewer
matches, snapshots = draw_bracket(rows)
print('Generated matches:')
for k, v in matches.items():
    print(k, [type(x).__name__ if x is not None else None for x in v])

print('\nBracket display:')
bracket_viewer.show_bracket_table(matches, title='Smoke Test Bracket')

# Bye distribution regression: verify byes are balanced across halves and that group 1st/2nd bye recipients are separated.
small_rows = [
    DrawDataRow('S', 'M1', 100, 2, 1, 1, True, False, 1, ''),
    DrawDataRow('S', 'M1', 95, 2, 2, 1, True, False, 2, ''),
    DrawDataRow('S', 'M1', 90, 2, 1, 2, True, False, 3, ''),
    DrawDataRow('S', 'M1', 85, 2, 2, 2, True, False, 4, ''),
    DrawDataRow('S', 'M1', 80, 2, 1, 3, True, False, 5, ''),
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


# --- Additional custom test: teams and BYE ordering ---
from models.draw_data import DrawDataRow

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
