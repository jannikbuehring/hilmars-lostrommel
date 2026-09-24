import logging
import os
import sys

from misc.menu import show_main_menu
from misc.initializer import initialize_data
from misc.config import initialize_config
from misc.startup_info import print_startup_info

def get_base_dir():
    """Get the base directory of the application."""
    if getattr(sys, 'frozen', False):
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


def main():
    """Main function to initialize and start the application."""
    try:
        print_startup_info()
        initialize_config(BASE_DIR)
        completed = initialize_data()
        if not completed:
            print_incomplete_run_banner()

        print("")
        show_main_menu()
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e} - Returning to main menu\n")
        print_incomplete_run_banner()
        show_main_menu()

if __name__ == "__main__":
    main()
