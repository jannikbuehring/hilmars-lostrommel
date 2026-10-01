"""Phase 1b: place the byes that go to participants below the group winners.

When byes outnumber the top-group-pos players, the remaining byes (pos-5,
pos-6, ... in seeding order) are distributed with the same balanced placer,
each restricted to the quarter/half required by where its group's top landed.
This spreads the byes evenly so the leftover non-bye players still fit; only
afterwards does Phase 2 run.  In the common case (byes <= number of tops)
there are no non-top byes and this is a no-op.
"""

from draw.bracket.context import BracketContext
from draw.bracket.placement import max_matching, place_batch
from draw.bracket.rules import allowed_for, required_half
from draw.bracket.state import BracketState, opponent_slot


def distribute_byes(ctx: BracketContext, state: BracketState):
    slot_state = state.slot_state
    slot_quarter = ctx.geo.slot_quarter
    any_slot_tier = list(range(1, ctx.bracket_size + 1))
    # Records the opposite-half quarter a group already used, so its 2nd/3rd land
    # in different quarters (the sibling_quarter of allowed_quarters; Phase 2 seeds
    # its own map from the slots this one led to).
    group_opposite_quarter_used: dict = {}

    def required_quarters_for(participant):
        """Allowed quarters for a non-top bye, per the half/quarter separation rules."""
        return allowed_for(
            ctx,
            state.group_top_quarter,
            participant,
            group_opposite_quarter_used.get(getattr(participant, "group_no", None)),
        )

    # Continue the seeded-slot hierarchy where Phase 1 stopped.  Phase 1 breaks out
    # of its batch loop as soon as the group winners run out, leaving the rest of
    # the partially-filled batch — and every later batch — untouched; any hierarchy
    # slot still free is therefore the strongest slot left, and the next-highest
    # bye recipients should fill it before dropping to a weaker one.  Each batch is
    # assigned jointly, exactly like Phase 1, with every participant masked to the
    # quarters its group's anchor allows, so the separation rules still bind.
    remaining_byes = list(ctx.non_top_bye_recipients)
    for hierarchy_group in ctx.hierarchy_groups:
        while remaining_byes:
            # Every phase-1b participant is a bye recipient and occupies the whole
            # match, so a slot whose partner is already taken cannot host one.
            free_in_group = [
                s for s in hierarchy_group if slot_state[s] is None and slot_state[opponent_slot(s)] is None
            ]
            if not free_in_group:
                break

            # A group's 2nd constrains its 3rd via group_opposite_quarter_used, which
            # only holds while they are assigned in separate batches — so never take
            # two participants of the same group into one chunk.
            chunk = []
            chunk_groups = set()
            allowed_slots = {}
            for participant in remaining_byes:
                if len(chunk) >= len(free_in_group):
                    break
                group_no = getattr(participant, "group_no", None)
                if group_no is not None and group_no in chunk_groups:
                    continue
                allowed_qs = required_quarters_for(participant)
                allowed = {s for s in free_in_group if slot_quarter(s) in allowed_qs}
                if not allowed:
                    continue
                # Simply taking the top N by seeding can be jointly unassignable even
                # when every member has a candidate slot on its own (e.g. four players
                # needing half 0 while only three half-0 slots are free).  Admit a
                # player only while a perfect matching survives; a rejected one stays
                # in remaining_byes for the next round of this level, or the next
                # level.  Matchable subsets form a transversal matroid, so this
                # seeding-ordered greedy yields the highest-seeded maximum-size chunk.
                trial_allowed = dict(allowed_slots)
                trial_allowed[id(participant)] = allowed
                trial_ids = [id(p) for p in chunk] + [id(participant)]
                if len(max_matching(trial_ids, trial_allowed)) < len(trial_ids):
                    continue
                chunk.append(participant)
                chunk_groups.add(group_no)
                allowed_slots[id(participant)] = allowed
            if not chunk:
                break

            chosen_slots = None
            while chunk:
                chosen_slots = place_batch(
                    ctx, state, chunk, [free_in_group], action_name="bye_assign", allowed_slots=allowed_slots
                )
                if chosen_slots is not None:
                    break
                # Never abandon a whole hierarchy level over one un-placeable player:
                # drop the lowest-seeded chunk member and retry, so the strong slots
                # still go to as many high seeds as will fit.
                allowed_slots.pop(id(chunk.pop()), None)
            if not chunk:
                break

            for participant, slot in zip(chunk, chosen_slots):
                group_no = getattr(participant, "group_no", None)
                if group_no is not None:
                    group_opposite_quarter_used.setdefault(group_no, slot_quarter(slot))
                remaining_byes.remove(participant)

    # Whoever the hierarchy could not host: required quarter, then required half,
    # then any free slot.
    for participant in remaining_byes:
        allowed_qs = required_quarters_for(participant)
        quarter_tier = [s for s in any_slot_tier if slot_quarter(s) in allowed_qs]
        participant_half = required_half(ctx, participant, state.group_top_half)
        half_tier = (
            [s for s in any_slot_tier if ctx.geo.slot_half(s) == participant_half]
            if participant_half is not None
            else any_slot_tier
        )
        chosen = place_batch(
            ctx, state, [participant], [quarter_tier, half_tier, any_slot_tier], action_name="bye_assign"
        )
        if chosen is None:
            state.fail(
                "bye_slot_failure",
                {
                    "message": "Unable to place bye recipients in their required quarters.",
                    "type": "bye_slot_failure",
                    "phase": "bye_distribution",
                    "top_group_pos": ctx.top_group_pos,
                    "locked_slots": sorted(state.locked_slots),
                    "group_top_quarter": dict(state.group_top_quarter),
                },
                [participant],
            )
        group_no = getattr(participant, "group_no", None)
        if group_no is not None:
            group_opposite_quarter_used.setdefault(group_no, slot_quarter(chosen[0]))
