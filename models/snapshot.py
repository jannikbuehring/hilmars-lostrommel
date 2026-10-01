class Snapshot:
    """Audit-trail entry for a step of the group or bracket draw."""

    def __init__(self, action, groups, index, participants, violations, violation_score, state=None):
        self.action = action  # e.g. 'swap', 'revert'
        self.groups = groups  # list of group numbers involved
        self.index = index  # index of the respective member in their group
        self.participants = participants  # list of DrawDataRow (or EmptySlot)
        self.violations = violations
        self.violation_score = violation_score
        self.state = state  # Optional full state at this step: groups (group draw) or matches (bracket draw)

    def __repr__(self):
        return (
            f"Snapshot(action={self.action!r}, groups={self.groups!r}, "
            f"participants={self.participants!r}, violation_score={self.violation_score!r})"
        )
