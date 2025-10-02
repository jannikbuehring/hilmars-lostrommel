"""Data structures for draw data input."""
from models.player import players_by_start_number

seeding_by_start_numbers = {}

class DrawDataRow:
    """Data structure for a row in the draw data input."""
    def __init__(self, competition, competition_class, seeding: int, amount_of_groups: int, group_no: int, group_pos: int, main_round: bool, consolation_round: bool, start_number_a: int, start_number_b: int):
        self.competition = competition
        self.competition_class = competition_class
        self.seeding = int(seeding) if seeding != '' else None
        self.amount_of_groups = int(amount_of_groups) if amount_of_groups != '' else None
        self.group_no = int(group_no) if group_no != '' else None
        self.group_pos = int(group_pos) if group_pos != '' else None
        self.main_round = main_round
        self.consolation_round = consolation_round
        self.start_number_a = int(start_number_a)
        self.start_number_b = int(start_number_b) if start_number_b != '' else None
        
        if self.seeding is not None:
            key = str(start_number_a)
            if self.start_number_b is not None:
                key += "/" + str(start_number_b)
            seeding_by_start_numbers[key] = self.seeding

    def __repr__(self):
        return f"{self.competition} {self.competition_class} (Seeding: {self.seeding}, Player A: {self.start_number_a}, {players_by_start_number[self.start_number_a].country}. Player B: {self.start_number_b}, {players_by_start_number[self.start_number_b].country if self.start_number_b is not None else ''})"
    