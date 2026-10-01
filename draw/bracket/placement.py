"""Joint placement of a whole batch of participants (Phase 1 winners, Phase 1b byes).

Every participant of a seeding batch is assigned in ONE optimisation rather
than one at a time, so an early player's locally-best slot can no longer
force a worse assignment on the rest of its batch.
"""

import itertools
import math
import random

from draw.bracket.context import BracketContext
from draw.bracket.costs import assignment_quality_cost, half_load_cost, placement_penalty
from draw.bracket.lookahead import winner_country_lookahead
from draw.bracket.state import BracketState, Trial, bracket_score, opponent_slot, slots_to_matches


def max_matching(items, allowed):
    """Maximum bipartite matching (Kuhn's algorithm): items -> slots.

    *items* is an ordered list of keys, *allowed* maps each key to its set of
    candidate slots.  Returns {slot: item}; a perfect matching exists for the
    whole list iff len(result) == len(items).  Candidate slots are visited in
    sorted order so the result is deterministic under the shared seeded RNG.
    """
    match = {}

    def _augment(item, seen):
        for slot in sorted(allowed[item]):
            if slot in seen:
                continue
            seen.add(slot)
            if slot not in match or _augment(match[slot], seen):
                match[slot] = item
                return True
        return False

    for item in items:
        _augment(item, set())
    return match


def _add_finished_cost(ctx: BracketContext, total, trial: Trial):
    """*total* plus the terms charged once on a finished batch (ranks 1, 3, 4 and the tiebreakers)."""
    trial_matches = slots_to_matches(ctx, trial.state)
    total += half_load_cost(ctx, trial.tops) + winner_country_lookahead(ctx, trial.state, trial.tops)
    total += bracket_score(ctx, trial_matches)
    total += assignment_quality_cost(ctx, trial_matches, trial.tops)
    return total


def evaluate_assignment(ctx: BracketContext, state: BracketState, participants, slots):
    """Total cost of assigning *participants* (in order) to *slots*.

    Simulates the sequential commit, summing the same per-step penalties the
    single-slot placer used, then scores the finished batch ONCE.  Because a
    sequential greedy result is itself one of the assignments in this search
    space and scores identically here, the joint search can only match or
    beat the old player-by-player behaviour.

    Returns the cost, or None when the assignment is infeasible (slot taken,
    or bye-adjacency blocked by an earlier player of the same batch).
    """
    trial = state.trial()
    total = 0
    for participant, slot in zip(participants, slots):
        needs_bye = id(participant) in ctx.bye_recipient_ids
        if trial.state[slot] is not None:
            return None
        if needs_bye and trial.state[opponent_slot(slot)] is not None:
            return None
        total += placement_penalty(ctx, slot, trial, needs_bye)
        trial.apply(ctx, participant, slot, needs_bye)
    return _add_finished_cost(ctx, total, trial)


def greedy_assignment(ctx: BracketContext, state: BracketState, participants, pool, allowed_slots):
    """Player-by-player assignment — the pre-joint behaviour, kept as the
    starting point for the hill-climb on batches too large to enumerate."""
    trial = state.trial()
    chosen = []
    for participant in participants:
        needs_bye = id(participant) in ctx.bye_recipient_ids
        allowed = allowed_slots[id(participant)] if allowed_slots is not None else None
        best = None
        for slot in pool:
            if slot in chosen or (allowed is not None and slot not in allowed):
                continue
            if trial.state[slot] is not None:
                continue
            if needs_bye and trial.state[opponent_slot(slot)] is not None:
                continue
            step = trial.copy()
            cost = placement_penalty(ctx, slot, trial, needs_bye)
            step.apply(ctx, participant, slot, needs_bye)
            cost = _add_finished_cost(ctx, cost, step)
            if best is None or cost < best[0]:
                best = (cost, slot)
        if best is None:
            return None
        slot = best[1]
        chosen.append(slot)
        trial.apply(ctx, participant, slot, needs_bye)
    return chosen


def matching_seed(ctx: BracketContext, state: BracketState, participants, pool, allowed_slots):
    """Feasibility-only assignment, used when greedy_assignment strands a player.

    greedy_assignment picks each slot by cost, so an early low-cost choice can
    leave a later participant with nothing even though the batch is solvable.
    Ignoring cost entirely and solving the pure bipartite matching gives a
    starting point for the hill-climb in exactly those cases.  Returns the slot
    list aligned with *participants*, or None when no perfect matching exists.
    """
    slot_state = state.slot_state
    candidates = {}
    for participant in participants:
        needs_bye = id(participant) in ctx.bye_recipient_ids
        allowed = allowed_slots[id(participant)] if allowed_slots is not None else None
        candidates[id(participant)] = {
            slot
            for slot in pool
            if (allowed is None or slot in allowed)
            and slot_state[slot] is None
            and not (needs_bye and slot_state[opponent_slot(slot)] is not None)
        }
    ids = [id(p) for p in participants]
    matched = max_matching(ids, candidates)
    if len(matched) < len(ids):
        return None
    slot_for = {item: slot for slot, item in matched.items()}
    return [slot_for[i] for i in ids]


def _violates_mask(participants, slots, allowed_slots):
    return allowed_slots is not None and any(s not in allowed_slots[id(p)] for p, s in zip(participants, slots))


def _best_assignment(ctx: BracketContext, state: BracketState, participants, pool, allowed_slots):
    """The cheapest assignment of *participants* to *pool*, or None if none is feasible.

    Solved exactly when the assignment count fits joint_batch_max_evaluations,
    otherwise by a hill-climb (random swaps/moves) from the player-by-player
    result.  Ties are broken at random.
    """
    k = len(participants)
    budget = ctx.joint_batch_max_evaluations
    best_cost = None
    candidates = []
    if math.perm(len(pool), k) <= budget:
        # Small enough to solve exactly.
        for slots in itertools.permutations(pool, k):
            if _violates_mask(participants, slots, allowed_slots):
                continue
            cost = evaluate_assignment(ctx, state, participants, list(slots))
            if cost is None:
                continue
            if best_cost is None or cost < best_cost:
                best_cost, candidates = cost, [list(slots)]
            elif cost == best_cost:
                candidates.append(list(slots))
    else:
        # Too large to enumerate: start from the player-by-player result
        # and improve it with random swaps/moves within the budget.
        seed = greedy_assignment(ctx, state, participants, pool, allowed_slots)
        if seed is None:
            seed = matching_seed(ctx, state, participants, pool, allowed_slots)
        if seed is not None:
            best_cost = evaluate_assignment(ctx, state, participants, seed)
        if best_cost is not None:
            current = seed
            for _ in range(budget):
                trial = list(current)
                spare = [s for s in pool if s not in trial]
                if k >= 2 and (not spare or random.random() < 0.5):
                    i, j = random.sample(range(k), 2)
                    trial[i], trial[j] = trial[j], trial[i]
                elif spare:
                    trial[random.randrange(k)] = random.choice(spare)
                else:
                    continue
                if _violates_mask(participants, trial, allowed_slots):
                    continue
                cost = evaluate_assignment(ctx, state, participants, trial)
                if cost is not None and cost < best_cost:
                    best_cost, current = cost, trial
            candidates = [current]

    if not candidates:
        return None
    random.shuffle(candidates)
    return candidates[0]


def place_batch(
    ctx: BracketContext,
    state: BracketState,
    participants,
    slot_pool_tiers,
    action_name="top_seed_assign",
    allowed_slots=None,
):
    """Jointly place *participants* and commit them to *state*.

    *slot_pool_tiers* is an ordered list of candidate slot lists; the first tier
    that admits a feasible assignment for the whole batch is used (later tiers
    are fallbacks).  *allowed_slots* optionally restricts individual
    participants (used by Phase 1b, where each player is bound to the quarters
    its group's anchor allows).

    Returns the list of chosen slots (aligned with *participants*), or None
    when no tier admitted a feasible assignment.
    """
    if not participants:
        return []

    best_slots = None
    for tier in slot_pool_tiers:
        pool = []
        for slot in tier:
            if slot not in pool and state.slot_state[slot] is None:
                pool.append(slot)
        if len(pool) < len(participants):
            continue
        best_slots = _best_assignment(ctx, state, participants, pool, allowed_slots)
        if best_slots is not None:
            break

    if best_slots is None:
        return None

    # Replay the winning assignment on the real state, snapshotting per
    # participant so the interactive viewer keeps its step granularity.
    for participant, slot in zip(participants, best_slots):
        state.place(participant, slot, id(participant) in ctx.bye_recipient_ids)
        state.record(action_name, [slot], [participant])
    return best_slots
