from models.player import players_by_start_number
from tabulate import tabulate

def show_groups_table(groups):
    
    for number, group in groups.items():
        table_data = []
        for index, member in enumerate(group):
            player = players_by_start_number[member.start_number_a]
            table_data.append([index + 1, member.seeding, player.first_name, player.last_name, player.start_number, player.country, player.base])

        # Print the table using tabulate
        print(f"Group {number}")
        print(tabulate(table_data, headers=["#", "Seeding", "First Name", "Last Name", "Start Number", "Country", "Base"], tablefmt="grid"))
        print("")