"""Phase 1c: repair pass over everything Phase 1/1b locked in.

Both distribution objectives are properties of the FINISHED layout, but
Phase 1/1b can only ever optimise one batch at a time: an uneven tier spread
emerges ACROSS hierarchy levels (the runners-up of a 64-slot draw are split
between two levels, placed by different place_batch calls), and a chunk of
~16 participants into 16 slots is far past joint_batch_max_evaluations, so it
falls to a hill-climb seeded by a cost-greedy pass that commits each player
before its round-two opposite even exists.  This pass is the only one with a
global view of the result.

It swaps two NON-TOP bye recipients, which is FEASIBILITY-NEUTRAL by
construction and so cannot undo anything Phase 1/1b established: both slots
are (player, BYE) matches before and after, so every per-quarter and per-half
bye count is unchanged, and a top-placed participant is not a candidate at all
-- neither as the mover nor as its partner -- so the group anchors, and with
them the tops-per-quarter and net-half-load balances and Phase 2's dependence
on group_top_quarter, are invariant here by construction rather than by a
boundary check.  Phase 1 decides where the group winners sit; they stay put.
That is the same capacity-neutrality argument that makes
rebalance_bottom_tier_quarters safe to run after capacity is settled.

Deterministic best-improvement, consuming NO randomness: drawing from the
shared RNG stream here would shift every downstream random outcome, so any
change in a drawn bracket stays attributable to the rules rather than to the
pass having run.  Also like rebalance_bottom_tier_quarters.
"""

from checks.bracket_checker import check_half_group_separation, check_quarter_group_separation
from draw.bracket.context import BracketContext
from draw.bracket.costs import assignment_quality_cost
from draw.bracket.rules import allowed_for
from draw.bracket.state import BracketState, bracket_score, opponent_slot


def repair_bye_placements(ctx: BracketContext, state: BracketState):
    """Swap or move placed non-top bye recipients while it strictly improves the layout."""
    slot_state = state.slot_state
    locked_slots = state.locked_slots
    top_group_pos = ctx.top_group_pos
    number_of_matches = ctx.number_of_matches
    num_quarters = ctx.geo.num_quarters
    slot_quarter = ctx.geo.slot_quarter

    # Top-placed participants are filtered out HERE rather than skipped per pair
    # inside the sweep: a swap moves both of its participants, so a group winner
    # must not be a partner either, and dropping them up front shrinks the
    # quadratic sweep instead of paying for them on every iteration.
    def bye_recipient_slots():
        return sorted(
            s
            for s in locked_slots
            if slot_state[s] not in (None, "BYE")
            and slot_state[s].group_pos != top_group_pos
            and slot_state[opponent_slot(s)] == "BYE"
        )

    candidates = bye_recipient_slots()
    if not candidates:
        return

    def state_cost(trial_matches):
        return bracket_score(ctx, trial_matches) + assignment_quality_cost(ctx, trial_matches, state.group_top_quarter)

    def separation_counts(trial_matches):
        return (
            len(check_half_group_separation(trial_matches, number_of_matches, bounds=ctx.bracket_bounds)),
            len(check_quarter_group_separation(trial_matches, number_of_matches, bounds=ctx.bracket_bounds)),
        )

    # The residual 2nd/3rd (delta 1/2) that Phase 2 still has to place, by group,
    # and the residual 4ths (delta 3), each tied to its winner's own half.
    residual_by_group = {}
    residual_fourths = []
    for p in ctx.participants:
        if id(p) in ctx.bye_recipient_ids or p.group_no not in state.group_top_quarter:
            continue
        if p.group_pos - top_group_pos in (1, 2):
            residual_by_group.setdefault(p.group_no, []).append(p)
        elif p.group_pos - top_group_pos == 3:
            residual_fourths.append(p)

    def residual_overflow():
        """Residual players the free slots of their forced quarter cannot hold.

        A group's 2nd and 3rd go to the opposite half, in different quarters.
        So once one of them sits there with a bye, the other is forced into the
        sibling quarter -- and a 2nd with a bye placed without regard for that
        can leave the sibling quarter full (S M1 consolation: free slots 4/6,
        five 6th places forced into the "4" quarter).  A 4th is forced into the
        other quarter of its winner's half.  The moves below change how many
        free slots a quarter has, so they need the 4ths counted too.
        """
        free_in_q = {q: 0 for q in range(num_quarters)}
        placed_quarters = {}
        for s in range(1, ctx.bracket_size + 1):
            value = slot_state[s]
            if value is None:
                free_in_q[slot_quarter(s)] += 1
            elif value != "BYE" and value.group_pos - top_group_pos in (1, 2):
                placed_quarters.setdefault(value.group_no, set()).add(slot_quarter(s))
        forced = {q: 0 for q in range(num_quarters)}
        for group_no, members in residual_by_group.items():
            # A residual 2nd/3rd has at most one placed sibling; the members share
            # the same allowed quarters, so the first one speaks for the group.
            placed = placed_quarters.get(group_no, set())
            open_quarters = allowed_for(ctx, state.group_top_quarter, members[0], next(iter(placed), None))
            # Only a group with no choice left forces anything.
            if len(open_quarters) == len(members):
                for q in open_quarters:
                    forced[q] += 1
        for p in residual_fourths:
            allowed = allowed_for(ctx, state.group_top_quarter, p)
            if len(allowed) == 1:
                forced[allowed[0]] += 1
        return sum(max(0, forced[q] - free_in_q[q]) for q in range(num_quarters))

    current_matches = state.matches()
    # Lexicographic: residual capacity first -- an overflow sends the whole
    # draw down the quarter_capacity_degrade path -- then the layout cost.
    best_key = (residual_overflow(), state_cost(current_matches))
    # Separations are a HARD gate, not part of the objective: at 2500 a tier
    # unit outweighs both split weights, so a scored gate would let the pass
    # buy a tier repair with a separation -- "darf eigentlich nicht verletzt
    # werden, country und base lieber violaten".  Phase 1/1b can leave one
    # behind, so the bar is "no worse", not "none".
    best_separations = separation_counts(current_matches)

    # Two kinds of step, both feasibility-guarded by residual_overflow and the
    # separation gate:
    #
    # * swap two non-top bye recipients -- every per-quarter bye count stays;
    # * move one non-top bye recipient, with its BYE, into a free match of the
    #   other quarter of its own half -- only while that lowers the overflow.
    #
    # The swap alone cannot repair a bracket without a spare slot.  S M3 main
    # (50 groups x 3, 256 slots, 106 byes) fills every slot, so each quarter
    # must hold precisely the 3rd places its sibling quarter's runners-up force
    # into it; Phase 1/1b balance tops+byes with one unit of slack and could
    # leave free slots 8/10 against 9/9 forced 3rd places.  Swapping two
    # runners-up of that half moves one forced 3rd each way (net zero), so the
    # draw went down the degrade path.  Moving ONE of them closes the gap: its
    # old quarter gains two free slots and one forced 3rd.  A move never leaves
    # its half, so the half separation and the bye-half balance stay put.
    #
    # Best-improvement rather than first-improvement: a sweep costs the same
    # either way, and taking the first improving step settles for whatever
    # trade it stumbles on -- on a 33-player draw that meant paying a real
    # round-two violation for a tier repair that a different pair delivered
    # for free.  Each accepted step strictly lowers the key, so this
    # terminates; the cap only bounds the work on a pathological plateau.
    for _ in range(2 * len(candidates) + number_of_matches):
        candidates = bye_recipient_slots()
        best_step = None
        for index, slot_a in enumerate(candidates):
            for slot_b in candidates[index + 1 :]:
                participant_a, participant_b = slot_state[slot_a], slot_state[slot_b]
                slot_state[slot_a], slot_state[slot_b] = participant_b, participant_a
                trial_matches = state.matches()
                trial_key = (residual_overflow(), state_cost(trial_matches))
                # Separations are the more expensive check, so only pay for it
                # once a step is actually in the running.
                if trial_key < best_key and (best_step is None or trial_key < best_step[0]):
                    trial_separations = separation_counts(trial_matches)
                    if all(t <= b for t, b in zip(trial_separations, best_separations)):
                        best_step = (trial_key, trial_separations, "bye_swap", slot_a, slot_b)
                slot_state[slot_a], slot_state[slot_b] = participant_a, participant_b

        free_matches = (
            [m for m in range(1, number_of_matches + 1) if slot_state[2 * m - 1] is None and slot_state[2 * m] is None]
            if best_key[0] > 0
            else []
        )
        for slot_from in candidates:
            bye_from = opponent_slot(slot_from)
            quarter_from = slot_quarter(slot_from)
            for match_to in free_matches:
                # Keep the player on the same side of its match.
                slot_to = 2 * match_to - 1 if slot_from % 2 == 1 else 2 * match_to
                quarter_to = slot_quarter(slot_to)
                if quarter_to == quarter_from or ctx.geo.quarter_half(quarter_to) != ctx.geo.quarter_half(quarter_from):
                    continue
                bye_to = opponent_slot(slot_to)
                participant = slot_state[slot_from]
                slot_state[slot_from], slot_state[bye_from] = None, None
                slot_state[slot_to], slot_state[bye_to] = participant, "BYE"
                # A move shifts the per-quarter bye counts Phase 1/1b balanced,
                # so it is only worth that when it removes an overflow.
                trial_overflow = residual_overflow()
                if trial_overflow < best_key[0]:
                    trial_matches = state.matches()
                    trial_key = (trial_overflow, state_cost(trial_matches))
                    if best_step is None or trial_key < best_step[0]:
                        trial_separations = separation_counts(trial_matches)
                        if all(t <= b for t, b in zip(trial_separations, best_separations)):
                            best_step = (trial_key, trial_separations, "bye_move", slot_from, slot_to)
                slot_state[slot_to], slot_state[bye_to] = None, None
                slot_state[slot_from], slot_state[bye_from] = participant, "BYE"

        if best_step is None:
            break

        best_key, best_separations, action, slot_a, slot_b = best_step
        if action == "bye_swap":
            participant_a, participant_b = slot_state[slot_a], slot_state[slot_b]
            slot_state[slot_a], slot_state[slot_b] = participant_b, participant_a
            moved = [participant_a, participant_b]
        else:
            bye_a, bye_b = opponent_slot(slot_a), opponent_slot(slot_b)
            moved = [slot_state[slot_a]]
            slot_state[slot_a], slot_state[bye_a] = None, None
            slot_state[slot_b], slot_state[bye_b] = moved[0], "BYE"
            locked_slots.difference_update((slot_a, bye_a))
            locked_slots.update((slot_b, bye_b))
        # No group_top_quarter/_half resync: no top-placed participant moves,
        # so the anchors cannot have moved.
        state.record(action, [slot_a, slot_b], moved)
