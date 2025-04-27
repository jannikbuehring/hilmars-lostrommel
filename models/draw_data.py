class DrawDataRow:
    def __init__(self, competition, competition_class, seeding, amount_of_groups, group_no, group_pos, main_round: bool, consolation_round: bool, start_number_a, start_number_b):
        self.competition = competition
        self.competition_class = competition_class
        self.seeding = seeding
        self.amount_of_groups = amount_of_groups
        self.group_no = group_no
        self.group_pos = group_pos
        self.main_round = main_round
        self.consolation_round = consolation_round
        self.start_number_a = start_number_a
        self.start_number_b = start_number_b