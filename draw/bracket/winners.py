"""Phase 1: place the group winners in strict seeding batches.

Batch 0 → hierarchy_groups[0] = [slot 1]        — completely deterministic
Batch 1 → hierarchy_groups[1] = [last slot]     — completely deterministic
Batch 2 → hierarchy_groups[2] (2 slots)         — joint best-score + shuffle
Batch k → hierarchy_groups[k] (2^(k-1) slots)   — joint best-score + shuffle
"""

from draw.bracket.context import BracketContext
from draw.bracket.placement import place_batch
from draw.bracket.state import BracketState, opponent_slot


def place_group_winners(ctx: BracketContext, state: BracketState):
    top_sorted = ctx.top_sorted
    n_top = len(top_sorted)
    any_slot_tier = list(range(1, ctx.bracket_size + 1))

    batch_start = 0
    for batch_idx, hierarchy_group in enumerate(ctx.hierarchy_groups):
        if batch_start >= n_top:
            break
        batch_end = batch_start + len(hierarchy_group)
        batch_players = top_sorted[batch_start : min(batch_end, n_top)]

        if len(hierarchy_group) == 1 and len(batch_players) == 1:
            # Completely deterministic: single slot, single player — no scoring.
            participant = batch_players[0]
            slot = hierarchy_group[0]
            needs_bye = id(participant) in ctx.bye_recipient_ids

            if state.slot_state[slot] is not None or (needs_bye and state.slot_state[opponent_slot(slot)] is not None):
                state.fail(
                    "seed_slot_failure",
                    {
                        "message": f"Required seeded slot {slot} is already occupied.",
                        "type": "seed_slot_failure",
                        "phase": "deterministic_batch",
                        "batch_idx": batch_idx,
                        "slot": slot,
                        "locked_slots": sorted(state.locked_slots),
                    },
                    [participant],
                )

            state.place(participant, slot, needs_bye)
            state.record("top_seed_assign", [slot], [participant])
        # Joint balanced placement of the WHOLE batch within its hierarchy
        # group, falling back to any remaining free slot.
        elif place_batch(ctx, state, batch_players, [hierarchy_group, any_slot_tier]) is None:
            state.fail(
                "seed_slot_failure",
                {
                    "message": (
                        f"No slot assignment available for top-seeded batch {batch_idx} "
                        f"(participants {[p.start_number_a for p in batch_players]})."
                    ),
                    "type": "seed_slot_failure",
                    "phase": "joint_batch",
                    "batch_idx": batch_idx,
                    "locked_slots": sorted(state.locked_slots),
                },
                batch_players,
            )

        batch_start = batch_end
