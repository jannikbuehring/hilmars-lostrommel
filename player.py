class Player:
    def __init__(self, player_number, country, base, rank, group = None):
        self.player_number = player_number
        self.country = country
        self.base = base
        self.rank = rank
        self.group = group

    def __repr__(self):
        return f"Player {self.player_number} (Country: {self.country}, Base: {self.base}, Rank: {self.rank})"
    
    def set_group(self, group):
        self.group = group

    def set_rank(self, rank):
        self.rank = rank