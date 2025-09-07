from models.player import Player
from models.draw_data import DrawDataRow

def read_draw_data():
    with open("input/draw_input.csv", "r", encoding="utf-8") as file:
        lines = file.readlines()
        draw_data = []
        for line in lines[1:]:
            competition, competition_class, amount_of_groups, seeding, group_no, group_pos, main_round, consolation_round, start_number_a, start_number_b = line.strip().split(";")
            draw_data.append(DrawDataRow(competition=competition, competition_class=competition_class, seeding=seeding, amount_of_groups=amount_of_groups, group_no=group_no, group_pos=group_pos, main_round=bool(main_round), consolation_round=bool(consolation_round), start_number_a=start_number_a, start_number_b=start_number_b))
        return draw_data

def read_players():
    with open("input/players.csv", "r", encoding="utf-8") as file:
        lines = file.readlines()
        players = []
        for line in lines[1:]:
            start_number, last_name, first_name, country, base, gender = line.strip().split(";")
            players.append(Player(start_number=start_number, first_name=first_name, last_name=last_name, country=country, base=base, gender=gender))
        return players