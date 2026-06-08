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

# Prevent verbose table printing which can cause encoding issues in some terminals
bracket_viewer.show_bracket_table = lambda x: None
import draw.bracket_drawer as _bracket_mod
# override the local symbol used inside draw.bracket_drawer
_bracket_mod.show_bracket_table = lambda x: None
matches = draw_bracket(rows)
print('Generated matches:')
for k, v in matches.items():
    print(k, v)
