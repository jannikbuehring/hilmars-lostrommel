"""Helpers shared by the viewers and the HTML exporters.

Kept in a module of its own so the group and bracket sides can both use them
without importing each other (the bracket viewer and its HTML exporter used to
form an import cycle around participant_display_fields). Besides participant
display data this holds the page heading, the provenance footer and the loader
for the CSS/JS in viewer/assets/, so both exported pages look alike.
"""

import functools
import html
import webbrowser
from datetime import datetime
from pathlib import Path

from core.version import APP_NAME, __version__
from models.player import players_by_start_number

# Bundled next to this module; the PyInstaller spec ships the folder as datas,
# so the path resolves the same from source and from the frozen exe.
_ASSETS_DIR = Path(__file__).with_name("assets")


@functools.cache
def read_asset(name):
    """Return the text of a CSS/JS file from viewer/assets/ (read once, then cached)."""
    return (_ASSETS_DIR / name).read_text(encoding="utf-8")


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

    Consumed by both HTML exporters, so they stay in sync with a single
    source of truth.
    """
    if p is None:
        return None
    if p == "BYE":
        return "BYE"

    try:
        names = []
        for start_number in (p.start_number_a, getattr(p, "start_number_b", None)):
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
            "seeding": getattr(p, "seeding", None),
            "group_no": getattr(p, "group_no", None),
            "group_pos": getattr(p, "group_pos", None),
            "names": names,
        }
    except Exception:
        return "ERR"


def participant_key(p):
    """Stable identity key for a participant, independent of object id()/deepcopy."""
    if p is None or p == "BYE":
        return None
    key = str(p.start_number_a)
    if getattr(p, "start_number_b", None) is not None:
        key += "/" + str(p.start_number_b)
    return key


_COMPETITION_NAMES = {"S": "Singles", "D": "Doubles", "M": "Mixed"}
_CLASS_GENDER_NAMES = {"M": "Men", "W": "Women", "X": "Mixed"}


def class_display_name(competition, competition_class, bracket_type):
    """Human-readable class heading, e.g. ("S", "M1", "main") -> "Singles Men 1 Main".

    Falls back to the raw codes for any competition/class shape not covered by
    the maps, so an unexpected class code still produces a usable heading.
    """
    competition_name = _COMPETITION_NAMES.get(competition, competition)
    class_name = competition_class
    if len(competition_class) >= 2 and competition_class[0] in _CLASS_GENDER_NAMES:
        gender_name = _CLASS_GENDER_NAMES[competition_class[0]]
        # Mixed classes ("X") inside the Mixed competition would read
        # "Mixed Mixed 1"; drop the redundant repetition.
        prefix = "" if gender_name == competition_name else f"{gender_name} "
        class_name = f"{prefix}{competition_class[1:]}"
    return f"{competition_name} {class_name} {bracket_type.capitalize()}"


def format_duration(seconds):
    """Human-readable duration, or None if no duration was recorded."""
    if seconds is None:
        return None
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)} min {remainder:.1f} s"


def render_footer(heading, draw_seconds, run_meta):
    """Provenance line below the bracket or groups: which build produced this
    file, when, and how long it took.

    *run_meta* is absent when the exporter runs outside the initialization
    pipeline (the on-demand re-export in bracket_viewer/group_viewer), so every part is
    optional and simply omitted when its value is missing.
    """
    meta = run_meta or {}
    version = meta.get("version", __version__)

    parts = [f"{APP_NAME} v{version}"]

    draw_text = format_duration(draw_seconds)
    if draw_text:
        parts.append(f"{heading} drawn in {draw_text}")

    total_text = format_duration(meta.get("total_seconds"))
    if total_text:
        parts.append(f"total run {total_text}")

    seed = meta.get("random_seed")
    if seed:
        parts.append(f"seed {seed}")

    parts.append(f"generated {meta.get('generated_at') or datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return f'<footer class="export-meta">{html.escape(" · ".join(str(p) for p in parts))}</footer>'
