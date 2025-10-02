class Snapshot:
    """Snapshot for Monte Carlo group assignment optimization."""
    def __init__(self, action, groups, index, participants, violation_count, initial_groups=None):
        self.action = action  # e.g. 'swap', 'revert'
        self.groups = groups  # list of group numbers involved
        self.index = index  # index of the respective member in their group
        self.participants = participants  # list of DrawDataRow (or EmptySlot)
        self.violation_count = violation_count
        self.initial_groups = initial_groups  # Optional initial group state for reference

    def __repr__(self):
        return (f"Snapshot(action={self.action!r}, groups={self.groups!r}, "
                f"participants={self.participants!r}, violation_count={self.violation_count!r})")
