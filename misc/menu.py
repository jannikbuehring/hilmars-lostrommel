import inquirer
from viewer.group_viewer import *
from viewer.player_viewer import show_players_table
from viewer.bracket_viewer import show_bracket_table
from misc.initializer import *
from hilmars_lostrommel import *

def show_main_menu():
    action = inquirer.list_input("Choose what to do", choices=['View', 'Export all', 'Exit'])
    match (action):
        case 'View':
            view_choice()
        case 'Export':
            print("")
        case 'Exit':
            exit()
    show_main_menu()

def view_choice():
    what_to_view = inquirer.list_input("Choose what to view", choices=['Players', 'Groups', 'Bracket', 'Back'])
    match (what_to_view):
        case 'Players':
            show_players_table()
        case 'Groups':
            singles_doubles_mixed_choice()
        case 'Bracket':
            show_bracket_table()
        case 'Back':
            show_main_menu()

def singles_doubles_mixed_choice():
    s_d_m = inquirer.list_input("Choose what to view", choices=['Singles', 'Doubles', 'Mixed'])
    match (s_d_m):
        case 'Singles':
            choices = list(singles_groups.keys())
            groups_choice('S', choices)
        case 'Doubles':
            choices = list(doubles_groups.keys())
            groups_choice('D', choices)
        case 'Mixed':
            choices = list(mixed_groups.keys())
            groups_choice('M', choices)
        case 'Back':
            view_choice()

def groups_choice(s_d_m, choices):
    choices.sort()
    choices.append('Back')
    competition = inquirer.list_input("Choose a competition", choices=choices)
    match (competition):
        case 'Back':
            view_choice()
        case _:
            match(s_d_m):
                case 'S':
                    if mode == 'interactive':
                        show_snapshot_viewer(singles_groups[competition]["group"], singles_groups[competition]["snapshots"])
                    else: 
                        show_groups_table(singles_groups[competition]["group"])
                case 'D':
                    if mode == 'interactive':
                        show_snapshot_viewer(doubles_groups[competition]["group"], doubles_groups[competition]["snapshots"])
                    else:
                        show_groups_table(doubles_groups[competition]["group"])
                case 'M':
                    if mode == 'interactive':
                        show_snapshot_viewer(mixed_groups[competition]["group"], mixed_groups[competition]["snapshots"])
                    else:
                        show_groups_table(mixed_groups[competition]["group"])
                case _:
                    return