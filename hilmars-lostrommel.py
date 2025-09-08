import traceback
import logging
import inquirer
from yaspin import yaspin

from misc.startup_info import print_startup_info

from draw.group_drawer import GroupDrawer
from draw.bracket_drawer import simulate_main_draw
from data_io.mock_data import mock_players, mock_teams
from data_io.input_reader import read_players, read_draw_data
from viewer.group_viewer import show_groups_table
from viewer.player_viewer import show_players_table
from models.player import players_by_start_number

singles_groups = {}
doubles_groups = {}
mixed_groups = {}

def show_main_menu():
    ########################################################################################
    action = inquirer.list_input("Choose what to do", choices=['View', 'Export all', 'Exit'])
    match (action):
        case 'View':
            view_choice()
        case 'Export all':
            print("")
        case 'Exit':
            return

def view_choice():
    what_to_view = inquirer.list_input("Choose what to view", choices=['Players', 'Groups', 'Bracket', 'Back'])
    match (what_to_view):
        case 'Players':
            show_players_table()
        case 'Groups':
            groups_choice()
        case 'Bracket':
            return
        case 'Back':
            show_main_menu()

def groups_choice():
    choices = list(singles_groups.keys())
    choices.sort()
    choices.append('Back')
    competition = inquirer.list_input("Choose a competition", choices=choices)
    match (competition):
        case 'Back':
            view_choice()
        case _:
            show_groups_table(singles_groups[competition])

def main():
    print_startup_info()

    # Basic configuration
    logging.basicConfig(
        level=logging.INFO,                     # minimum level to log
        format="%(asctime)s [%(levelname)s] %(message)s",  # log format
        datefmt="%Y-%m-%d %H:%M:%S"            # timestamp format
    )

    ########################################################################################
    with yaspin(text="Reading player data...", color="cyan") as spinner:
        try:
            # Read players from CSV file
            # players = mock_players(32)
            players = read_players()
            spinner.text = f"Successfully imported {len(players)} players"
            spinner.ok()

        except FileNotFoundError:
            spinner.text = f"File 'players.csv' in directory 'input' not found"
            spinner.fail()
            return

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return

    ########################################################################################
    with yaspin(text="Reading draw data...", color="cyan") as spinner:
        try:
            # Read draw data from CSV file
            draw_data = read_draw_data()
            
            # Filter out single draw data
            singles_draw_data = [data for data in draw_data if data.competition == 'S']

            # Filter out doubles draw data
            doubles_draw_data = [data for data in draw_data if data.competition == 'D']

            # Filter out mixed draw data
            mixed_draw_data = [data for data in draw_data if data.competition == 'M']


            spinner.text = f"Successfully imported {len(draw_data)} ({len(singles_draw_data)} single, {len(doubles_draw_data)} double, {len(mixed_draw_data)} mixed) draw data objects"
            spinner.ok()

        except FileNotFoundError:
            spinner.text = f"File 'draw_input.csv' in directory 'input' not found"
            spinner.fail()
            return

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return


    group_drawer = GroupDrawer(players=players)

    # TODO: check if single draw has already been performed

    ########################################################################################
    with yaspin(text="Drawing singles groups...", color="cyan") as spinner:
        try:
            if not singles_draw_data:
                spinner.text = f"No singles draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                singles_competition_classes = set(data.competition_class for data in singles_draw_data)
                for competition_class in singles_competition_classes:
                    class_subset = [data for data in singles_draw_data if data.competition_class == competition_class]
                    group = group_drawer.draw_groups(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    singles_groups[competition_class] = group

                competition_classes_list = list(singles_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created singles groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception:
            spinner.fail()
            print("An error occurred:", e)

    ########################################################################################
    with yaspin(text="Drawing doubles groups...", color="cyan") as spinner:
        try:
            if not doubles_draw_data:
                spinner.text = f"No doubles draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                doubles_competition_classes = set(data.competition_class for data in doubles_draw_data)
                for competition_class in doubles_competition_classes:
                    class_subset = [data for data in doubles_draw_data if data.competition_class == competition_class]
                    #group = group_drawer.draw_groups(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    #doubles_groups[competition_class] = group

                competition_classes_list = list(doubles_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created doubles groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception:
            spinner.fail()
            print("An error occurred:", e)

    ########################################################################################
    with yaspin(text="Drawing mixed groups...", color="cyan") as spinner:
        try:
            if not mixed_draw_data:
                spinner.text = f"No mixed draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                mixed_competition_classes = set(data.competition_class for data in mixed_draw_data)
                for competition_class in mixed_competition_classes:
                    class_subset = [data for data in mixed_draw_data if data.competition_class == competition_class]
                    #group = group_drawer.draw_groups(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    #mixed_groups[competition_class] = group

                competition_classes_list = list(mixed_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created mixed groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception:
            spinner.fail()
            print("An error occurred:", e)


    print("")
    show_main_menu()





    #singles_or_doubles = inquirer.list_input("Draw for singles or doubles/mixed?", choices=['Singles', 'Doubles/Mixed'])
    #draw_type = inquirer.list_input("Select draw type:", choices=['Group Draw', 'Main/Consolation Draw'])

    # Call the corresponding function based on user input
    #if draw_type == 'Group Draw':
    #    
    #    group_size = int(inquirer.text("Please enter desired group size:"))
    #    print("\n")
        
    #    if singles_or_doubles == 'Singles':
    #        group_drawer.simulate_group_draw(players, group_size)
    #    elif singles_or_doubles == 'Doubles/Mixed':
    #        teams = mock_teams(16)
    #        group_drawer.simulate_group_draw(teams, group_size)

    #elif draw_type == 'Main/Consolation Draw':
    #    simulate_main_draw()
    #else:
    #    print("Exiting program.")
    #    exit

if __name__ == "__main__":
    main()