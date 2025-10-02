import sys
import inquirer
from viewer.group_viewer import show_groups
from viewer.player_viewer import show_players_table
from viewer.bracket_viewer import show_bracket
from misc.initializer import singles_groups, doubles_groups, mixed_groups

TO_SHOW = ""

def show_main_menu():
    """Display the main menu and handle user choices."""
    global TO_SHOW
    TO_SHOW = ""
    action = inquirer.list_input("Choose what to do", choices=['View', 'Exit'])
    match (action):
        case 'View':
            view_choice()
        case 'Exit':
            sys.exit()
    show_main_menu()

def view_choice():
    """Choose what to view: Players, Groups, Bracket, Back to main menu"""
    global TO_SHOW
    what_to_view = inquirer.list_input("Choose what to view", choices=['Players', 'Groups', 'Bracket', 'Back'])
    match (what_to_view):
        case 'Players':
            show_players_table()
        case 'Groups':
            TO_SHOW = "Groups"
            singles_doubles_mixed_choice()
        case 'Bracket':
            TO_SHOW = "Bracket"
            singles_doubles_mixed_choice()
        case 'Back':
            show_main_menu()

def singles_doubles_mixed_choice():
    """Choose between Singles, Doubles, Mixed, Back to previous menu"""
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
    """Choose competition class to view groups or bracket, or go back"""
    global TO_SHOW
    choices.sort()
    choices.append('Back')
    competition_class = inquirer.list_input("Choose a competition class", choices=choices)
    match (competition_class):
        case 'Back':
            view_choice()
        case _:
            match(s_d_m, TO_SHOW):
                case ('S', "Groups"):
                    show_groups(
                        competition=s_d_m,
                        competition_class=competition_class,
                        groups=singles_groups[competition_class]["group"],
                        snapshots= singles_groups[competition_class]["snapshots"]
                        )
                case ('S', "Bracket"):
                    show_bracket("TODO")
                case ('D', "Groups"):
                    show_groups(
                        competition=s_d_m,
                        competition_class=competition_class,
                        groups=doubles_groups[competition_class]["group"],
                        snapshots=doubles_groups[competition_class]["snapshots"]
                        )
                case ('D', "Bracket"):
                    show_bracket("TODO")
                case ('M', "Groups"):
                    show_groups(
                        competition=s_d_m,
                        competition_class=competition_class,
                        groups=mixed_groups[competition_class]["group"],
                        snapshots=mixed_groups[competition_class]["snapshots"]
                        )
                case ('M', "Bracket"):
                    show_bracket("TODO")
                case _:
                    return