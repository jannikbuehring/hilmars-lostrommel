"""Module for opening a class's group draw as its HTML page."""

import os

from misc.config import config
from viewer.group_html_exporter import export_group_html, group_html_path
from viewer.viewer_shared import open_in_browser


def show_groups(competition, competition_class, groups, snapshots):
    """Open the class's pre-exported group HTML page in the browser."""
    output_dir = config["files"].get("group_html_output_dir", "output/groups")
    # Groups are pre-exported during initialization; open the existing file.
    path = group_html_path(competition, competition_class, output_dir)
    if not os.path.exists(path):
        # Fallback: export on demand if the pre-exported file is missing.
        path = export_group_html(competition, competition_class, groups, snapshots, output_dir)
    if path:
        open_in_browser(path)
    else:
        print("No group draw available to display.")
