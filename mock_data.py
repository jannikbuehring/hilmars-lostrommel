import random
from itertools import pairwise
from player import Player
from team import Team

random.seed(1000)

countries = ["USA", "GER", "FRA", "ISR", "CZE", "AUT"]
bases = {"GER": ["Frankfurt", "Berlin", "München"], 
         "USA": ["New York", "Los Angeles"], 
         "FRA": ["Lyon"],
         "ISR": ["Jerusalem"],
         "CZE": ["Prag"],
         "AUT": ["Wien", "Graz"]
         }

def mock_players(amount_of_players, amount_of_groups=1):
    players = []

    for i in range(amount_of_players):
        player_number = random.randint(1, 400)
        country = random.choice(countries)
        base = random.choice(bases[country])
        group = i % amount_of_groups
        players.append(Player(player_number=player_number, country=country, base=base, rank=i+1, group=group))

    return players

def mock_teams(amount_of_teams, amount_of_groups=1):
    players = mock_players(amount_of_players=amount_of_teams * 2)
    random.shuffle(players)

    teams = []

    for index, (player_a, player_b) in enumerate(zip(players[::2], players[1::2])):
        group = index % amount_of_groups
        team = Team(rank=index, group=group, player_a=player_a, player_b=player_b)
        teams.append(team)

    return teams