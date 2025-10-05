"""Module to handle drawing of groups with country conflict avoidance."""
import random
import copy
from models.draw_data import DrawDataRow
from models.snapshot import Snapshot
from checks.group_checker import check_base_uniqueness, check_country_distribution, get_qttr_distributions, check_team_country_distribution
from misc.config import config

# Define a safe EmptySlot class
class EmptySlot:
    """A placeholder for empty group slots."""
    def __init__(self):
        self.country = None
        self.base = None
        self.start_number_a = "EMPTY"
        self.start_number_b = None
        self.competition = None
        self.qttr = None
    def __repr__(self):
        return "Empty Slot"
    def __deepcopy__(self, memo):
        # EmptySlot is stateless, so just return a new instance
        return type(self)()

def draw_groups_monte_carlo(class_subset: list[DrawDataRow], amount_of_groups, max_attempts=10000):
    """Draw groups for a competition class using Monte Carlo optimization to minimize country conflicts."""
    # Helper to record delta snapshots
    snapshots = []
    def snapshot_delta(action: str, groups: list[int], index_in_group: int, participants: list[DrawDataRow], violations, violation_score):
        snapshots.append(Snapshot(action, groups, index_in_group, participants, violations, violation_score))

    def get_violations(groups):
        competition = groups[1][0].competition
        violations = {}
        violations["country"] = check_country_distribution(competition, {"dummy": {"group": groups}})
        violations["base"] = check_base_uniqueness({"dummy": {"group": groups}})
        violations["qttr"] = get_qttr_distributions({"dummy": {"group": groups}}) if (competition == 'S') else []      
        violations["team_country"] = check_team_country_distribution({"dummy": {"group": groups}}) if (competition in ('D', 'M')) else []

        return violations

    def get_violation_count(violations):
        country_violations = violations["country"] 
        base_violations = violations["base"]
        qttr_violations = violations["qttr"]
        team_country_violations = violations["team_country"]
        return len(country_violations) + len(base_violations) + len(qttr_violations) + len(team_country_violations)

    def calculate_violation_score(violations):
        country_violations = violations["country"]
        country_violation_weight = int(config["group_draw_weights"]["country_violation_weight"])
        team_country_violations = violations["team_country"]
        team_country_violation_weight = int(config["group_draw_weights"]["team_country_violation_weight"])
        base_violations = violations["base"]
        base_violation_weight = int(config["group_draw_weights"]["base_violation_weight"])
        qttr_violations = violations["qttr"]
        qttr_violation_weight = int(config["group_draw_weights"]["qttr_violation_weight"])
        return (
            len(country_violations) * country_violation_weight
            + len(team_country_violations) * team_country_violation_weight
            + len(base_violations) * base_violation_weight
            + len(qttr_violations) * qttr_violation_weight
            )


    def calc_max_group_size(num_participants: int, num_groups: int) -> int:
        return -(-num_participants // num_groups)
    
    class_subset.sort(key=lambda d: d.seeding, reverse=True)
    max_group_size = calc_max_group_size(len(class_subset), amount_of_groups)
    groups = {i + 1: [] for i in range(amount_of_groups)}

    # Deterministic batch assignment
    batches = []
    for i in range(0, len(class_subset), amount_of_groups):
        batch = class_subset[i:i + amount_of_groups]
        batches.append(batch)
        for j, participant in enumerate(batch):
            group_no = j + 1
            groups[group_no].append(participant)

    # Fill up groups with EmptySlot for empty slots
    for group_no in groups:
        while len(groups[group_no]) < max_group_size:
            groups[group_no].append(EmptySlot())

    # Monte Carlo optimization
    current_violations = get_violations(groups)
    current_violation_score = calculate_violation_score(current_violations)
    snapshots.append(Snapshot(None, None, None, None, current_violations, current_violation_score, initial_groups=copy.deepcopy(groups)))

    for _ in range(max_attempts):
        # Choose a batch randomly
        batch_idx = random.randint(0, len(batches) - 1)
        batch = batches[batch_idx]
        # Find group slots for this batch, but never swap the first batch (index 0)
        batch_slots = []
        for group_no in groups:
            slot_idx = batch_idx
            if slot_idx == 0:
                continue  # Never swap first batch
            if slot_idx < len(groups[group_no]):
                batch_slots.append((group_no, slot_idx))
        # Only swap if there are at least two eligible slots
        if len(batch_slots) < 2:
            continue
        slot1, slot2 = random.sample(batch_slots, 2)
        g1, idx1 = slot1
        g2, idx2 = slot2
        if idx1 != idx2:
            raise IndexError("This should never happen. Can only swap same index in different groups.")
        p1 = groups[g1][idx1]
        p2 = groups[g2][idx2]
        # Swap
        groups[g1][idx1], groups[g2][idx2] = p2, p1
        # Only keep swap if violation count is not worse
        new_violations = get_violations(groups)
        new_violation_score = calculate_violation_score(new_violations)
        snapshot_delta("swap", [g1, g2], idx1, [p1, p2], new_violations, new_violation_score)
        if new_violation_score <= current_violation_score:
            current_violation_score = new_violation_score
            if current_violation_score == 0:
                break
        else:
            # Revert swap
            groups[g1][idx1], groups[g2][idx2] = p1, p2
            snapshot_delta("revert", [g1, g2], idx1, [p1, p2], current_violations, current_violation_score)
    # Remove EmptySlot placeholders from groups
    for group_no in groups:
        groups[group_no] = [p for p in groups[group_no] if not isinstance(p, EmptySlot)]
    return groups, snapshots