"""Module for opening a class's brackets as their HTML pages."""

import os

import inquirer

from misc.config import config
from viewer.bracket_html_exporter import bracket_html_path, export_bracket_html
from viewer.viewer_shared import open_in_browser


def show_bracket(competition, competition_class, bracket):
    """Choose a bracket type, then open its pre-exported HTML page in the browser."""
    if not bracket or ("main" not in bracket and "consolation" not in bracket):
        print("No bracket information available for this competition class.")
        return

    bracket_types = [
        k
        for k in ("main", "consolation")
        if bracket.get(k) and (bracket[k].get("matches") or bracket[k].get("snapshots"))
    ]
    if not bracket_types:
        print("No bracket matches available to display.")
        return

    if len(bracket_types) == 1:
        bracket_type = bracket_types[0]
    else:
        choice = inquirer.list_input("Choose bracket type", choices=[bt.capitalize() for bt in bracket_types])
        bracket_type = choice.lower()

    if not bracket[bracket_type].get("matches"):
        # A failed draw keeps only its snapshots; no HTML was written for it.
        print("The draw of this bracket failed - no HTML was written.")
        return
    output_dir = config["files"].get("bracket_html_output_dir", "output/brackets")
    # Brackets are pre-exported during initialization; open the existing file.
    path = bracket_html_path(competition, competition_class, bracket_type, output_dir)
    if os.path.exists(path):
        open_in_browser(path)
        return
    # Fallback: export on demand if the pre-exported file is missing.
    single = {bracket_type: bracket[bracket_type]}
    paths = export_bracket_html(competition, competition_class, single, output_dir)
    if paths:
        for p in paths:
            open_in_browser(p)
    else:
        print("No bracket matches available to display.")
