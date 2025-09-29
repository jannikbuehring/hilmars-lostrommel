import logging
import os
import sys

from misc.menu import *
from misc.initializer import *
from misc.startup_info import *

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()

def main():
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