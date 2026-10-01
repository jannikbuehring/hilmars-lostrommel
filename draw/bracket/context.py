"""Everything one bracket draw derives from its input before placing anyone.

A BracketContext is built once per draw attempt and never changes afterwards
(its lookahead cache aside); the mutable placement lives in state.BracketState.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from checks.bracket_checker import BALANCED_TIERS_BELOW_TOP, participant_countries
from core.config import settings
from draw.bracket.costs import BYE_HALF_BALANCE_WEIGHT, TIER_HALF_BALANCE_WEIGHT
from draw.bracket.hierarchy import bye_hierarchy, winner_level_slots
from models.bracket_geometry import BracketGeometry
from models.draw_data import DrawDataRow, seeding_by_start_numbers


@dataclass(frozen=True)
class BracketContext:
    # The input, seeded and sorted by (group_pos, -seeding).
    participants: list[DrawDataRow]
    # False drops the projected bye/tier half balance (see draw_bracket).
    half_balance: bool
    # draw_bracket's status callback.
    report: Callable[[str], None]

    bracket_size: int
    number_of_matches: int
    byes: int
    geo: BracketGeometry
    hierarchy_groups: list[list[int]]

    # Settings.  joint_batch_max_evaluations is the evaluation budget for the
    # joint per-batch assignment in Phase 1/1b: a batch is solved exactly when
    # its assignment count P(pool, batch) fits the budget, otherwise a hill-climb
    # seeded with the player-by-player result runs for that many iterations.
    # Raising it buys optimality on large batches at the cost of draw runtime.
    max_attempts: int
    joint_batch_max_evaluations: int
    # Weights for bracket_checker.score_bracket and score_round_two (lower score =
    # better bracket).  Their order is checked once, when the config is loaded.
    bracket_weights: dict
    round_two_weights: dict

    top_group_pos: int
    top_participants: list
    # The group winners, strongest first: the order Phase 1 places them in.
    top_sorted: list
    # Ground-truth tier range, taken from the INPUT rather than from a bracket
    # state.  Every tier-guarded checker derives (top, bottom) from the matches it
    # is handed, which is right for a finished bracket but wrong for the partial
    # states this drawer scores: during Phase 1 only the winners are placed, so a
    # derived range reads (top, top) and the three-tier guard switches the
    # round-two rules off exactly where they are needed.
    bracket_bounds: tuple[int, int]
    # How many participants each placement tier will end up holding, so a partial
    # state can tell a finished tier from one still being filled.
    tier_totals: dict
    # Taken from the input for the same reason as bracket_bounds: first-vs-first is
    # only charged above what forced_first_vs_first says the bracket cannot avoid,
    # and a Phase 1 state still missing some winners would under-count it.
    bracket_top_count: int

    # Who gets a bye is fixed by seeding before anything is placed.
    bye_recipients: list
    bye_recipient_ids: set
    # The bye recipients below the winners, placed by Phase 1b.
    non_top_bye_recipients: list
    non_top_bye_ids: set
    # Everyone below the winners without a bye: what Phase 2 places.
    residual_players: list

    # Net load of each group winner on its own half once placed (see half_load_cost).
    top_net_load: dict

    # The bye/tier half projection (see projected_half_balance_units).
    winner_groups: set
    balanced_tiers: range
    half_tracked: list
    half_balance_keys: tuple
    half_balance_weight: dict
    group_half_vector: dict
    free_half_slack: dict

    # winner_country_lookahead's inputs and its per-attempt cache.
    winner_level_slots: dict
    winner_countries: dict
    winner_country_slack: int
    winner_lookahead_cache: dict = field(default_factory=dict)


def resolve_seedings(class_subset):
    """Set every entry's seeding from seeding_by_start_numbers ("A" or "A/B", either order)."""
    for entry in class_subset:
        key = str(entry.start_number_a)
        if entry.start_number_b is not None:
            alternate_key = f"{entry.start_number_b}/{entry.start_number_a}"
            key = f"{entry.start_number_a}/{entry.start_number_b}"
            if key in seeding_by_start_numbers:
                entry.seeding = seeding_by_start_numbers[key]
            elif alternate_key in seeding_by_start_numbers:
                entry.seeding = seeding_by_start_numbers[alternate_key]
            else:
                raise KeyError(f"Seeding key not found for participant: {key} or {alternate_key}")
        else:
            entry.seeding = seeding_by_start_numbers[key]


def _group_half_loads(class_subset, top_group_pos, bye_recipient_ids):
    """Per-group opposite/same-half loads, used to weight each group winner by how
    much it actually loads its OWN half.

    A winner forces its 2nd/3rd (delta 1/2) into the opposite half and its 4th
    (delta 3) into the same half; balancing raw winner counts wrongly assumes every
    group demands the same 2 opposite slots, which breaks for uneven groups (e.g. a
    consolation group missing its 3rd).

    A non-winner bye recipient counts TWICE: its BYE sits opposite it, so it takes
    two slots of the half its group anchor sends it to.  Who gets a bye is fixed by
    seeding before anything is placed, so this is known up front -- counting it as
    one slot let Phase 1 put 8 winners into one half of the S M1 consolation draw
    (15 groups of 4th/5th/6th, 8 byes for the 5th places), leaving the other half
    short of room and the draw on the degrade path.
    """
    group_opp_load: dict = {}
    group_same_load: dict = {}
    for p in class_subset:
        group_no = getattr(p, "group_no", None)
        if group_no is None or p.group_pos is None:
            continue
        delta = p.group_pos - top_group_pos
        slots = 2 if id(p) in bye_recipient_ids else 1
        if delta in (1, 2):
            group_opp_load[group_no] = group_opp_load.get(group_no, 0) + slots
        elif delta == 3:
            group_same_load[group_no] = group_same_load.get(group_no, 0) + slots
    return group_opp_load, group_same_load


def _top_reverse_weight(group_opp_load, group_same_load, group_no):
    """Net load a group's winner places on its OWN half: opposite demand minus
    same-half demand minus the winner's own slot, the byes of its non-winners
    included (see _group_half_loads).  A full group without such byes (2nd + 3rd
    in the opposite half) yields 1 — so this collapses to the plain winner count
    for symmetric brackets — while a group missing its 3rd yields 0."""
    if group_no is None:
        return 1
    return group_opp_load.get(group_no, 0) - group_same_load.get(group_no, 0) - 1


def build_context(class_subset: list[DrawDataRow], half_balance: bool, progress=None) -> BracketContext:
    """Seed and sort *class_subset* in place and derive the draw's fixed inputs."""
    resolve_seedings(class_subset)
    class_subset.sort(key=lambda p: (p.group_pos, -p.seeding))

    num_participants = len(class_subset)
    bracket_size = 1 << (num_participants - 1).bit_length()
    number_of_matches = bracket_size // 2
    byes = bracket_size - num_participants
    logging.debug("Bracket size: %s, participants: %s, byes: %s", bracket_size, num_participants, byes)
    # Half/quarter geometry lives in models.bracket_geometry, shared with the checker.
    geo = BracketGeometry(number_of_matches)
    hierarchy_groups = bye_hierarchy(bracket_size)

    top_group_pos = min(p.group_pos for p in class_subset if p.group_pos is not None)
    top_participants = [p for p in class_subset if p.group_pos == top_group_pos]
    top_sorted = sorted(top_participants, key=lambda p: -p.seeding)
    bracket_bounds = (
        top_group_pos,
        max(p.group_pos for p in class_subset if p.group_pos is not None),
    )
    tier_totals: dict = {}
    for p in class_subset:
        if p.group_pos is not None:
            tier_totals[p.group_pos] = tier_totals.get(p.group_pos, 0) + 1

    bye_recipients = class_subset[:byes]
    bye_recipient_ids = {id(p) for p in bye_recipients}
    non_top_bye_recipients = [p for p in bye_recipients if p.group_pos != top_group_pos]

    # Non-winner byes are already inside the reverse weight (see _group_half_loads),
    # so a winner's own BYE is the only one subtracted here.
    group_opp_load, group_same_load = _group_half_loads(class_subset, top_group_pos, bye_recipient_ids)
    top_net_load = {
        id(p): _top_reverse_weight(group_opp_load, group_same_load, getattr(p, "group_no", None))
        - (1 if id(p) in bye_recipient_ids else 0)
        for p in top_participants
    }

    # ---------------------------------------------------------------------------
    # Rank 3 of the ladder: byes and tiers top..top+2 even over the halves.
    #
    # Both splits are fixed by the group winners' halves long before the players
    # themselves are placed: a winner's 2nd/3rd (and their byes) must go to the
    # opposite half, its 4th to the same one.  Scoring only what is on the board
    # let Phase 1 accept a winner layout that could only end 8/6 on the byes or
    # 4/2 on the winners (review finding N2), and nothing after Phase 1 can change
    # it.  So every participant not yet placed is counted in the half its
    # group's anchor already forces, and only what is truly still open (a group
    # whose winner is pending, a bye recipient below top+3) counts as slack --
    # charged, like half_load_cost, only for the gap the slack can no longer
    # close, so a legal final split is never charged for its build order.
    # ---------------------------------------------------------------------------
    winner_groups = {p.group_no for p in top_participants if getattr(p, "group_no", None) is not None}
    balanced_tiers = range(top_group_pos, top_group_pos + BALANCED_TIERS_BELOW_TOP + 1)
    half_tracked = [
        p for p in class_subset if id(p) in bye_recipient_ids or getattr(p, "group_pos", None) in balanced_tiers
    ]

    # The same projection per group, for winner_country_lookahead's hypothetical
    # completions: what a group adds to (half 0 - half 1) of the byes and of each
    # balanced tier when its winner lands in half 0 (negated for half 1), and the
    # participants no winner binds (their own slack).
    half_balance_keys = ("bye", *balanced_tiers) if half_balance else ()
    half_balance_weight = {
        key: BYE_HALF_BALANCE_WEIGHT if key == "bye" else TIER_HALF_BALANCE_WEIGHT for key in half_balance_keys
    }
    group_half_vector: dict = {}
    free_half_slack = dict.fromkeys(half_balance_keys, 0)
    for p in half_tracked:
        keys = [
            key for key in (("bye",) if id(p) in bye_recipient_ids else ()) + (p.group_pos,) if key in half_balance_keys
        ]
        delta = p.group_pos - top_group_pos
        if getattr(p, "group_no", None) in winner_groups and delta <= 3:
            vector = group_half_vector.setdefault(p.group_no, dict.fromkeys(half_balance_keys, 0))
            for key in keys:
                vector[key] += 1 if delta in (0, 3) else -1
        else:
            for key in keys:
                free_half_slack[key] += 1

    return BracketContext(
        participants=class_subset,
        half_balance=half_balance,
        report=progress or (lambda _msg: None),
        bracket_size=bracket_size,
        number_of_matches=number_of_matches,
        byes=byes,
        geo=geo,
        hierarchy_groups=hierarchy_groups,
        max_attempts=settings.bracket_draw.max_attempts,
        joint_batch_max_evaluations=settings.bracket_draw.joint_batch_max_evaluations,
        bracket_weights=dict(settings.bracket_draw.weights),
        round_two_weights=dict(settings.bracket_draw.round_two_weights),
        top_group_pos=top_group_pos,
        top_participants=top_participants,
        top_sorted=top_sorted,
        bracket_bounds=bracket_bounds,
        tier_totals=tier_totals,
        bracket_top_count=tier_totals.get(top_group_pos, 0),
        bye_recipients=bye_recipients,
        bye_recipient_ids=bye_recipient_ids,
        non_top_bye_recipients=non_top_bye_recipients,
        non_top_bye_ids={id(p) for p in non_top_bye_recipients},
        residual_players=[p for p in class_subset if p.group_pos != top_group_pos and id(p) not in bye_recipient_ids],
        top_net_load=top_net_load,
        winner_groups=winner_groups,
        balanced_tiers=balanced_tiers,
        half_tracked=half_tracked,
        half_balance_keys=half_balance_keys,
        half_balance_weight=half_balance_weight,
        group_half_vector=group_half_vector,
        free_half_slack=free_half_slack,
        winner_level_slots=winner_level_slots(hierarchy_groups, top_sorted),
        winner_countries={id(p): participant_countries(p) for p in top_participants},
        # Same slack as check_country_balance_halves: a team carries two countries.
        winner_country_slack=2 if any(getattr(p, "start_number_b", None) is not None for p in top_participants) else 1,
    )
