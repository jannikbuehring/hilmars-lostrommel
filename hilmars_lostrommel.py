import logging

from misc.menu import *
from misc.initializer import *
from misc.startup_info import *

def main():
    try:
        print_startup_info()
        initialize_config()
        initialize_data()

        print("")
        show_main_menu()
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e} - Returning to main menu\n")
        show_main_menu()

if __name__ == "__main__":
    main()