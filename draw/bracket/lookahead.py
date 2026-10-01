"""Country lookahead for the group winners.

Phase 1 places the winners one hierarchy level at a time, and half_load_cost
can leave a later level no choice: on 11 groups x 3 (33 players, 64 slots)
the two groups whose 3rd gets no bye must share the half that takes 6
winners.  An earlier level that already put the other winner of one of
those groups' countries in that half has then made the country pile-up
unavoidable.  So each candidate assignment is also charged for the best
winner country split still REACHABLE: the pending winners enumerated over
the halves their own level still has room in, keeping the final net half
load balanced.  Enumeration is exponential in the pending winners, so it
only runs once at most WINNER_LOOKAHEAD_MAX_PENDING are left; the levels
before that are too wide open for a single pile-up to be forced anyway.

The same enumeration also scores rank 3, the bye/tier half balance, of each
reachable completion.  projected_half_balance_units treats a pending winner
as free to take either half, but half_load_cost may not let it: on doubles
10 groups x 2 (32 slots, 12 byes) a level that put both groups whose
runner-up also gets a bye into one half left the last level only 6/4
winner splits that keep the net load balanced.  The lookahead returns what
the best reachable completion costs ON TOP of the projection's own lower
bound, so assignment_quality_cost still charges the rest exactly once.
"""

from typing import TYPE_CHECKING

from draw.bracket.state import opponent_slot

if TYPE_CHECKING:
    from draw.bracket.context import BracketContext

# winner_country_lookahead enumerates 2^k half choices for the k group winners
# still to be placed; 12 keeps one enumeration at a few thousand leaves.
WINNER_LOOKAHEAD_MAX_PENDING = 12


def winner_country_lookahead(ctx: BracketContext, trial_state, trial_tops):
    """Cost of the best winner split still reachable: its country_half cost,
    plus its bye/tier half balance beyond what projected_half_balance_units
    already charges for this state (never negative)."""
    geo = ctx.geo
    placed, pending = [], []
    for p in ctx.top_sorted:
        gq = trial_tops.get(getattr(p, "group_no", None))
        (pending if gq is None else placed).append((p, None if gq is None else geo.quarter_half(gq)))
    if not pending or len(pending) > WINNER_LOOKAHEAD_MAX_PENDING:
        return 0
    cache_key = frozenset((id(p), h) for p, h in placed)
    if cache_key in ctx.winner_lookahead_cache:
        return ctx.winner_lookahead_cache[cache_key]

    keys = ctx.half_balance_keys
    counts = {}
    net = [0, 0]
    # Half 0 minus half 1 of the byes and tiers, from the placed winners' groups.
    balance = dict.fromkeys(keys, 0)
    pending_slack = dict.fromkeys(keys, 0)
    for p, h in placed:
        net[h] += ctx.top_net_load[id(p)]
        for country in ctx.winner_countries[id(p)]:
            counts.setdefault(country, [0, 0])[h] += 1
        for key, value in ctx.group_half_vector.get(getattr(p, "group_no", None), {}).items():
            balance[key] += value if h == 0 else -value
    for p, _ in pending:
        for key, value in ctx.group_half_vector.get(getattr(p, "group_no", None), {}).items():
            pending_slack[key] += abs(value)

    def balance_cost(slack):
        return sum(ctx.half_balance_weight[key] * max(0, abs(balance[key]) - slack[key] - 1) for key in keys)

    # What projected_half_balance_units already charges for this state.
    projected = balance_cost({key: ctx.free_half_slack[key] + pending_slack[key] for key in keys})
    # Room per (level, half) for the pending winners.
    room = {}
    for p, _ in pending:
        level = ctx.winner_level_slots.get(id(p), ())
        if id(level) in room:
            continue
        needs_bye = id(p) in ctx.bye_recipient_ids
        level_room = [0, 0]
        for s in level:
            if trial_state[s] is None and not (needs_bye and trial_state[opponent_slot(s)] is not None):
                level_room[geo.slot_half(s)] += 1
        room[id(level)] = level_room

    best = None

    def search(index):
        nonlocal best
        if index == len(pending):
            if abs(net[0] - net[1]) > 1:
                return
            excess = sum(max(0, abs(c0 - c1) - ctx.winner_country_slack) for c0, c1 in counts.values())
            cost = balance_cost(ctx.free_half_slack) + excess * ctx.bracket_weights["country_half"]
            if best is None or cost < best:
                best = cost
            return
        if best is not None and best <= projected:
            return
        p = pending[index][0]
        level_room = room[id(ctx.winner_level_slots.get(id(p), ()))]
        for h in (0, 1):
            if level_room[h] == 0:
                continue
            level_room[h] -= 1
            net[h] += ctx.top_net_load[id(p)]
            vector = ctx.group_half_vector.get(getattr(p, "group_no", None), {})
            for key, value in vector.items():
                balance[key] += value if h == 0 else -value
            for country in ctx.winner_countries[id(p)]:
                counts.setdefault(country, [0, 0])[h] += 1
            search(index + 1)
            for country in ctx.winner_countries[id(p)]:
                counts[country][h] -= 1
            for key, value in vector.items():
                balance[key] -= value if h == 0 else -value
            net[h] -= ctx.top_net_load[id(p)]
            level_room[h] += 1

    search(0)
    cost = 0 if best is None else best - projected
    ctx.winner_lookahead_cache[cache_key] = cost
    return cost
