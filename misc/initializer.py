import logging
import traceback
import random

from viewer.group_viewer import *
from yaspin import yaspin

import configparser

from data_io.input_reader import read_players, read_draw_data
from data_io.output_writer import write_to_csv, prepare_export_from_group_draw

from draw.group_drawer import GroupDrawer
from draw.bracket_drawer import BracketDrawer

from checks.validity_checker import *

from models.player import players_by_start_number

config = configparser.ConfigParser()
config.read("config.ini")

log_level = config["settings"]["log_level"]
mode = config["settings"]["mode"]
random_seed = config["settings"]["random_seed"]

export_data = []

if random_seed != '':
    random.seed(random_seed)

singles_groups = {}
doubles_groups = {}
mixed_groups = {}

group_drawer = GroupDrawer()
bracket_drawer = BracketDrawer()

def initialize_config():
    
    # Basic configuration
    logging.basicConfig(
        level=int(log_level),                                   # minimum level to log
        format="%(asctime)s [%(levelname)s] %(message)s",       # log format
        datefmt="%Y-%m-%d %H:%M:%S"                             # timestamp format
    )

def initialize_data():
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
            singles_group_draw_data = [data for data in singles_draw_data if data.group_pos == None]
            singles_bracket_draw_data = [data for data in singles_draw_data if data.group_pos != None]

            # Filter out doubles draw data
            doubles_draw_data = [data for data in draw_data if data.competition == 'D']
            doubles_group_draw_data = [data for data in doubles_draw_data if data.group_pos == None]
            doubles_bracket_draw_data = [data for data in doubles_draw_data if data.group_pos != None]

            # Filter out mixed draw data
            mixed_draw_data = [data for data in draw_data if data.competition == 'M']
            mixed_group_draw_data = [data for data in mixed_draw_data if data.group_pos == None]
            mixed_bracket_draw_data = [data for data in mixed_draw_data if data.group_pos != None]


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

    ########################################################################################
    with yaspin(text="Performing data validity checks...", color="cyan") as spinner:
        try:
            wrongful_player_data = check_all_players_only_exist_once()
            if wrongful_player_data:
                spinner.text = f"There were multiple player entries found"
                spinner.fail()
                print(f">>>> Multiple player entries for start number(s): {wrongful_player_data}")
                return

            missing_players = find_missing_players(draw_data)
            if missing_players:
                spinner.text = f"The draw data contains references to players that are missing from the import"
                spinner.fail()
                print(f">>>> Missing player(s): {missing_players}")
                return

            players_not_in_draw_data = find_players_not_in_draw_data(draw_data)
            if players_not_in_draw_data:
                spinner.text = f"There were players imported that are not partaking in any competition: {players_not_in_draw_data}"
                spinner.ok("WARN")    

            errors = find_players_in_wrong_competition(draw_data)
            if errors:
                spinner.text = f"Competition integrity problems detected"
                spinner.fail()
                print("")
                for e in errors:
                    print("   ", e)
                #return
            else:
                spinner.text = f"The imported data seems valid"
                spinner.ok()
                

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return

    ########################################################################################
    with yaspin(text="Drawing singles groups...", color="cyan") as spinner:
        try:
            if not singles_group_draw_data:
                spinner.text = f"No singles group draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                singles_competition_classes = set(data.competition_class for data in singles_group_draw_data)
                for competition_class in singles_competition_classes:
                    class_subset = [data for data in singles_group_draw_data if data.competition_class == competition_class]
                    group, snapshots = group_drawer.draw_groups(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    singles_groups[competition_class] = {"group": group, "snapshots": snapshots}

                competition_classes_list = list(singles_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created singles groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Drawing doubles groups...", color="cyan") as spinner:
        try:
            if not doubles_group_draw_data:
                spinner.text = f"No doubles group draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                doubles_competition_classes = set(data.competition_class for data in doubles_group_draw_data)
                for competition_class in doubles_competition_classes:
                    class_subset = [data for data in doubles_group_draw_data if data.competition_class == competition_class]
                    group, snapshots = group_drawer.draw_groups(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    doubles_groups[competition_class] = {"group": group, "snapshots": snapshots}

                competition_classes_list = list(doubles_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created doubles groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Drawing mixed groups...", color="cyan") as spinner:
        try:
            if not mixed_group_draw_data:
                spinner.text = f"No mixed draw group data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                mixed_competition_classes = set(data.competition_class for data in mixed_group_draw_data)
                for competition_class in mixed_competition_classes:
                    class_subset = [data for data in mixed_group_draw_data if data.competition_class == competition_class]
                    group, snapshots = group_drawer.draw_groups(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    mixed_groups[competition_class] = {"group": group, "snapshots": snapshots}

                competition_classes_list = list(mixed_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created mixed groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Drawing singles bracket...", color="cyan") as spinner:
        try:
            if not singles_bracket_draw_data:
                spinner.text = f"No singles bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                singles_competition_classes = set(data.competition_class for data in singles_bracket_draw_data)
                for competition_class in singles_competition_classes:
                    class_subset = [data for data in singles_bracket_draw_data if data.competition_class == competition_class]
                    main_round_participants = [data for data in class_subset if data.main_round == True]
                    consolation_round_participants = [data for data in class_subset if data.consolation_round == True]

                    #main_bracket = bracket_drawer.draw_bracket(class_subset=main_round_participants)
                    #consolation_bracket = bracket_drawer.draw_bracket(class_subset=consolation_round_participants)

                competition_classes_list = list(singles_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created singles bracket for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Drawing doubles bracket...", color="cyan") as spinner:
        try:
            if not doubles_bracket_draw_data:
                spinner.text = f"No doubles bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                doubles_competition_classes = set(data.competition_class for data in doubles_bracket_draw_data)
                for competition_class in doubles_competition_classes:
                    class_subset = [data for data in doubles_bracket_draw_data if data.competition_class == competition_class]
                    # draw bracket

                competition_classes_list = list(doubles_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created doubles bracket for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Drawing mixed bracket...", color="cyan") as spinner:
        try:
            if not mixed_bracket_draw_data:
                spinner.text = f"No mixed bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                mixed_competition_classes = set(data.competition_class for data in mixed_bracket_draw_data)
                for competition_class in mixed_competition_classes:
                    class_subset = [data for data in mixed_bracket_draw_data if data.competition_class == competition_class]
                    # draw bracket

                competition_classes_list = list(mixed_competition_classes)
                competition_classes_list.sort()
                spinner.text = f"Successfully created mixed bracket for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Preparing data for export...", color="cyan") as spinner:
        try:
            groups = {'S': singles_groups, 'D': doubles_groups, 'M': mixed_groups}
            brackets = {}
            export_data.extend(prepare_export_from_group_draw(groups))
            #export_data.append(prepare_export_from_bracket_draw(brackets))


            spinner.text = f"Export successfully prepared"
            spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Exporting draws to file...", color="cyan") as spinner:
        try:
            write_to_csv(export_data)

            spinner.text = f"Successfully created output file"
            spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred:", e)
            return