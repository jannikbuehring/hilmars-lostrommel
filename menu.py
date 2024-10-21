'''
# Initialize colorama for Windows
init()

# Define menu options
menu = ["Group Draw", "Main/Consolation Draw", "Exit"]
current_row = 0

# Key scan codes (these codes should work regardless of keyboard layout)
KEY_UP = 72
KEY_DOWN = 80
KEY_ENTER = 28

def main():
    global current_row

    print_menu()  # Print the initial menu with startup info

    while True:
        event = keyboard.read_event()  # Read the key press event

        if event.event_type == "down":  # Only react to key presses (not releases)
            scan_code = event.scan_code

            if scan_code == KEY_UP and current_row > 0:
                current_row -= 1
                print_menu()
            elif scan_code == KEY_DOWN and current_row < len(menu) - 1:
                current_row += 1
                print_menu()
            elif scan_code == KEY_ENTER:
                selected_option = menu[current_row]
                if selected_option == "Exit":
                    print("Exiting the program...")
                    break
                else:
                    if current_row == 0:
                        select_group_draw()
                    elif current_row == 1:
                        simulate_main_draw()
                    
                    print("Press Enter to return to the main menu")
                    print_menu()

if __name__ == "__main__":
    main()

    def print_menu():
    os.system('cls' if os.name == 'nt' else 'clear')  # Clear the console
    print_startup_info()
    for idx, option in enumerate(menu):
        if idx == current_row:
            print(Fore.YELLOW + f"> {option}" + Style.RESET_ALL)  # Highlight selected option
        else:
            print(f"  {option}")
'''