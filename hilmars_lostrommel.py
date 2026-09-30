import logging
import os
import sys

from misc.cli import parse_args
from misc.config import initialize_config
from misc.initializer import DrawResults, initialize_data
from misc.menu import show_main_menu
from misc.startup_info import print_startup_info


def get_base_dir():
    """Get the base directory of the application."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()

_RED = "\033[91m"
_RESET = "\033[0m"


def print_incomplete_run_banner():
    """Warn that this run produced no current output, so nobody posts an old draw."""
    print(f"\n{_RED}{'=' * 78}")
    print("  The draw did NOT complete - no current output CSV or HTML was written.")
    print("  The previous run's files (if any) were moved to the 'previous' folder next to the output CSV.")
    print(f"{'=' * 78}{_RESET}")


def main(argv=None):
    """Main function to initialize and start the application."""
    # Parsed before the banner, so --help, --version and a bad argument print nothing else.
    args = parse_args(argv)
    results = DrawResults()
    try:
        print_startup_info()
        initialize_config(BASE_DIR, args)
        completed = initialize_data(results, export_html=not args.no_html)
        if not completed:
            print_incomplete_run_banner()
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}\n")
        print_incomplete_run_banner()
        completed = False

    if args.no_menu:
        sys.exit(0 if completed else 1)
    print("")
    show_main_menu(results)


if __name__ == "__main__":
    main()
