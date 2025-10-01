"""Module defining the Player class and managing player instances."""
# for validation
players_list = []
players_by_start_number = {}

class Player:
    """Class representing a player."""
    def __init__(self, start_number: int, first_name, last_name, country, base, gender, qttr):
        self.start_number = int(start_number)
        self.first_name = first_name
        self.last_name = last_name
        self.country = country
        self.base = base if base != '' else None
        self.gender = gender
        self.qttr = int(qttr) if qttr not in (None, '') else None
        players_list.append(self)   

    def __repr__(self):
        return f"[{self.start_number}] {self.first_name} {self.last_name} ({self.country}, {self.base if self.base is not None else 'No base'})"
