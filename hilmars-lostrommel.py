from group_draw import simulate_group_draw
from main_draw import simulate_main_draw
from mock_data import *
from startup_info import print_startup_info
from input_reader import read_players, read_draw_data
import inquirer

def main():
    print_startup_info()

    # Read players from CSV file
    players = read_players()

    # Read draw data from CSV file
    draw_data = read_draw_data()

    singles_or_doubles = inquirer.list_input("Draw for singles or doubles/mixed?", choices=['Singles', 'Doubles/Mixed'])
    draw_type = inquirer.list_input("Select draw type:", choices=['Group Draw', 'Main/Consolation Draw'])

    # Call the corresponding function based on user input
    if draw_type == 'Group Draw':
        
        group_size = int(inquirer.text("Please enter desired group size:"))
        print("\n")
        
        if singles_or_doubles == 'Singles':
            players = mock_players(32)
            simulate_group_draw(players, group_size)
        elif singles_or_doubles == 'Doubles/Mixed':
            teams = mock_teams(16)
            simulate_group_draw(teams, group_size)

    elif draw_type == 'Main/Consolation Draw':
        simulate_main_draw()
    else:
        print("Exiting program.")
        exit

if __name__ == "__main__":
    main()