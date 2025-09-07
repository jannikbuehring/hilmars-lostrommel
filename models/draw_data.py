class DrawDataRow:
    def __init__(self, competition, competition_class, seeding: int, amount_of_groups: int, group_no: int, group_pos: int, main_round: bool, consolation_round: bool, start_number_a: int, start_number_b: int | None = None):
        self.competition = competition
        self.competition_class = competition_class
        self.seeding = int(seeding)
        self.amount_of_groups = int(amount_of_groups)
        self.group_no = int(group_no)
        self.group_pos = int(group_pos)
        self.main_round = main_round
        self.consolation_round = consolation_round
        self.start_number_a = int(start_number_a)
        self.start_number_b = int(start_number_b) if start_number_b != '' else None