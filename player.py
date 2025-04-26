class Player:
    def __init__(self, start_number, first_name, last_name, country, base, gender):
        self.start_number = start_number
        self.first_name = first_name
        self.last_name = last_name
        self.country = country
        self.base = base
        self.gender = gender

    def __repr__(self):
        return f"{self.start_number}: {self.first_name} {self.last_name} (Country: {self.country}, Base: {self.base})"