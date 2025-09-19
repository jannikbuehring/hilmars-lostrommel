class Match:
    def __init__(self, slot_a=None, slot_b=None):
        self.slot_a = slot_a
        self.slot_b = slot_b
        self.winner = None
        self.next_match = None  # link to next round

    def __repr__(self):
        return f"Match({self.slot_a} vs {self.slot_b})"