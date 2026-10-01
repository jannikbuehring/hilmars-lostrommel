"""Phases 4 and 5: fill the free slots quarter by quarter and polish each quarter.

Phase 4 builds one pool per quarter from the Phase-2 assignment; Phase 5 is a
four-phase Monte Carlo, one phase per quarter: it fixes the other three
quarters and shuffles the active one.
"""

import copy
import random

from checks.bracket_checker import score_bracket_tiers
from draw.bracket.context import BracketContext
from draw.bracket.state import BracketState, bracket_score, slots_to_matches


def fill_quarter_pools(ctx: BracketContext, state: BracketState, residual_players, required_quarter):
    """Place *residual_players* into the free slots of their required quarters.

    Returns (matches, snapshots) of the best bracket found.
    """
    number_of_matches = ctx.number_of_matches
    max_attempts = ctx.max_attempts

    free_slots = [s for s in range(1, ctx.bracket_size + 1) if state.slot_state[s] is None]
    free_slots_by_quarter = {q: [s for s in free_slots if ctx.geo.slot_quarter(s) == q] for q in range(4)}

    def build_matches_from_quarter_pools(pools):
        """Assign each quarter pool (in slot order) and return a matches dict."""
        trial_state = dict(state.slot_state)
        for q in range(4):
            for slot, participant in zip(free_slots_by_quarter[q], pools[q]):
                trial_state[slot] = participant
        return slots_to_matches(ctx, trial_state)

    def tiers(matches):
        # Compared as score_bracket_tiers tuples, not the summed score: a weighted
        # sum would trade one winner-vs-runner-up for a few same-country pairings.
        return score_bracket_tiers(
            matches, number_of_matches, weights=ctx.bracket_weights, top_count=ctx.bracket_top_count
        )

    final_pool_quarter: dict = {q: [] for q in range(4)}
    for p in residual_players:
        rq = required_quarter.get(id(p), 0)
        final_pool_quarter[rq].append(p)

    for q in range(4):
        if len(final_pool_quarter[q]) != len(free_slots_by_quarter[q]):
            state.fail(
                "permutation_failure",
                {
                    "message": (
                        f"Quarter {q} pool size {len(final_pool_quarter[q])} "
                        f"does not match slot capacity {len(free_slots_by_quarter[q])}."
                    ),
                    "type": "quarter_pool_size_mismatch",
                    "group_top_quarter": dict(state.group_top_quarter),
                    "remaining_start_numbers": [p.start_number_a for p in residual_players],
                },
                residual_players,
            )

    if not residual_players:
        first_full_matches = slots_to_matches(ctx, dict(state.slot_state))
        state.record("final", None, None, first_full_matches)
        return first_full_matches, state.snapshots

    # Initial shuffle: each quarter pool shuffled independently.
    current_pools = {q: list(final_pool_quarter[q]) for q in range(4)}
    for q in range(4):
        random.shuffle(current_pools[q])

    first_full_matches = build_matches_from_quarter_pools(current_pools)
    first_full_score = bracket_score(ctx, first_full_matches)
    state.record("initial_fill", None, None, first_full_matches, violation_score=first_full_score)

    best_score = first_full_score
    best_key = tiers(first_full_matches)
    best_matches = copy.deepcopy(first_full_matches)
    best_pools = {q: list(current_pools[q]) for q in range(4)}

    snapshot_interval = max(1, max_attempts // 10)

    for active_q in range(4):
        if not final_pool_quarter[active_q]:
            continue  # nothing to optimise in this quarter

        state.record(f"quarter{active_q}_mc_start", None, None, best_matches, violation_score=best_score)

        for attempt in range(max_attempts):
            if attempt % snapshot_interval == 0:
                ctx.report(f"fine-tuning quarter {active_q + 1} of 4 (step {attempt:,} of {max_attempts:,})...")
            trial_pool = list(final_pool_quarter[active_q])
            random.shuffle(trial_pool)
            trial_pools = dict(best_pools)
            trial_pools[active_q] = trial_pool
            m_try = build_matches_from_quarter_pools(trial_pools)
            trial_key = tiers(m_try)
            score = sum(trial_key)

            if trial_key < best_key:
                best_key = trial_key
                best_score = score
                best_pools = {q: list(trial_pools[q]) for q in range(4)}
                best_matches = copy.deepcopy(m_try)
                state.record("improvement", [attempt], None, m_try, violation_score=score)
                if best_score == 0:
                    break
            elif attempt % snapshot_interval == 0:
                state.record("progress", [attempt], None, m_try, violation_score=score)

        if best_score == 0:
            break

    state.record("final", None, None, best_matches)
    return best_matches, state.snapshots
