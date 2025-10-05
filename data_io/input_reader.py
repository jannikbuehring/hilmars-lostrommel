from models.player import Player
from models.draw_data import DrawDataRow
from misc.config import config

def read_draw_data() -> list[DrawDataRow]:
    """Read draw data from the specified CSV file and return a list of DrawDataRow objects."""
    draw_data_file_path = config["files"]["draw_data_path"]
    with open(draw_data_file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        draw_data = []
        for line in lines[1:]:
            competition, competition_class, amount_of_groups, seeding, group_no, group_pos, main_round, consolation_round, start_number_a, start_number_b = line.strip().split(";")
            draw_data.append(DrawDataRow(competition=competition, competition_class=competition_class, seeding=seeding, amount_of_groups=amount_of_groups, group_no=group_no, group_pos=group_pos, main_round=bool(main_round), consolation_round=bool(consolation_round), start_number_a=start_number_a, start_number_b=start_number_b))
        return draw_data

def read_players() -> list[Player]:
    """Read player data from the specified CSV file and return a list of Player objects."""
    player_file_path = config["files"]["players_path"]
    with open(player_file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        players = []
        for line in lines[1:]:
            start_number, last_name, first_name, country, base, gender, qttr = line.strip().split(";")
            players.append(Player(start_number=start_number, first_name=first_name, last_name=last_name, country=country, base=base, gender=gender, qttr=qttr))
        return players
