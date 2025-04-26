from player import Player

def read_draw_data():
    with open("input/draw_input.csv", "r") as file:
        lines = file.readlines()
    
def read_players():
    with open("input/players.csv", "r") as file:
        lines = file.readlines()
        players = []
        for line in lines[1:]:
            start_number, first_name, last_name, country, base, gender = line.strip().split(",")
            players.append(Player(start_number=start_number, first_name=first_name, last_name=last_name, country=country, base=base, gender=gender))
        return players