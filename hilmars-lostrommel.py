from group_draw import simulate_group_draw
from main_draw import simulate_main_draw
from mock_data import *
from startup_info import print_startup_info

def main():
    print_startup_info()

    print("Press [1] for group draw")
    print("Press [2] for main/consolation draw")
    print("Press any other key to exit")

    choice = input("Enter your choice: ")

    # Call the corresponding function based on user input
    if choice == '1':
        group_size = int(input("Please enter desired group size: "))
        print("Press [1] for singles")
        print("Press [2] for doubles/mixed")
        choice2 = input("Enter your choice: ")
        if choice2 == '1':
            players = mock_players(32)
            simulate_group_draw(players, group_size)
        elif choice2 == '2':
            teams = mock_teams(16)
            simulate_group_draw(teams, group_size)
    elif choice == '2':
        simulate_main_draw()
    else:
        print("Exiting program.")
        exit

if __name__ == "__main__":
    main()