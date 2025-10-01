from models.player import players_by_start_number
from tabulate import tabulate
from viewer.view_config import table_format

def show_players_table():
    """Print all players in a tabular format."""
    # Convert to list of rows
    table_data = [[start_number, player.gender, player.qttr, player.first_name, player.last_name, player.country, player.base] for start_number, player in sorted(players_by_start_number.items())]

    # Print table
    print(tabulate(table_data, headers=["Start Number", "Gender", "QTTR", "First Name", "Last Name", "Country", "Base"], tablefmt=table_format))
