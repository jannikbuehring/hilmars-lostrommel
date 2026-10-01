"""Module to handle drawing of groups with country conflict avoidance."""

import copy
import logging
import random

from checks.group_checker import (
    check_base_uniqueness,
    check_country_distribution,
    check_team_country_distribution,
    get_qttr_violations,
)
from misc.config import settings
from models.draw_data import DrawDataRow
from models.snapshot import Snapshot

# How often (in swap steps) the optimiser reports its progress.
PROGRESS_INTERVAL = 250


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


def draw_groups_monte_carlo(class_subset: list[DrawDataRow], amount_of_groups, progress=None):
    """Draw groups for a competition class using Monte Carlo optimization to minimize country conflicts.
    Retries with different random seeds if the score is not 0, up to a configurable limit.

    progress: optional callable taking one plain-language status line, called at
    each attempt start, on every new best score and every PROGRESS_INTERVAL steps.
    """
    report = progress or (lambda _msg: None)
    group_settings = settings.group_draw
    max_iterations = group_settings.max_iterations
    max_no_improvement_iterations = group_settings.max_no_improvement_iterations
    max_escape_attempts = group_settings.max_escape_attempts
    max_seed_retries = group_settings.max_seed_retries

    best_groups = None
    best_snapshots = None
    best_score = float("inf")

    for attempt_no in range(1, max_seed_retries + 1):
        seed = random.randint(1, 99999999)
        random.seed(seed)

        snapshots = []

        def snapshot_delta(
            action: str,
            groups: list[int],
            index_in_group: int,
            participants: list[DrawDataRow],
            violations,
            violation_score,
        ):
            snapshots.append(Snapshot(action, groups, index_in_group, participants, violations, violation_score))

        def get_violations(groups):
            competition = groups[1][0].competition
            violations = {}
            violations["country"] = check_country_distribution(competition, groups)
            violations["base"] = check_base_uniqueness(groups)
            violations["qttr"] = get_qttr_violations(groups) if (competition == "S") else []
            violations["team_country"] = check_team_country_distribution(groups) if (competition in ("D", "M")) else []
            return violations

        def calculate_violation_score(violations):
            return (
                sum(v[4] for v in violations["country"]) * group_settings.country_violation_weight
                + sum(v[5] for v in violations["team_country"]) * group_settings.team_country_violation_weight
                + len(violations["base"]) * group_settings.base_violation_weight
                + len(violations["qttr"]) * group_settings.qttr_violation_weight
            )

        def calc_max_group_size(num_participants: int, num_groups: int) -> int:
            return -(-num_participants // num_groups)

        class_subset.sort(key=lambda d: d.seeding, reverse=True)
        max_group_size = calc_max_group_size(len(class_subset), amount_of_groups)
        groups = {i + 1: [] for i in range(amount_of_groups)}

        # Deterministic batch assignment
        batches = []
        for i in range(0, len(class_subset), amount_of_groups):
            batch = class_subset[i : i + amount_of_groups]
            batches.append(batch)
            for j, participant in enumerate(batch):
                group_no = j + 1
                groups[group_no].append(participant)

        # Fill up groups with EmptySlot for empty slots
        for group_no in groups:
            while len(groups[group_no]) < max_group_size:
                groups[group_no].append(EmptySlot())

        report(f"attempt {attempt_no} of {max_seed_retries} - arranging players by seeding...")

        # Monte Carlo optimization with escape from local minima
        current_violations = get_violations(groups)
        current_violation_score = calculate_violation_score(current_violations)
        snapshots.append(
            Snapshot(
                None,
                None,
                None,
                None,
                current_violations,
                current_violation_score,
                state=copy.deepcopy(groups),
            )
        )

        # Best state visited in this seed; escapes may walk away from it, so it is
        # what gets returned (and snapshots are cut back to it for the replay).
        seed_best_score = current_violation_score
        seed_best_groups = {g: list(m) for g, m in groups.items()}
        seed_best_len = len(snapshots)

        no_improvement_count = 0
        escape_attempts = 0

        # With a single batch (entries <= groups) there is nothing to swap, since the
        # first batch is never touched: keep the deterministic placement as is.
        swappable = len(batches) > 1

        def report_step(step):
            best = min(seed_best_score, best_score)
            report(
                f"attempt {attempt_no} of {max_seed_retries}, step {step:,} of {max_iterations:,}"
                f" - current score {current_violation_score}, best so far {best} (0 = perfect)"
            )

        if not swappable:
            report("nothing to optimise - groups are fixed by seeding")

        for step in range(1, (max_iterations if swappable else 0) + 1):
            if step % PROGRESS_INTERVAL == 0:
                report_step(step)
            # Choose a batch randomly, never swap first batch
            batch_idx = random.randint(1, len(batches) - 1)
            batch = batches[batch_idx]
            # Find group slots for this batch, but never swap the first batch (index 0)
            batch_slots = []
            for group_no in groups:
                if batch_idx < len(groups[group_no]):
                    batch_slots.append((group_no, batch_idx))
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
            new_violations = get_violations(groups)
            new_violation_score = calculate_violation_score(new_violations)
            snapshot_delta("swap", [g1, g2], idx1, [p1, p2], new_violations, new_violation_score)

            if new_violation_score < current_violation_score:
                current_violation_score = new_violation_score
                current_violations = new_violations
                no_improvement_count = 0
                if current_violation_score < seed_best_score:
                    seed_best_score = current_violation_score
                    seed_best_groups = {g: list(m) for g, m in groups.items()}
                    seed_best_len = len(snapshots)
                    escape_attempts = 0  # Only reset on a new best, not on climbing back
                    report_step(step)
                if current_violation_score == 0:
                    report("perfect draw found (score 0)")
                    break
            elif new_violation_score == current_violation_score:
                no_improvement_count += 1
                current_violations = new_violations
                current_violation_score = new_violation_score
                # escape_attempts unchanged
            else:
                # Bad swap: only allow if stuck in local minimum
                if no_improvement_count >= max_no_improvement_iterations and escape_attempts < max_escape_attempts:
                    escape_attempts += 1
                    # Accept the bad swap, but don't reset no_improvement_count
                    current_violation_score = new_violation_score
                    current_violations = new_violations
                else:
                    # Revert swap
                    groups[g1][idx1], groups[g2][idx2] = p1, p2
                    snapshot_delta("revert", [g1, g2], idx1, [p1, p2], current_violations, current_violation_score)
                    no_improvement_count += 1

        # Return the best state of this seed, not wherever the walk ended
        groups = seed_best_groups
        current_violation_score = seed_best_score
        del snapshots[seed_best_len:]

        # Remove EmptySlot placeholders from groups
        for group_no in groups:
            groups[group_no] = [p for p in groups[group_no] if not isinstance(p, EmptySlot)]

        # Track best result
        if current_violation_score < best_score:
            best_score = current_violation_score
            best_groups = copy.deepcopy(groups)
            best_snapshots = list(snapshots)
        if best_score == 0 or not swappable:
            break  # Early exit if perfect solution found, or if every retry would give the same result

    if best_score > 0:
        # Logged, not printed: a print would land inside the draw spinner, and the
        # group validation stage lists the remaining violations anyway.
        logging.info(
            "Could not achieve perfect group draw after %s seed attempts. Best score: %s", max_seed_retries, best_score
        )

    return best_groups, best_snapshots
