"""The Phase-1 penalty ladder: what a (partial) placement of winners and byes costs.

Ladder, highest first:
  half_load_cost      x 100000  net half load           (feasibility)
  combined_excess     x  10000  quarter tops+byes       (feasibility, placement_penalty)
  bye_half     (5000)           byes even over halves
  tier_half    (5000)           tiers top..top+2 even over halves
  tier_quarter (2500)           tiers even within a half
                                -- all three in assignment_quality_cost
  score_bracket + score_round_two          quality tiebreakers
score_bracket peaks at 250 across a full 33-player/64-slot draw's Phase 1/1b
calls (the few-thousand values only occur on a finished, degraded bracket, which
no phase-1 candidate ever is).  So neither distribution rule can be bought off
with a country/matchup tiebreak, and neither can override a feasibility
constraint or push a placeable layout onto the quarter_capacity_degrade path.
"""

from typing import TYPE_CHECKING

from checks.bracket_checker import check_bye_balance_halves, check_placement_balance_quarters, score_round_two
from draw.bracket.rules import required_half

if TYPE_CHECKING:
    from draw.bracket.context import BracketContext
    from draw.bracket.state import Trial

# Rank 4 of the Phase-1 penalty ladder: a placement tier must not be lopsided
# between the two quarters of ONE half.  Deliberately NOT a config key -- the
# ladder ranks are a strict-ordering proof (feasibility > explicit distribution
# rules > quality tiebreakers), not a matter of taste, and a value above 5000
# would silently outrank the feasibility terms and push placeable layouts onto
# the quarter_capacity_degrade path.  It sits 2x below BYE_HALF_BALANCE_WEIGHT
# (byes are both a rule and a feasibility input, tier spread is quality only) and
# an order of magnitude above the score_bracket values seen during Phase 1/1b
# (measured ceiling 250 on a 33-player/64-slot draw).
TIER_QUARTER_BALANCE_WEIGHT = 2500

# Rank 3 of the same ladder: "Freilose ... gleichmaessig auf die Haelften
# verteilen".  Same value the per-step form used, but charged ONCE on the finished
# assignment (see assignment_quality_cost) instead of accumulated per placement.
#
# The per-step form was unsound as an objective.  It charged a marginal excess on
# the RUNNING PREFIX, and its justification only ever proved the sufficient
# direction -- a final split with a gap >= 2 does charge at least one unit whatever
# the order.  The converse fails: a perfectly legal final split is also charged
# whenever the iteration happens to visit one half twice in a row.  On the S M2
# main draw (33 players / 64 slots) the three leftover group winners enter Phase
# 1's last batch with the byes at 4/4, so every assignment ends 6/5 -- clean -- yet
# the orders h0,h1,* and h1,h0,* scored 0 while h0,h0,h1 scored 5000, on nothing
# but participant order.  That phantom 5000 outranked country_half (20) by 250x and
# was the sole reason two Slovenian group winners shared a half: the country-clean
# assignment needed both of its first two placements in the upper half.
BYE_HALF_BALANCE_WEIGHT = 5000

# Same rank, same rule line: the group winners, runners-up and 3rd places even
# over the halves (check_placement_balance_halves).  Like the byes, their split is
# decided by the winners' halves in Phase 1, so both are charged there on the
# split the state is already committed to (projected_half_balance_units).
TIER_HALF_BALANCE_WEIGHT = 5000


def placement_penalty(ctx: BracketContext, slot, trial: Trial, needs_bye):
    """Per-step feasibility penalty of placing one participant into *slot* of *trial*.

    Keeps (tops + byes) balanced across the quarters: this joint balance is what
    determines whether the remaining non-bye player quarter assignment will be
    feasible later -- each quarter must keep enough free slots for the players
    whose group top landed in the OPPOSITE half.  Concentrating tops+byes in one
    quarter shrinks its free slots and can make the later assignment impossible.

    The half balance (half_load_cost) and the byes' and tiers' own balance across
    the halves ("Freilose, Gruppenerste, ... gleichmaessig auf die Haelften
    verteilen", assignment_quality_cost) are charged on the FINISHED assignment,
    not here: accumulated as per-step marginals they charged legal layouts for the
    order they happened to be built in.  See BYE_HALF_BALANCE_WEIGHT.
    """
    num_quarters = ctx.geo.num_quarters
    slot_quarter = ctx.geo.slot_quarter
    # Combined (tops + byes) per quarter in the trial state.
    tops_in_q_now = {q: sum(1 for gq in trial.tops.values() if gq == q) for q in range(num_quarters)}
    combined_in_q = {
        q: (tops_in_q_now[q] + sum(1 for s in trial.locked if trial.state[s] == "BYE" and slot_quarter(s) == q))
        for q in range(num_quarters)
    }
    min_combined = min(combined_in_q.values())

    q = slot_quarter(slot)
    future = combined_in_q[q] + 1 + (1 if needs_bye else 0)
    # Allow up to 1 above the current minimum without penalty.
    combined_excess = max(0, future - min_combined - 1)
    return combined_excess * 10000


def half_load_cost(ctx: BracketContext, trial_tops):
    """Rank 1 of the ladder: the net half load, on a finished batch.

    A group winner forces its 2nd/3rd (delta 1/2) into the OPPOSITE half and
    its 4th (delta 3) into the SAME half, so the two halves only both fill up
    when the winners' net loads (top_net_load) cancel out.  Balancing raw
    winner counts would treat a 3-2 and a 2-3 split as equal even when only one
    is fillable, and would over-count a winner from an uneven group.

    Charged only for the imbalance the winners still to be placed can no
    longer make up (their loads summed), so a batch is never pushed into a
    half by a gap a later batch closes anyway -- that would decide halves on
    participant order and cost the country balance of the group winners.
    """
    net = {0: 0, 1: 0}
    pending = 0
    for p in ctx.top_participants:
        gq = trial_tops.get(getattr(p, "group_no", None))
        if gq is None:
            pending += abs(ctx.top_net_load[id(p)])
        else:
            net[ctx.geo.quarter_half(gq)] += ctx.top_net_load[id(p)]
    return max(0, abs(net[0] - net[1]) - pending - 1) * 100000


def projected_half_balance_units(ctx: BracketContext, trial_matches, trial_tops):
    """(bye units, tier units) of the half split *trial_matches* is committed to.

    On a finished bracket this equals check_bye_balance_halves plus
    check_placement_balance_halves.  *trial_tops* is the group -> anchor
    quarter map of the trial.  See BracketContext.half_tracked for which
    participants are projected.
    """
    if not ctx.half_balance:
        return sum(v[-1] for v in check_bye_balance_halves(trial_matches, ctx.number_of_matches)), 0
    top_group_pos = ctx.top_group_pos
    top_half = {g: ctx.geo.quarter_half(q) for g, q in trial_tops.items()}
    byes = [0, 0]
    tiers = {pos: [0, 0] for pos in ctx.balanced_tiers}
    placed = set()
    for match_idx, participants in trial_matches.items():
        h = ctx.geo.match_half(match_idx)
        for p in participants:
            if p == "BYE":
                byes[h] += 1
            elif p is not None:
                placed.add(id(p))
                if p.group_pos in tiers:
                    tiers[p.group_pos][h] += 1

    bye_slack = 0
    tier_slack = dict.fromkeys(tiers, 0)
    # A group whose winner is still pending moves as one: its anchor-bound bye
    # recipients land together, winner/4th on one side, 2nd/3rd on the other.
    pending_group_byes = {}
    for p in ctx.half_tracked:
        if id(p) in placed:
            continue
        needs_bye = id(p) in ctx.bye_recipient_ids
        h = required_half(ctx, p, top_half)
        if h is not None:
            byes[h] += needs_bye
            if p.group_pos in tiers:
                tiers[p.group_pos][h] += 1
            continue
        if p.group_pos in tiers:
            tier_slack[p.group_pos] += 1
        if not needs_bye:
            continue
        group_no = getattr(p, "group_no", None)
        delta = p.group_pos - top_group_pos
        if group_no in ctx.winner_groups and group_no not in top_half and delta <= 3:
            pending_group_byes[group_no] = pending_group_byes.get(group_no, 0) + (1 if delta in (0, 3) else -1)
        else:
            bye_slack += 1
    bye_slack += sum(abs(v) for v in pending_group_byes.values())

    def excess(counts, slack):
        return max(0, abs(counts[0] - counts[1]) - slack - 1)

    return excess(byes, bye_slack), sum(excess(tiers[pos], tier_slack[pos]) for pos in tiers)


# ---------------------------------------------------------------------------
# Rank 4 of the ladder, plus the round-two tiebreaker.  These and rank 3 are
# functions of a FINISHED assignment rather than per-step marginals, so unlike
# the two feasibility terms above they are evaluated once on the completed
# trial state instead of being accumulated placement by placement.
#
# The two feasibility terms have to stay per-step: they gate whether the REST
# of the draw can still be filled, so they must be charged as the capacity is
# consumed.  These only grade the result, and measuring the result
# directly is both exact and cheaper -- accumulating a marginal is at best a
# lower bound on it, and for bye_half_excess it was not even that (a legal
# final split could be charged for the order it was built in, which is what
# BYE_HALF_BALANCE_WEIGHT documents).
# ---------------------------------------------------------------------------
def assignment_quality_cost(ctx: BracketContext, trial_matches, trial_tops, tier_halves=True):
    """Bye/tier-half + tier-quarter balance + round-two quality for a finished state.

    *tier_halves* False leaves out the tier-half term (see fill_residual_soft).
    """
    # Only charge for a tier every member of which is already on the board.
    # A partially placed tier's counts are a moving target: in a 33-player /
    # 64-slot draw the 3rd places arrive as 9 bye recipients here and 2
    # residual players in Phase 2, so a "repair" of the 9 is chasing a number
    # Phase 2 is about to change -- and Phase 1c would happily pay a real
    # round-two violation for it.  Round two needs no such guard: it is
    # already fully determined (see score_round_two).
    tier_units = sum(
        v[-1]
        for v in check_placement_balance_quarters(trial_matches, ctx.number_of_matches)
        if sum(v[1]) == ctx.tier_totals.get(v[0], 0)
    )
    # The half terms need no "fully placed" guard: they already count every
    # participant still to come in the half it is bound to (see above).
    bye_half_units, tier_half_units = projected_half_balance_units(ctx, trial_matches, trial_tops)
    return (
        bye_half_units * BYE_HALF_BALANCE_WEIGHT
        + (tier_half_units * TIER_HALF_BALANCE_WEIGHT if tier_halves else 0)
        + tier_units * TIER_QUARTER_BALANCE_WEIGHT
        + score_round_two(trial_matches, weights=ctx.round_two_weights, bounds=ctx.bracket_bounds)
    )
