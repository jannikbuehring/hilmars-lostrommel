"""Helpers shared by the terminal viewers and the HTML exporters.

Kept in a module of its own so the group and bracket sides can both use them
without importing each other (the bracket viewer and its HTML exporter used to
form an import cycle around participant_display_fields).
"""
import os
import webbrowser
from pathlib import Path

from models.player import players_by_start_number


def clear_screen():
    """Clear the terminal screen in a cross-platform way."""
    os.system("cls" if os.name == "nt" else "clear")


def open_in_browser(path):
    """Open an exported HTML file in the default browser (best-effort)."""
    try:
        webbrowser.open(Path(path).resolve().as_uri())
    except Exception as exc:  # pragma: no cover - depends on desktop environment
        print(f"Could not open {path} automatically: {exc}")


def participant_display_fields(p, include_qttr=False):
    """Extract structured display data for a participant.

    Returns None for an empty slot, the string "BYE" for a bye, the string
    "ERR" if extraction failed, or a dict:
      {"seeding": int|None, "group_no": int|None, "group_pos": int|None,
       "names": [{"first_name", "last_name", "start_number", "country", "base"}, ...]}
    "names" has one entry for a single player, two for a team. If a player
    can't be resolved via players_by_start_number, its entry is instead
    {"unknown": start_number}.

    *include_qttr* adds each player's "qttr" to their names entry. Off by
    default because the bracket views never show it, and the bracket HTML
    export repeats every participant in every snapshot, where an unused field
    would be paid for thousands of times.

    Consumed by format_participant_display (terminal) and by both HTML
    exporters, so all renderers stay in sync with a single source of truth.
    """
    if p is None:
        return None
    if p == "BYE":
        return "BYE"

    try:
        names = []
        for start_number in (p.start_number_a, getattr(p, 'start_number_b', None)):
            if start_number is None:
                continue
            pl = players_by_start_number.get(start_number)
            if pl is None:
                names.append({"unknown": start_number})
            else:
                name = {
                    "first_name": pl.first_name,
                    "last_name": pl.last_name,
                    "start_number": pl.start_number,
                    "country": pl.country,
                    "base": pl.base,
                }
                if include_qttr:
                    name["qttr"] = pl.qttr
                names.append(name)

        return {
            "seeding": getattr(p, 'seeding', None),
            "group_no": getattr(p, 'group_no', None),
            "group_pos": getattr(p, 'group_pos', None),
            "names": names,
        }
    except Exception:
        return "ERR"
