import sys

import inquirer

from models.draw_results import COMPETITIONS, DrawResults
from viewer.bracket_viewer import show_bracket
from viewer.group_viewer import show_groups
from viewer.player_viewer import show_players_table


def show_main_menu(results: DrawResults):
    """Display the main menu until the user exits."""
    while True:
        action = inquirer.list_input("Choose what to do", choices=["View", "Exit"])
        if action == "Exit":
            sys.exit()
        _view_menu(results)


def _view_menu(results):
    """Choose Players, Groups or Bracket. Returns to the main menu after showing something."""
    while True:
        # Groups and Bracket open the exported HTML pages; after --no-html those
        # are from an earlier run, so they are not offered.
        views = ["Groups", "Bracket", "Players"] if results.html_exported else ["Players"]
        what_to_view = inquirer.list_input("Choose what to view", choices=[*views, "Back"])
        match what_to_view:
            case "Back":
                return
            case "Players":
                show_players_table()
                return
            case _:
                if _show_competition(results, what_to_view):
                    return


def _show_competition(results, what_to_view):
    """Choose a competition and a class, then open it. Returns False when the user went back."""
    labels = {label: code for code, label in COMPETITIONS}
    label = inquirer.list_input("Choose what to view", choices=[*labels, "Back"])
    if label == "Back":
        return False
    code = labels[label]
    drawn = results.brackets[code] if what_to_view == "Bracket" else results.groups[code]

    competition_class = inquirer.list_input("Choose a competition class", choices=[*sorted(drawn), "Back"])
    if competition_class == "Back":
        return False
    if what_to_view == "Bracket":
        show_bracket(competition=code, competition_class=competition_class, bracket=drawn.get(competition_class, {}))
    else:
        show_groups(
            competition=code,
            competition_class=competition_class,
            groups=drawn[competition_class]["group"],
            snapshots=drawn[competition_class]["snapshots"],
        )
    return True
