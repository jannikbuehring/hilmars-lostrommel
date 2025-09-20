class DrawDataRow:
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

    def __repr__(self):
        return f"{self.competition} {self.competition_class} (Seeding: {self.seeding}, Start number a: {self.start_number_a}, Start number b: {self.start_number_b})"