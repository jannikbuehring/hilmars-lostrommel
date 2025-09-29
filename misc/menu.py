import inquirer
import sys
from viewer.group_viewer import *
from viewer.player_viewer import show_players_table
from viewer.bracket_viewer import show_bracket_table
from misc.initializer import *
from hilmars_lostrommel import *

to_show = ""

def show_main_menu():
    global to_show
    to_show = ""
    action = inquirer.list_input("Choose what to do", choices=['View', 'Exit'])
    match (action):
        case 'View':
            view_choice()
        case 'Exit':
            sys.exit()
    show_main_menu()

def view_choice():
    global to_show
    what_to_view = inquirer.list_input("Choose what to view", choices=['Players', 'Groups', 'Bracket', 'Back'])
    match (what_to_view):
        case 'Players':
            show_players_table()
        case 'Groups':
            to_show = "Groups"
            singles_doubles_mixed_choice()
        case 'Bracket':
            to_show = "Bracket"
            singles_doubles_mixed_choice()
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
    global to_show
    choices.sort()
    choices.append('Back')
    competition = inquirer.list_input("Choose a competition", choices=choices)
    match (competition):
        case 'Back':
            view_choice()
        case _:
            match(s_d_m, to_show):
                case ('S', "Groups"):
                    show_groups(singles_groups[competition]["group"], singles_groups[competition]["snapshots"])
                case ('S', "Bracket"):
                    show_bracket("TODO")
                case ('D', "Groups"):
                    show_groups(doubles_groups[competition]["group"], doubles_groups[competition]["snapshots"])
                case ('D', "Bracket"):
                    show_bracket("TODO")
                case ('M', "Groups"):
                    show_groups(mixed_groups[competition]["group"], mixed_groups[competition]["snapshots"])
                case ('M', "Bracket"):
                    show_bracket("TODO")
                case _:
                    return