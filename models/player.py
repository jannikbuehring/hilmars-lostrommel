# for validation
players_list = []
players_by_start_number = {}

class Player:
    def __init__(self, start_number: int, first_name, last_name, country, base, gender):
        self.start_number = int(start_number)
        self.first_name = first_name
        self.last_name = last_name
        self.country = country
        self.base = base if base != '' else None
        self.gender = gender
        players_list.append(self)    

    def __repr__(self):
        return f"[{self.start_number}] {self.first_name} {self.last_name} ({self.country}, {self.base if self.base != None else 'No base'})"