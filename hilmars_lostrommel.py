import logging
import os
import sys

from misc.menu import show_main_menu
from misc.initializer import initialize_config, initialize_data
from misc.startup_info import print_startup_info

def get_base_dir():
    """Get the base directory of the application."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()

def main():
    """Main function to initialize and start the application."""
    try:
        print_startup_info()
        initialize_config(BASE_DIR)
        initialize_data()

        print("")
        show_main_menu()
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e} - Returning to main menu\n")
        show_main_menu()

if __name__ == "__main__":
    main()