"""Draw a single-elimination bracket with group separation and country conflict avoidance.

One attempt runs the phases in order, each in its own module:

  Phase 1   winners.place_group_winners    group winners down the seeded-slot hierarchy
  Phase 1b  byes.distribute_byes           byes for participants below the winners
  Phase 1c  repair.repair_bye_placements   swap/move those byes while it improves the layout
  Phase 2   quarters.assign_quarter_buckets (+ rebalance_bottom_tier_quarters)
  Phase 4/5 fill.fill_quarter_pools        fill each quarter and polish it by Monte Carlo
  or        degrade.fill_residual_soft     when a quarter cannot hold its players

All randomness comes from the shared global `random` module (seeded once from
settings.general.random_seed by core.config.initialize_config), the same RNG
stream draw/group_drawer.py uses, so a single config seed deterministically
drives the whole pipeline instead of each bracket draw restarting its own
Random() from the same seed.
"""

import logging
import random
from collections.abc import Callable

from draw.bracket.byes import distribute_byes
from draw.bracket.context import build_context
from draw.bracket.degrade import fill_residual_soft
from draw.bracket.fill import fill_quarter_pools
from draw.bracket.quality import result_rank, took_degrade_path
from draw.bracket.quarters import assign_quarter_buckets, over_capacity_quarters, rebalance_bottom_tier_quarters
from draw.bracket.repair import repair_bye_placements
from draw.bracket.state import BracketState
from draw.bracket.winners import place_group_winners
from models.draw_data import DrawDataRow
from models.snapshot import Snapshot


def draw_bracket(
    class_subset: list[DrawDataRow], phase1_only: bool = False, progress: Callable[[str], None] | None = None
) -> tuple[dict[int, list], list[Snapshot]]:
    """
    Build a single-elimination bracket from seeded participants.
    class_subset: players advancing from groups
    phase1_only: stop after Phase 1 and return the partial bracket with only the
    top-group-pos players placed (used by tests to isolate Phase 1)
    progress: optional callable taking one plain-language status line, called at
    each phase and every tenth of the long search loops

    Phase 1 balances the byes and tiers over the halves (review finding N2).  On
    the tightest shapes that can pick a winner layout Phase 2 cannot fill, where
    the old objective found one it could.  So a draw that ends on the degrade
    path is drawn once more without the half balance, from the same RNG state
    -- i.e. exactly the draw the pre-N2 objective made -- and the better result
    by result_rank is kept: a separation is never paid for an even split.
    """
    rng_state = random.getstate()
    matches, snapshots = draw_bracket_attempt(
        class_subset, half_balance=True, phase1_only=phase1_only, progress=progress
    )
    if not took_degrade_path(snapshots):
        return matches, snapshots
    balanced_rng_state = random.getstate()
    random.setstate(rng_state)
    if progress is not None:
        progress("first layout was not clean - trying a second strategy to compare...")
    try:
        fallback_matches, fallback_snapshots = draw_bracket_attempt(
            class_subset, half_balance=False, phase1_only=phase1_only, progress=progress
        )
    except Exception as exc:  # the balanced result stands; see N1 for the known crash
        logging.warning("Bracket fallback draw without half balance failed: %s", exc)
        random.setstate(balanced_rng_state)
        return matches, snapshots
    if result_rank(fallback_snapshots) < result_rank(snapshots):
        return fallback_matches, fallback_snapshots
    random.setstate(balanced_rng_state)
    return matches, snapshots


def draw_bracket_attempt(class_subset: list[DrawDataRow], half_balance: bool, phase1_only: bool = False, progress=None):
    """One full draw.  *half_balance* False drops the bye/tier half balance
    from Phase 1 (projected_half_balance_units, the lookahead), which leaves
    the pre-N2 objective: only the byes already on the board are balanced.
    *progress* is draw_bracket's status callback.
    """
    ctx = build_context(class_subset, half_balance, progress)
    state = BracketState.empty(ctx)
    state.record("seed_start", None, None)

    ctx.report("placing the group winners on the seeded positions...")
    place_group_winners(ctx, state)
    post_top_matches = state.matches()
    state.record("top_seed_complete", sorted(state.locked_slots), list(ctx.top_sorted), post_top_matches)
    if phase1_only:
        # Return the partial bracket (only top-group-pos players placed).
        return post_top_matches, state.snapshots

    if ctx.byes:
        ctx.report("distributing byes...")
    distribute_byes(ctx, state)

    ctx.report("fine-tuning the positions of group winners and byes...")
    if ctx.non_top_bye_recipients:
        # Gated on Phase 1b having run.  Without it every bye recipient is a group
        # winner, so the repair's candidate set would come out empty anyway; the
        # gate just skips the work and keeps the low-bye draws untouched.
        repair_bye_placements(ctx, state)
        state.record(
            "seeded_byes",
            sorted(state.locked_slots),
            list(ctx.top_sorted) + list(ctx.non_top_bye_recipients),
        )

    ctx.report("placing the remaining players into the quarters...")
    residual = ctx.residual_players
    required_quarter = assign_quarter_buckets(ctx, state, residual)
    # Capacity-neutral repair pass so each quarter can actually serve its non-bye
    # group winners a bottom-tier opponent.  Runs before the capacity check below,
    # which by construction still sees the same per-quarter counts.
    rebalance_bottom_tier_quarters(ctx, state, required_quarter, residual)

    if over_capacity_quarters(ctx, state, residual, required_quarter):
        return fill_residual_soft(ctx, state, residual)
    return fill_quarter_pools(ctx, state, residual, required_quarter)
