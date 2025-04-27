from draw.group_drawer import GroupDrawer
from draw.bracket_drawer import simulate_main_draw
from io import mock_players, mock_teams
from misc.startup_info import print_startup_info
from io import read_players, read_draw_data
import inquirer

def main():
    print_startup_info()

    # Read players from CSV file
    # players = read_players()
    players = mock_players(32)

    # Read draw data from CSV file
    draw_data = read_draw_data()

    group_drawer = GroupDrawer(draw_data=draw_data, players=players)

    # Filter out single draw data
    singles_draw_data = [data for data in draw_data if data.competition == 'S']

    # Create data subsets for each distinct competition class
    competition_classes = set(data.competition_class for data in draw_data)
    for competition_class in competition_classes:
        class_subset = [data for data in draw_data if data.competition_class == competition_class]
        group_drawer.draw_groups(class_subset=class_subset, group_size=competition_class.amount_of_groups)
    
    # Filter out doubles draw data
    doubles_draw_data = [data for data in draw_data if data.competition == 'D']

    # Filter out mixed draw data
    mixed_draw_data = [data for data in draw_data if data.competition == 'M']


    singles_or_doubles = inquirer.list_input("Draw for singles or doubles/mixed?", choices=['Singles', 'Doubles/Mixed'])
    draw_type = inquirer.list_input("Select draw type:", choices=['Group Draw', 'Main/Consolation Draw'])

    # Call the corresponding function based on user input
    if draw_type == 'Group Draw':
        
        group_size = int(inquirer.text("Please enter desired group size:"))
        print("\n")
        
        if singles_or_doubles == 'Singles':
            group_drawer.simulate_group_draw(players, group_size)
        elif singles_or_doubles == 'Doubles/Mixed':
            teams = mock_teams(16)
            group_drawer.simulate_group_draw(teams, group_size)

    elif draw_type == 'Main/Consolation Draw':
        simulate_main_draw()
    else:
        print("Exiting program.")
        exit

if __name__ == "__main__":
    main()