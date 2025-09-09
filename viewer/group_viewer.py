from models.player import players_by_start_number
from tabulate import tabulate

def show_groups_table(groups):
    for number, group in groups.items():
        table_data = []

        print(f"Group {number}")

        # Single Group
        if group[0].start_number_b == None:
            for index, member in enumerate(group):
                player = players_by_start_number[member.start_number_a]
                table_data.append([index + 1, member.seeding, player.first_name, player.last_name, player.start_number, player.country, player.base])
            print(tabulate(table_data, headers=["#", "Seeding", "First Name", "Last Name", "Start Number", "Country", "Base"], tablefmt="grid"))
       # Team Group
        else:
            for index, participant in enumerate(group):
                player_a = players_by_start_number[participant.start_number_a]
                player_b = players_by_start_number[participant.start_number_b]
                table_data.append([index + 1, participant.seeding, player_a.last_name + "/" + player_b.last_name, str(player_a.start_number) + "/" + str(player_b.start_number), player_a.country + "/" + player_b.country, str(player_a.base) + "/" + str(player_b.base)])
            print(tabulate(table_data, headers=["#", "Seeding", "Last Names", "Start Numbers", "Countries", "Bases"], tablefmt="grid"))

    print("")