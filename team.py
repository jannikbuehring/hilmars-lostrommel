from player import Player

class Team:
    def __init__(self, rank, group, player_a: Player, player_b: Player):
        self.rank = rank
        self.group = group
        self.player_a = player_a
        self.player_b = player_b

    def __repr__(self):
        return f"Team {self.rank} (Player A: {self.player_a.start_number}. Player B: {self.player_b.start_number})"