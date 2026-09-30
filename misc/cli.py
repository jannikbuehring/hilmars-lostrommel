"""Command-line arguments of hilmars_lostrommel.py.

Every override defaults to None ("not given"), so a run without arguments
behaves exactly like one that only reads config.ini. misc.config applies the
given values on top of the parsed ini file.
"""

import argparse
import logging

from misc.version import APP_NAME, __version__


def _log_level(text):
    """argparse type for --log-level: a level name (any case) or its number."""
    level = logging.getLevelNamesMapping().get(text.upper())
    if level is not None:
        return level
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid log level {text!r} (use debug/info/warning/error/critical or 10-50)"
        ) from None


def build_parser():
    parser = argparse.ArgumentParser(
        prog="hilmars_lostrommel",
        description=f"{APP_NAME}: group draws and knock-out brackets. "
        "Options given here override the matching config.ini keys for this run.",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--config", metavar="PATH", help="config file to load (default: config/config.ini)")
    parser.add_argument("--players", metavar="PATH", help="players CSV, overrides [files] players_path")
    parser.add_argument("--draw-input", metavar="PATH", help="draw input CSV, overrides [files] draw_data_path")
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="output CSV, overrides [files] output_file_path; the report is written next to it",
    )
    parser.add_argument("--seed", help="random seed, overrides [settings] random_seed")
    parser.add_argument(
        "--log-level",
        type=_log_level,
        metavar="LEVEL",
        help="debug/info/warning/error/critical or 10-50, overrides [settings] log_level",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="skip the HTML export and leave the existing HTML pages untouched",
    )
    parser.add_argument(
        "--no-menu",
        action="store_true",
        help="exit after the draw instead of opening the menu (exit code 1 if the draw did not complete)",
    )
    return parser


def parse_args(argv=None):
    """Parse `argv` (default: sys.argv[1:])."""
    return build_parser().parse_args(argv)
