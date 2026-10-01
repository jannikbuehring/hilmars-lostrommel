"""Phase 2: assign every remaining (non-bye) participant its quarter.

With the byes already balanced by Phase 1/1b/1c, the residual demand is small.
"""

from checks.bracket_checker import participant_countries
from draw.bracket.context import BracketContext
from draw.bracket.rules import allowed_for
from draw.bracket.state import BracketState, opponent_slot


def assign_quarter_buckets(ctx: BracketContext, state: BracketState, non_top_participants):
    """Return dict mapping id(participant) → required quarter (0-3).

    Uses the group_top_quarter map built during Phase 1.  Capacity is tracked
    dynamically: after every commit the remaining slot count for the chosen
    quarter is decremented.  Bye recipients (those in ctx.non_top_bye_ids)
    consume two slots (player + adjacent BYE).

    Selection criterion for delta=1 (2nd-place) players when both options
    are valid: primary = most remaining quarter capacity, secondary =
    fewest same-country players already committed to that quarter.  This
    prevents all players from piling into the same quarter when country
    counts are tied (the most common case early in assignment).
    """
    slot_state = state.slot_state
    slot_quarter = ctx.geo.slot_quarter
    top_group_pos = ctx.top_group_pos

    # Prime the country-count table with already-placed (seeded) participants.
    quarter_country_counts: dict = {q: {} for q in range(4)}
    for slot_idx, p in slot_state.items():
        if p is None or p == "BYE":
            continue
        q = slot_quarter(slot_idx)
        for country in participant_countries(p):
            quarter_country_counts[q][country] = quarter_country_counts[q].get(country, 0) + 1

    # quarter_remaining tracks how many free slots each quarter still has.
    # Initialise from total slots, then subtract already-locked slots.
    quarter_remaining: dict = {
        q: sum(1 for s in range(1, ctx.bracket_size + 1) if slot_quarter(s) == q) for q in range(4)
    }
    for s in state.locked_slots:
        quarter_remaining[slot_quarter(s)] -= 1

    required_quarter_map: dict = {}
    # Tracks which opposite-half quarter each group already used for its
    # delta=1 player so the delta=2 player goes to the other one.
    group_opposite_half_used: dict = {}

    # Seed it from what Phase 1/1b already committed.  A group's delta=1 may
    # have received a bye and been placed back in Phase 1b, in which case it
    # is NOT in non_top_participants and this map would start empty — leaving
    # the residual delta=2 to be chosen on capacity alone and land in the very
    # quarter its runner-up already occupies.  That is a violation of a rule
    # that "darf eigentlich nicht verletzt werden" (open_questions.md), and it
    # fires for every group of that shape: a 12-group / 36-player / 64-slot
    # layout produced 8 of them.  Mirrors group_opposite_quarter_used, which
    # feeds the same sibling_quarter into allowed_quarters inside 1b.
    for placed_slot, placed in slot_state.items():
        if placed is None or placed == "BYE":
            continue
        placed_group = getattr(placed, "group_no", None)
        if placed_group is None or placed.group_pos is None:
            continue
        if placed.group_pos - top_group_pos in (1, 2):
            group_opposite_half_used.setdefault(placed_group, slot_quarter(placed_slot))

    delta3_players, delta1_players, delta2_players, unconstrained_players = [], [], [], []

    for p in non_top_participants:
        group_no = getattr(p, "group_no", None)
        if group_no is None or group_no not in state.group_top_quarter:
            unconstrained_players.append(p)
            continue
        delta = p.group_pos - top_group_pos
        if delta == 3:
            delta3_players.append(p)
        elif delta == 1:
            delta1_players.append(p)
        elif delta == 2:
            delta2_players.append(p)
        else:
            unconstrained_players.append(p)

    def _slots_for(p):
        return 2 if id(p) in ctx.non_top_bye_ids else 1

    def _commit(p, q):
        required_quarter_map[id(p)] = q
        quarter_remaining[q] -= _slots_for(p)
        for country in participant_countries(p):
            quarter_country_counts[q][country] = quarter_country_counts[q].get(country, 0) + 1

    def _country_cost(p, q):
        return sum(quarter_country_counts[q].get(c, 0) for c in participant_countries(p))

    def _best_quarter(p, candidates):
        """Pick the quarter from *candidates* with the most remaining capacity;
        use country-conflict count as tiebreaker.

        A same-tier count was tried as an intermediate tiebreaker, to spread
        the placement tiers over the quarters the way Phase 1/1b now does.
        It does not work here: capacity almost always decides before any
        tiebreaker is reached, so across the real input the tier imbalance was
        unchanged (12 units either way) while country conflicts rose (36 -> 38
        first-round, 18 -> 21 quarter spread).  See check_placement_balance_quarters
        for what this phase consequently still leaves on the table.
        """
        return min(candidates, key=lambda q: (-quarter_remaining[q], _country_cost(p, q)))

    # delta=3 (4th place): other quarter of the SAME half as pos-1 (in a small
    # bracket with one quarter per half, that half's only quarter).
    for p in delta3_players:
        _commit(p, _best_quarter(p, allowed_for(ctx, state.group_top_quarter, p)))

    def _place_sibling(p):
        """Place a delta=1/2 player in the opposite half, away from its sibling.

        Whichever of the group's 2nd/3rd is placed first -- here or with a bye in
        Phase 1b -- claims its quarter; the other is steered to the one left.
        """
        chosen_q = _best_quarter(
            p, allowed_for(ctx, state.group_top_quarter, p, group_opposite_half_used.get(p.group_no))
        )
        group_opposite_half_used.setdefault(p.group_no, chosen_q)
        _commit(p, chosen_q)

    # A full group's delta=1 and delta=2 occupy the two DIFFERENT opposite-half
    # quarters (one each), so their placement is effectively forced.  A "solo"
    # delta=1 — a short group with no delta=2 sibling, e.g. a consolation group
    # missing its 3rd — has a real choice, so defer it until AFTER the forced
    # delta=2 players are committed.  Placed greedily up front, a solo delta=1
    # can steal the quarter a full group's delta=2 is forced into, overflowing
    # it and needlessly triggering the quarter-capacity degrade.
    groups_with_delta2 = {p.group_no for p in delta2_players}
    paired_delta1 = [p for p in delta1_players if p.group_no in groups_with_delta2]
    solo_delta1 = [p for p in delta1_players if p.group_no not in groups_with_delta2]

    # delta=1 (paired): pick the OPPOSITE-half quarter with the most remaining
    # capacity; break ties by fewest same-country conflicts.
    for p in paired_delta1:
        _place_sibling(p)

    # delta=2 (3rd place): MUST use the OTHER opposite-half quarter so that
    # 2nd and 3rd from the same group land in different quarters.
    for p in delta2_players:
        _place_sibling(p)

    # delta=1 (solo): short groups whose delta=1 has no residual delta=2 sibling
    # -- placed last, into whatever opposite-half capacity the forced players
    # left free, and away from a delta=2 that took a bye in Phase 1b.
    for p in solo_delta1:
        _place_sibling(p)

    # Unconstrained players: group by group_no, assign each group to the
    # quarter with the most remaining capacity.
    unc_by_group: dict = {}
    _none_ctr = 0
    for p in unconstrained_players:
        gno = getattr(p, "group_no", None)
        if gno is None:
            _none_ctr += 1
            key = f"_none_{_none_ctr}"
        else:
            key = gno
        unc_by_group.setdefault(key, []).append(p)

    for group_members in unc_by_group.values():
        n = sum(_slots_for(p) for p in group_members)
        viable = [q for q in range(4) if quarter_remaining[q] >= n]
        chosen_q = max(viable if viable else range(4), key=lambda q: quarter_remaining[q])
        for p in group_members:
            _commit(p, chosen_q)

    return required_quarter_map


def rebalance_bottom_tier_quarters(ctx: BracketContext, state: BracketState, required_quarter, residual_players):
    """Repair the per-quarter bottom-tier supply that check_top_easy_first_round needs.

    A post-pass over the Phase-2 assignment so every quarter holding a non-bye
    group winner also holds a bottom-tier player to pair it with.

    A group winner earned a BYE or a lowest-placed opponent, and that outranks
    the country distribution (open_questions.md 29.07).  Scoring alone cannot
    deliver it: the phase-5 Monte Carlo only shuffles WITHIN a quarter, so a
    non-bye winner can only be paired with a bottom-tier player that Phase 2
    already assigned to its quarter — and assign_quarter_buckets decides that
    blind to this rule, breaking the very first capacity tie on quarter index.
    For the live 10-group/32-slot layout that deterministically splits the
    3rd places 2/3 across the two quarters that need 3 and 2, stranding one
    winner in each half.

    Exchanging the quarters of a group's delta=1/delta=2 pair is exactly
    capacity-neutral (each quarter still receives one of the two), and both
    stay in the opposite half in different quarters — so the half separation
    and the 2nd/3rd different-quarter rule are untouched and only the
    deliberately lower-weighted country spread can shift.  That makes it safe
    to repair the allocation AFTER capacity has been settled, which a tie-break
    inside _best_quarter could not do: it would only steer the first delta=1 of
    each half (capacity forces the rest), and ranking it above capacity would
    risk the far more expensive quarter_capacity_degrade path.

    Deterministic and consumes no RNG.  Known limitation: only delta=1/delta=2
    pairs can be swapped, because only those two share a half and so can trade
    quarters without moving anyone across halves.  A 4-tier bracket's bottom
    tier is delta=3, which lives in the anchor's OWN half, so there swapping
    would break the half separation outright — that case bails out below and
    falls back to scoring alone.
    """
    top_group_pos = ctx.top_group_pos
    positions = [p.group_pos for p in ctx.participants if p.group_pos is not None]
    if not positions:
        return
    bottom_pos = max(positions)
    bottom_delta = bottom_pos - top_group_pos
    # delta < 2: fewer than three tiers, the rule is exempt (see the checker).
    # delta > 2: the bottom tier sits in the anchor's own half, so no swap here
    # is half-preserving; leave it to the score.
    if bottom_delta != 2:
        return

    # Non-bye winners whose opponent slot is still free — one bottom-tier
    # player is owed to each of them, in their own quarter.
    slot_state = state.slot_state
    demand = {q: 0 for q in range(4)}
    for slot in range(1, ctx.bracket_size + 1):
        participant = slot_state[slot]
        if participant is None or participant == "BYE":
            continue
        if participant.group_pos != top_group_pos:
            continue
        if slot_state[opponent_slot(slot)] is None:
            demand[ctx.geo.slot_quarter(slot)] += 1

    players_by_identity = {id(p): p for p in residual_players}

    def unmet_demand():
        supply = {q: 0 for q in range(4)}
        for participant_id, quarter in required_quarter.items():
            participant = players_by_identity.get(participant_id)
            if participant is not None and participant.group_pos == bottom_pos:
                supply[quarter] += 1
        return sum(max(0, demand[q] - supply[q]) for q in range(4))

    # Swap candidates: a bottom-tier player and a delta 1/2 sibling of the same
    # group that currently sit in different quarters.
    members_by_group: dict = {}
    for p in residual_players:
        group_no = getattr(p, "group_no", None)
        if group_no is not None:
            members_by_group.setdefault(group_no, []).append(p)

    swap_candidates = []
    for members in members_by_group.values():
        bottom_members = [p for p in members if p.group_pos == bottom_pos]
        other_members = [p for p in members if p.group_pos != bottom_pos and p.group_pos - top_group_pos in (1, 2)]
        for low in bottom_members:
            for high in other_members:
                if required_quarter.get(id(low)) != required_quarter.get(id(high)):
                    swap_candidates.append((low, high))

    # Greedy first-improving swaps; bounded by the candidate count.
    for _ in range(len(swap_candidates)):
        base_cost = unmet_demand()
        if base_cost == 0:
            return
        for low, high in swap_candidates:
            low_q, high_q = required_quarter[id(low)], required_quarter[id(high)]
            required_quarter[id(low)], required_quarter[id(high)] = high_q, low_q
            if unmet_demand() < base_cost:
                break
            required_quarter[id(low)], required_quarter[id(high)] = low_q, high_q
        else:
            return  # no single swap improves any more


def over_capacity_quarters(ctx: BracketContext, state: BracketState, residual_players, required_quarter):
    """Quarters assigned more residual players than they have free slots."""
    free_slots = [s for s in range(1, ctx.bracket_size + 1) if state.slot_state[s] is None]
    free_by_quarter = {q: sum(1 for s in free_slots if ctx.geo.slot_quarter(s) == q) for q in range(4)}
    required_counts = {q: 0 for q in range(4)}
    for p in residual_players:
        rq = required_quarter.get(id(p))
        if rq is not None:
            required_counts[rq] += 1
    return [q for q in range(4) if required_counts[q] > free_by_quarter[q]]
