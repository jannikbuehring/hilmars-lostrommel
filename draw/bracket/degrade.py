"""The degrade path: a best-effort fill when Phase 2's quarter buckets overflow.

Structurally tight, near-full brackets can leave the residual non-bye players
impossible to pack into their required quarters (e.g. an odd number of groups
each contributing 3 positions into a bracket that is almost entirely byes).
Rather than abort the whole bracket, the draw degrades gracefully: every free
slot is filled by a search that treats the separations as the top tier of a
lexicographic objective instead of as a hard constraint.
"""

import random

from checks.bracket_checker import check_bye_seeding_order, score_bracket_tiers
from draw.bracket.context import BracketContext
from draw.bracket.costs import assignment_quality_cost
from draw.bracket.state import BracketState, opponent_slot, slots_to_matches


def fill_residual_soft(ctx: BracketContext, state: BracketState, residual_players):
    """Best-effort fill of all free slots when hard quarter buckets overflow.

    The degrade is usually caused upstream: Phase 1/1b left a quarter or half
    without room for a player the separation rules send there (e.g. a quarter
    filled with "player vs BYE" matches, or an 8/6 bye split across the
    halves).  So the fill cannot just shuffle the leftover players -- random
    reshuffles of 30+ free slots never converge, and no placement of the
    leftovers alone can repair a full quarter.

    Instead: start from the best of a few random fills, then hill-climb
    (sideways moves accepted, best state kept) with three move types that
    never touch a group winner, which stays in its seeded slot:

    * swap two first-round matches without a winner -- moves whole
      "player vs BYE" pairs between quarters and halves;
    * move a BYE to another player-vs-player match, only when the new
      recipient has the same group position as the old one, so each tier
      keeps its number of byes;
    * swap two non-winner players, same group position only when exactly
      one of them faces a BYE (same reason).

    The objective is compared as a tuple, most important first: the hard
    tier (separations, first-vs-first); byes in seeding order within a tier
    ("Hoechstes Seeding bekommt zuerst Freilose" -- the two bye-moving moves
    may break it, but only to remove a hard violation); Phase 1/1b/1c's own
    assignment_quality_cost (byes even over the halves, tiers even over the
    quarters of a half, round-two quality), because the moves shift exactly
    what those phases balanced; then score_bracket_tiers' matchup and
    distribution tiers.

    The tier-half term is left out of that objective.  The winners never move
    here, so the tier split over the halves only changes by breaking a
    separation, and as a tiebreaker it steered the sideways moves away from
    the repairs: in a before/after sweep, three 4-tier short-group draws
    ended with 6-14 more half-separation violations with it in.

    Returns (matches, snapshots) of the best state found.
    """
    bracket_size = ctx.bracket_size
    number_of_matches = ctx.number_of_matches
    top_group_pos = ctx.top_group_pos
    free_slots_all = [s for s in range(1, bracket_size + 1) if state.slot_state[s] is None]

    def _fill_order(order):
        trial_state = dict(state.slot_state)
        for slot, participant in zip(free_slots_all, order):
            trial_state[slot] = participant
        return trial_state

    def _is_top(value):
        return value not in (None, "BYE") and value.group_pos == top_group_pos

    def _key(trial_state):
        trial_matches = slots_to_matches(ctx, trial_state)
        hard, matchup, distribution = score_bracket_tiers(
            trial_matches,
            number_of_matches,
            weights=ctx.bracket_weights,
            bounds=ctx.bracket_bounds,
            top_count=ctx.bracket_top_count,
        )
        return (
            hard,
            # "Hoechstes Seeding bekommt zuerst Freilose"
            len(check_bye_seeding_order(trial_matches, top_group_pos)),
            assignment_quality_cost(ctx, trial_matches, state.group_top_quarter, tier_halves=False),
            matchup,
            distribution,
        )

    def _player_slots():
        return [s for s in range(1, bracket_size + 1) if fill[s] != "BYE" and not _is_top(fill[s])]

    state.record("quarter_capacity_degrade", sorted(state.locked_slots), list(residual_players))

    best_order = list(residual_players)
    random.shuffle(best_order)
    best_key = _key(_fill_order(best_order))
    for _ in range(min(200, ctx.max_attempts)):
        trial_order = list(residual_players)
        random.shuffle(trial_order)
        trial_key = _key(_fill_order(trial_order))
        if trial_key < best_key:
            best_key, best_order = trial_key, trial_order

    fill = _fill_order(best_order)
    best_fill = dict(fill)
    current_key = best_key
    winner_free_matches = [
        m for m in range(1, number_of_matches + 1) if not _is_top(fill[2 * m - 1]) and not _is_top(fill[2 * m])
    ]
    player_slots = _player_slots()
    # 4x the phase-5 budget: a move costs one scoring pass, which is small next
    # to Phase 1 on the brackets that degrade, and the S M3 draws (150 players,
    # 256 slots) only reach zero hard violations with it.
    search_iterations = 4 * ctx.max_attempts
    snapshot_interval = max(1, search_iterations // 10)
    ctx.report("no clean layout possible - searching the best possible layout...")

    def _random_move():
        """Apply one random move to `fill`; return (changed slots, previous
        values) for the undo, or None when the drawn move is not allowed."""
        move = random.random()
        if move < 0.25:
            # Bye relocation.  Recipients are non-winners (the winners' byes
            # stay with their seeded slot).
            bye_slots = [
                s for s in range(1, bracket_size + 1) if fill[s] == "BYE" and not _is_top(fill[opponent_slot(s)])
            ]
            if not bye_slots:
                return None
            bye_slot = random.choice(bye_slots)
            recipient = fill[opponent_slot(bye_slot)]
            targets = [
                s
                for s in player_slots
                if s != opponent_slot(bye_slot)
                and fill[opponent_slot(s)] not in (None, "BYE")
                and fill[opponent_slot(s)].group_pos == recipient.group_pos
            ]
            if not targets:
                return None
            target = random.choice(targets)
            changed = [bye_slot, target]
            previous = [fill[s] for s in changed]
            # The player at the target takes the BYE's place opposite the old
            # recipient, and the target slot becomes the BYE.
            fill[bye_slot], fill[target] = previous[1], "BYE"
        elif move < 0.6 and len(winner_free_matches) >= 2:
            match_a, match_b = random.sample(winner_free_matches, 2)
            changed = [2 * match_a - 1, 2 * match_a, 2 * match_b - 1, 2 * match_b]
            previous = [fill[s] for s in changed]
            for s, value in zip(changed, previous[2:] + previous[:2]):
                fill[s] = value
        else:
            slot_a, slot_b = random.sample(player_slots, 2)
            bye_a = fill[opponent_slot(slot_a)] == "BYE"
            bye_b = fill[opponent_slot(slot_b)] == "BYE"
            if bye_a != bye_b and fill[slot_a].group_pos != fill[slot_b].group_pos:
                return None
            changed = [slot_a, slot_b]
            previous = [fill[s] for s in changed]
            fill[slot_a], fill[slot_b] = previous[1], previous[0]
        return changed, previous

    # A hill climb on a lexicographic key plateaus: once the hard tier is
    # stuck, every move that would pass through a worse lower tier is
    # rejected.  After `stall_limit` attempts without a new best, restart
    # from the best state with a few unconditional moves -- but only while
    # hard violations remain, since that is what the fill is for.
    stall_limit = max(100, search_iterations // 80)
    kick_moves = 4
    since_best = 0

    for attempt in range(search_iterations):
        if best_key == (0, 0, 0, 0, 0):
            break
        if attempt and attempt % snapshot_interval == 0:
            ctx.report(
                f"no clean layout possible - searching the best possible layout"
                f" (step {attempt:,} of {search_iterations:,})..."
            )
        if since_best >= stall_limit and best_key[0] > 0:
            since_best = 0
            fill = dict(best_fill)
            player_slots = _player_slots()
            for _ in range(kick_moves):
                if _random_move() is not None:
                    player_slots = _player_slots()
            current_key = _key(fill)

        since_best += 1
        applied = _random_move()
        if applied is None:
            continue
        changed, previous = applied

        trial_key = _key(fill)
        m_try = slots_to_matches(ctx, fill)
        if trial_key <= current_key:
            current_key = trial_key
            player_slots = _player_slots()
            if trial_key < best_key:
                since_best = 0
                best_key, best_fill = trial_key, dict(fill)
                state.record("improvement", [attempt], None, m_try)
                continue
        else:
            for s, value in zip(changed, previous):
                fill[s] = value
        if attempt % snapshot_interval == 0:
            state.record("progress", [attempt], None, m_try)

    best_matches = slots_to_matches(ctx, best_fill)
    state.record("final", None, None, best_matches)
    return best_matches, state.snapshots
