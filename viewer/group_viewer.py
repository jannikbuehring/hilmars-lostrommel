def show_groups_table(groups):
    # Prepare a table for each group
    for group, members in groups.items():
        print(f"\nGroup {group}")

        # Prepare rows for the table
        table_data = []
        for row in members:
            player = players_by_start_number[row.start_number_a]
            table_data.append([row.seeding, player.first_name, player.last_name, player.start_number, player.country, player.base])

        # Print the table using tabulate
        print(tabulate(table_data, headers=["Seeding", "First Name", "Last Name", "Start Number", "Country", "Base"], tablefmt="grid"))
