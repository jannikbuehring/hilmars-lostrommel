groups = {}

class Group:
    def __init__(self, s_d_m, competition, seeding):
        self.s_d_m = s_d_m
        self.competition = competition
        self.seeding = seeding
        self.a = "XD"
        groups[(self.start_number + self.competition)] = self
        

    def __repr__(self):
        return f"{self.first_name} {self.last_name} (Gender: {self.gender}, Country: {self.country}, Base: {self.base})"