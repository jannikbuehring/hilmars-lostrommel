"""Checks related to single-elimination bracket assignments."""
from collections import defaultdict
from typing import Dict, List
from models.player import players_by_start_number


# Weights for score_round_two.  See its docstring for why the three tier weights
# must live in the 36..49 band and the country one below round one's.
ROUND_TWO_DEFAULT_WEIGHTS = {
    "round_two_first_vs_first": 45,
    "round_two_top_easy_opponent": 42,
    "round_two_bottom_vs_bottom": 38,
    # Must stay below country_half and above country_quarter; a config that
    # changes either should re-check it (validate_bracket_weights warns).
    "round_two_country_first": 9,
}


def _match_half(match_index: int, number_of_matches: int) -> int:
    """Return 0 for first half, 1 for second half."""
    half = 0 if match_index <= (number_of_matches // 2) else 1
    return half


def _match_quarter(match_index: int, number_of_matches: int) -> int:
    """Return 0-3 for the quarter of the bracket.

    For small brackets with fewer than 4 matches the highest valid quarter
    index is returned (e.g. 2-match bracket yields quarters 0 and 1 only).
    """
    matches_per_quarter = max(1, number_of_matches // 4)
    return min(3, (match_index - 1) // matches_per_quarter)


def check_half_group_separation(matches: Dict[int, List], number_of_matches: int, bounds=None):
    """
    Ensure that for each group the bracket's top and top+3 positions are placed
    in one half and top+1/top+2 in the other half. Positions are relative to the
    bracket, like check_no_first_vs_first: a main draw runs 1..4, a consolation
    4..6.  *bounds* is an optional pre-computed ``(top, bottom)`` pair for
    partial states.  Returns list of violations as tuples:
      (group_no, details)
    """
    violations = []

    if bounds is None:
        bounds = _bracket_position_bounds(matches)
    if bounds is None:
        return violations
    top = bounds[0]

    # collect group_pos halves
    group_pos_halves = defaultdict(lambda: {"14": set(), "23": set()})
    for match_idx, participants in matches.items():
        for p in participants:
            if p is None or p == "BYE":
                continue
            try:
                group_no = p.group_no
                pos = p.group_pos
            except Exception:
                continue
            if pos is None:
                continue
            h = _match_half(match_idx, number_of_matches)
            delta = pos - top
            if delta in (0, 3):
                group_pos_halves[group_no]["14"].add(h)
            if delta in (1, 2):
                group_pos_halves[group_no]["23"].add(h)

    anchor_label = f"{top}/{top + 3}"
    opposite_label = f"{top + 1}/{top + 2}"
    for group_no, halves in group_pos_halves.items():
        h14 = halves["14"]
        h23 = halves["23"]
        # If any of the sets spans both halves -> violation
        if len(h14) > 1:
            violations.append((group_no, f"positions {anchor_label} split across halves"))
        if len(h23) > 1:
            violations.append((group_no, f"positions {opposite_label} split across halves"))
        # They must be in different halves
        if h14 & h23:
            violations.append((group_no, f"positions {anchor_label} and {opposite_label} share a half"))

    return violations


def check_quarter_group_separation(matches: Dict[int, List], number_of_matches: int):
    """Check that within each group:
      - 2nd and 3rd-highest placements are in *different* quarters.
      - The 4th-highest placement is in the same half but a *different* quarter
        from the 1st-highest placement.

    Returns a list of violation tuples (group_no, description).
    """
    violations = []

    group_pos_quarters: dict = defaultdict(lambda: defaultdict(set))
    for match_idx, participants in matches.items():
        for p in participants:
            if p is None or p == "BYE":
                continue
            try:
                group_no = p.group_no
                pos = p.group_pos
            except Exception:
                continue
            q = _match_quarter(match_idx, number_of_matches)
            group_pos_quarters[group_no][pos].add(q)

    all_positions = [pos for pd in group_pos_quarters.values() for pos in pd]
    if not all_positions:
        return violations
    top_pos = min(all_positions)

    for group_no, pos_map in group_pos_quarters.items():
        top_qs = pos_map.get(top_pos, set())
        second_qs = pos_map.get(top_pos + 1, set())
        third_qs = pos_map.get(top_pos + 2, set())
        fourth_qs = pos_map.get(top_pos + 3, set())

        # 2nd and 3rd must be in different quarters
        if second_qs and third_qs and (second_qs & third_qs):
            violations.append((group_no, "positions 2nd/3rd in same quarter"))

        # 4th must be in the same half as 1st but a different quarter
        if top_qs and fourth_qs:
            top_halves = {q // 2 for q in top_qs}
            fourth_halves = {q // 2 for q in fourth_qs}
            if top_halves != fourth_halves:
                violations.append((group_no, "position 4th not in same half as 1st"))
            elif top_qs & fourth_qs:
                violations.append((group_no, "position 4th in same quarter as 1st"))

    return violations


def check_no_first_vs_first(matches: Dict[int, List], bounds=None):
    """Check that no bracket-highest placements meet each other in round one.

    *bounds* is an optional pre-computed ``(top, bottom)`` pair.  It exists for
    :func:`check_round_two_matchups`, which evaluates a *virtual* round-two
    pairing dict holding only the participants the byes already decided — too
    few to derive the bracket's real tier range from.
    """
    violations = []

    # Determine the top placement present in this bracket.
    # In the main bracket this will normally be 1, but in consolation it may be 2 or higher.
    if bounds is None:
        bounds = _bracket_position_bounds(matches)
    if bounds is None:
        return violations

    bracket_top_position = bounds[0]

    for match_idx, participants in matches.items():
        if len(participants) < 2:
            continue
        a, b = participants[0], participants[1]
        if a == "BYE" or b == "BYE":
            continue
        try:
            if a.group_pos == bracket_top_position and b.group_pos == bracket_top_position:
                violations.append((match_idx, a, b))
        except Exception:
            continue
    return violations


def forced_first_vs_first(top_count: int, number_of_matches: int) -> int:
    """Return how many top-vs-top matches no bracket of this size can avoid.

    Every bye absorbs one top-tier participant and every lower-tier participant
    can absorb one more; whoever of the top tier is left over must meet each
    other.  With ``byes = 2 * number_of_matches - participants`` that leftover is
    ``2 * top_count - 2 * number_of_matches`` players, i.e.
    ``top_count - number_of_matches`` matches.  Example: 8 groups of 3 with the
    top two advancing leave a consolation of 8 thirds -- 4 matches, all of them
    third vs third, and none of it a rule break.
    """
    return max(0, top_count - number_of_matches)


def split_first_vs_first(violations: List, forced: int):
    """Split check_no_first_vs_first's result into ``(avoidable, forced)``.

    The forced matches are interchangeable, so which entries land in which list
    is arbitrary; only the counts carry meaning.
    """
    forced = min(forced, len(violations))
    return violations[forced:], violations[:forced]


def _top_count(matches: Dict[int, List], top: int) -> int:
    """Count the participants of placement tier *top* present in *matches*.

    Only the full count for a finished bracket; a partial state must pass the
    real count in, like it does *bounds*.
    """
    return sum(
        1
        for participants in matches.values()
        for p in participants
        if p not in (None, "BYE") and getattr(p, "group_pos", None) == top
    )


def _bracket_position_bounds(matches: Dict[int, List]):
    """Return (top, bottom) group_pos present in *matches*, or None when empty.

    Both bounds are relative to this bracket, like check_no_first_vs_first's
    bracket_top_position: a main draw normally runs 1..3, a consolation 4..6.
    """
    positions = []
    for participants in matches.values():
        for p in participants:
            if p == "BYE" or p is None:
                continue
            if getattr(p, "group_pos", None) is not None:
                positions.append(p.group_pos)
    if not positions:
        return None
    return min(positions), max(positions)


def _participant_countries(participant):
    """Return the country/countries a bracket participant brings to a match.

    A doubles/mixed participant is a team of two and therefore carries two
    countries.  Duplicated from draw.bracket_drawer's identically named closure,
    which is nested inside draw_bracket() and so cannot be imported.
    """
    countries = []
    try:
        countries.append(players_by_start_number[participant.start_number_a].country)
    except (KeyError, AttributeError):
        pass
    try:
        if getattr(participant, "start_number_b", None) is not None:
            countries.append(players_by_start_number[participant.start_number_b].country)
    except (KeyError, AttributeError):
        pass
    return countries


def _first_round_pair(participants):
    """Return the two real opponents of a match, or None if it isn't a real pairing.

    slots_to_matches yields short, empty and half-filled ([None, player]) matches
    while a draw is still in progress, and a bye match holds the string "BYE".
    """
    if len(participants) < 2:
        return None
    a, b = participants[0], participants[1]
    if a is None or b is None or a == "BYE" or b == "BYE":
        return None
    return a, b


def check_top_easy_first_round(matches: Dict[int, List], bounds=None):
    """Bracket-top placements earned a BYE or a bottom-tier round-one opponent.

    open_questions.md: "Gruppenerste ... nach Möglichkeit Freilos oder gegen
    Gruppendritten" and "1. gegen dritter oder freilos ist wichtiger als
    länderverteilung".  Returns (match_idx, top_player, opponent) per aggrieved
    top placement.

    Top-vs-top is deliberately NOT reported here: check_no_first_vs_first owns
    that match, so the two terms partition the space instead of double-charging
    one pairing.  Note that top-vs-top is unreachable by construction anyway (see
    ARCHITECTURE.md §5 phase 1), which makes this check the rule that actually
    constrains a group winner's opponent.

    Only applies with at least three placement tiers (bottom - top >= 2).  In a
    two-tier bracket — every doubles/mixed draw — "bottom" IS the runner-up, so
    the rule would collapse into a restatement of check_no_first_vs_first.

    *bounds* overrides the derived tier range; see check_no_first_vs_first.
    """
    if bounds is None:
        bounds = _bracket_position_bounds(matches)
    if bounds is None:
        return []
    top, bottom = bounds
    if bottom - top < 2:
        return []

    violations = []
    for match_idx, participants in matches.items():
        pair = _first_round_pair(participants)
        if pair is None:
            continue
        a, b = pair
        for player, opponent in ((a, b), (b, a)):
            if getattr(player, "group_pos", None) != top:
                continue
            if getattr(opponent, "group_pos", None) not in (top, bottom):
                violations.append((match_idx, player, opponent))
    return violations


def check_no_bottom_vs_bottom(matches: Dict[int, List], bounds=None):
    """Check that no two bottom-tier placements meet in round one.

    open_questions.md: "3. gegen 3. wäre nicht okay, 2. gegen 3. schon".  The
    consequence of check_top_easy_first_round — the scarce bottom-tier players
    are owed to the top placements, and pairing two of them wastes both.  This
    also subsumes the runner-up preference ("Gruppenzweiten nach Möglichkeit
    Freilos oder gegen Gruppendritten, sonst gegen Gruppenzweiten"): given
    {2,2,3,3}, penalising 3-vs-3 is exactly what pushes the 3s onto the 2s, and
    no other term distinguishes {2v3, 2v3} from {2v2, 3v3}.

    Soft, not hard: with very many byes it is structurally forced ("Bei ganz
    vielen freilosen dritter gegen dritter").  Same three-tier guard as
    check_top_easy_first_round, since a two-tier bracket's "bottom" is the
    runner-up and runner-up-vs-runner-up is the accepted fallback.

    *bounds* overrides the derived tier range; see check_no_first_vs_first.
    """
    if bounds is None:
        bounds = _bracket_position_bounds(matches)
    if bounds is None:
        return []
    top, bottom = bounds
    if bottom - top < 2:
        return []

    violations = []
    for match_idx, participants in matches.items():
        pair = _first_round_pair(participants)
        if pair is None:
            continue
        a, b = pair
        if getattr(a, "group_pos", None) == bottom and getattr(b, "group_pos", None) == bottom:
            violations.append((match_idx, a, b))
    return violations


def check_country_conflicts_first_round(matches: Dict[int, List]):
    """Return matches whose two opponents share a country in round one.

    open_questions.md: "same country matchups nach Möglichkeit vermeiden".
    Complements check_country_balance_halves/_quarters, which only balance
    *counts* across halves and quarters and so never object to a same-country
    pairing.  Unlike the placement rules above this applies to every bracket,
    with no tier guard.

    For doubles/mixed a participant is a team carrying up to two countries; a
    same-country *team* is not a conflict, only an overlap with the OPPONENT is.
    Returns (match_idx, sorted shared countries, a, b).
    """
    violations = []
    for match_idx, participants in matches.items():
        pair = _first_round_pair(participants)
        if pair is None:
            continue
        a, b = pair
        shared = {c for c in _participant_countries(a) if c} & {c for c in _participant_countries(b) if c}
        if shared:
            violations.append((match_idx, sorted(shared), a, b))
    return violations


def check_country_balance_halves(matches: Dict[int, List], number_of_matches: int):
    """Compute country counts per half and flag imbalances.

    Returns list of violations as tuples:
      (country, count_half0, count_half1, violation_amount)

    For doubles/mixed (detected by presence of paired participants), allow a difference
    of up to 2. If the excess in one half can be (partially) explained by full-country
    teams concentrated in that half (each full team contributes 2 players), the
    violation amount is reduced accordingly. Purely explained excesses are ignored.
    """
    counts = defaultdict(lambda: [0, 0])
    # track full-country teams per country per half (counts of teams)
    full_team_counts = defaultdict(lambda: [0, 0])
    is_doubles = False
    for match_idx, participants in matches.items():
        half = _match_half(match_idx, number_of_matches)
        for p in participants:
            if p == "BYE" or p is None:
                continue
            try:
                a = players_by_start_number[p.start_number_a]
            except Exception:
                continue
            counts[a.country][half] += 1
            if getattr(p, "start_number_b", None) is not None:
                b = players_by_start_number[p.start_number_b]
                counts[b.country][half] += 1
                is_doubles = True
                try:
                    if a.country == b.country:
                        full_team_counts[a.country][half] += 1
                except Exception:
                    pass

    allowed_diff = 2 if is_doubles else 1

    violations = []
    for country, (c0, c1) in counts.items():
        diff = abs(c0 - c1)
        if diff <= allowed_diff:
            continue
        violation_amount = diff - allowed_diff
        # determine which half has the excess
        half_with_max = 0 if c0 > c1 else 1
        # number of players from full teams in that half
        full_team_players = full_team_counts.get(country, [0, 0])[half_with_max] * 2
        # reduce violation by players that can be explained by full teams
        remaining_violation = violation_amount - full_team_players
        if remaining_violation > 0:
            violations.append((country, c0, c1, remaining_violation))
    return violations


def check_bye_balance_halves(matches: Dict[int, List], number_of_matches: int):
    """Flag byes unevenly spread across the two halves.

    Returns a list with at most one violation tuple:
      (count_half0, count_half1, violation_amount)

    "Freilose ... gleichmaessig auf die Haelften verteilen" (open_questions.md).  A
    difference of 1 is allowed, since an odd number of byes cannot split evenly;
    the violation amount is the excess above that, mirroring the magnitude
    convention of the country balance checks.

    Deliberately NOT part of :func:`score_bracket` — see the note there.  The
    drawer calls this function directly from its Phase 1/1b/1c objective
    (``assignment_quality_cost``), which is where the rule is enforced; this
    checker also exists so the viewers can report it.
    """
    counts = [0, 0]
    for match_idx, participants in matches.items():
        if any(p == "BYE" for p in participants):
            counts[_match_half(match_idx, number_of_matches)] += 1

    violation_amount = abs(counts[0] - counts[1]) - 1
    if violation_amount <= 0:
        return []
    return [(counts[0], counts[1], violation_amount)]


def check_country_balance_quarters(matches: Dict[int, List], number_of_matches: int):
    """Compute country counts per quarter and flag concentrations.

    Returns list of violations as tuples:
      (country, counts_per_quarter, violation_amount)

    Complements :func:`check_country_balance_halves` at the finer quarter
    granularity: a country's players should ideally spread one per quarter
    (4 GER players -> one in each quarter).  The per-quarter allowance is
    ceil(total / num_quarters), plus 1 for doubles/mixed, and the violation is
    the excess above that allowance summed over the quarters.  As in the halves
    check, excess explained by full-country teams (which occupy a single slot
    with two same-country players) is forgiven.

    Weighted *below* the half-level balance in score_bracket, so spreading
    across the halves stays the more important objective.
    """
    # Derive the quarter count from the bracket itself rather than assuming 4:
    # small brackets only ever yield quarters 0/1 (see _match_quarter).
    num_quarters = len({_match_quarter(i, number_of_matches) for i in range(1, number_of_matches + 1)})
    if num_quarters < 2:
        return []

    counts = defaultdict(lambda: [0] * num_quarters)
    # track full-country teams per country per quarter (counts of teams)
    full_team_counts = defaultdict(lambda: [0] * num_quarters)
    is_doubles = False
    for match_idx, participants in matches.items():
        quarter = _match_quarter(match_idx, number_of_matches)
        if quarter >= num_quarters:
            continue
        for p in participants:
            if p == "BYE" or p is None:
                continue
            try:
                a = players_by_start_number[p.start_number_a]
            except Exception:
                continue
            counts[a.country][quarter] += 1
            if getattr(p, "start_number_b", None) is not None:
                b = players_by_start_number[p.start_number_b]
                counts[b.country][quarter] += 1
                is_doubles = True
                try:
                    if a.country == b.country:
                        full_team_counts[a.country][quarter] += 1
                except Exception:
                    pass

    violations = []
    for country, quarter_counts in counts.items():
        total = sum(quarter_counts)
        # Ideal share rounded up; doubles get one extra slot of slack per quarter.
        allowed = -(-total // num_quarters) + (1 if is_doubles else 0)
        teams = full_team_counts.get(country, [0] * num_quarters)
        violation_amount = 0
        for quarter, count in enumerate(quarter_counts):
            excess = count - allowed
            if excess <= 0:
                continue
            # players in this quarter that are explained by full-country teams
            violation_amount += max(0, excess - teams[quarter] * 2)
        if violation_amount > 0:
            violations.append((country, list(quarter_counts), violation_amount))
    return violations


def check_base_conflicts_first_round(matches: Dict[int, List]):
    """Return list of matches where both participants share the same base in first round."""
    violations = []
    for match_idx, participants in matches.items():
        if len(participants) < 2:
            continue
        a, b = participants[0], participants[1]
        if a == "BYE" or b == "BYE":
            continue
        try:
            pa = players_by_start_number[a.start_number_a]
            pb = players_by_start_number[b.start_number_a]
        except Exception:
            continue
        if pa.base and pb.base and pa.base == pb.base:
            violations.append((match_idx, pa.base, a, b))
    return violations


def check_placement_balance_quarters(matches: Dict[int, List], number_of_matches: int):
    """Flag a placement tier piling into one quarter of a half.

    open_questions.md: "Freilose, Gruppenerste, Gruppenzweite und Gruppendritte
    gleichmaessig auf die Haelften verteilen" — one level finer than the halves,
    which is where the drawer already enforces it.

    Compares the two quarters of the SAME half rather than all four, because a
    participant's half is not a free choice: the separation rules pin 1st/4th to
    the group's anchor half and 2nd/3rd to the opposite one, so an uneven
    half-level split can be structurally forced.  Which quarter *within* that
    half a participant takes is free, and that is exactly what this measures —
    so the check never flags an imbalance the draw could not have avoided.

    A difference of 1 is allowed (an odd tier count cannot split evenly).
    Returns (group_pos, counts_per_quarter, violation_amount) per aggrieved tier,
    mirroring the magnitude convention of the country balance checks.
    """
    num_quarters = len({_match_quarter(i, number_of_matches) for i in range(1, number_of_matches + 1)})
    quarters_per_half = num_quarters // 2
    if quarters_per_half < 2:
        # One quarter per half: nothing is free to balance.
        return []

    counts = defaultdict(lambda: [0] * num_quarters)
    for match_idx, participants in matches.items():
        quarter = _match_quarter(match_idx, number_of_matches)
        if quarter >= num_quarters:
            continue
        for p in participants:
            if p == "BYE" or p is None:
                continue
            group_pos = getattr(p, "group_pos", None)
            if group_pos is None:
                continue
            counts[group_pos][quarter] += 1

    violations = []
    for group_pos, quarter_counts in sorted(counts.items()):
        violation_amount = 0
        for half_start in range(0, num_quarters, quarters_per_half):
            half_quarters = quarter_counts[half_start:half_start + quarters_per_half]
            violation_amount += max(0, max(half_quarters) - min(half_quarters) - 1)
        if violation_amount > 0:
            violations.append((group_pos, list(quarter_counts), violation_amount))
    return violations


def _bye_advancer(participants):
    """The participant that advances without playing, or None when undecided.

    A match decides its winner in advance only when one side is a BYE; a real
    pairing (or a still-incomplete match) leaves the next round open.
    """
    if len(participants) < 2:
        return None
    a, b = participants[0], participants[1]
    if a == "BYE" and b is not None and b != "BYE":
        return b
    if b == "BYE" and a is not None and a != "BYE":
        return a
    return None


def derive_round_two_matches(matches: Dict[int, List]):
    """Return the round-two pairings the byes already decide.

    Round-two match *r* is fed by first-round matches ``2r-1`` and ``2r``.  A
    side is filled only when its feeder was a bye, otherwise it stays None —
    which :func:`_first_round_pair` already skips, so every round-one checker
    works on the result unmodified.

    This matters because with very many byes round one barely happens: the S M2
    main draw (33 players, 64 slots, 31 byes) plays exactly one real first-round
    match, so round two is the first round that actually decides anything and
    the round-one matchup rules have nothing to grade there.
    """
    round_two = {}
    for r in range(1, len(matches) // 2 + 1):
        round_two[r] = [
            _bye_advancer(matches.get(2 * r - 1, [])),
            _bye_advancer(matches.get(2 * r, [])),
        ]
    return round_two


def check_round_two_matchups(matches: Dict[int, List], bounds=None):
    """Grade the round-two pairings by the same rules as round one.

    open_questions.md: "Bei ganz vielen freilosen dritter gegen dritter, in der
    Runde danach bevorzugt aber dritter gegen erster/zweiter".

    Returns a dict keyed 'first_vs_first' / 'top_easy_opponent' /
    'bottom_vs_bottom' / 'country_first', each holding the violations the
    corresponding round-one checker reports for the virtual round-two dict.
    'first_vs_first' only holds the avoidable matches; the ones forced by more
    bye-advancing top placements than round-two matches (see
    :func:`forced_first_vs_first`) are under 'first_vs_first_forced'.

    *bounds* is the bracket's real ``(top, bottom)`` tier range and callers that
    know it MUST pass it.  Deriving it from the round-two view alone mis-tiers
    (a round two holding only winners and runners-up concludes bottom ==
    runner-up, which both switches off the three-tier guard and relabels a
    1-vs-2 as clean), and deriving it from a *partial* first round is no better:
    while the drawer is still in Phase 1 only the winners are placed, so the
    bracket reads as (top, top) and every tier-guarded rule silently switches
    off exactly where it is needed.  draw_bracket takes the range from its input
    class_subset instead.  Falling back to the first-round dict is correct only
    for a finished bracket, which is what a report-only caller has.

    Base conflicts are deliberately left out: base is the weakest round-one term
    and there is no rule asking for it a round ahead.
    """
    if bounds is None:
        bounds = _bracket_position_bounds(matches)
    round_two = derive_round_two_matches(matches)
    first_vs_first, first_vs_first_forced = [], []
    if bounds is not None:
        forced = forced_first_vs_first(_top_count(round_two, bounds[0]), len(round_two))
        first_vs_first, first_vs_first_forced = split_first_vs_first(
            check_no_first_vs_first(round_two, bounds=bounds), forced
        )
    return {
        "first_vs_first": first_vs_first,
        "first_vs_first_forced": first_vs_first_forced,
        "top_easy_opponent": check_top_easy_first_round(round_two, bounds=bounds),
        "bottom_vs_bottom": check_no_bottom_vs_bottom(round_two, bounds=bounds),
        "country_first": check_country_conflicts_first_round(round_two),
    }


def score_round_two(matches: Dict[int, List], weights: Dict[str, int] = None, bounds=None):
    """Return a weighted round-two matchup score; lower is better.

    Deliberately NOT folded into :func:`score_bracket` — see the note there.
    The drawer adds it to its own Phase 1/1b/1c objective, which is the only
    place the round-two pairing can still be changed.

    The three tier weights sit strictly BELOW every round-one matchup weight and
    strictly ABOVE every country weight: a round-one pairing is real and
    immediate, a round-two one only conditional, but a group winner drawn
    against a runner-up a round later still matters more than country spread
    ("1. gegen dritter oder freilos ist wichtiger als laenderverteilung", which
    is about the matchup itself, not about when it happens).  With the defaults
    that is the band 36..49 (bottom_vs_bottom 50, country_first 35); a config
    that moves either end is flagged by validate_bracket_weights.  The country
    term is instead ranked below round one's, between country_half and
    country_quarter.
    """
    if weights is None:
        weights = ROUND_TWO_DEFAULT_WEIGHTS

    violations = check_round_two_matchups(matches, bounds=bounds)
    score = 0
    for violation_key, weight_key in (
        ("first_vs_first", "round_two_first_vs_first"),
        ("top_easy_opponent", "round_two_top_easy_opponent"),
        ("bottom_vs_bottom", "round_two_bottom_vs_bottom"),
        ("country_first", "round_two_country_first"),
    ):
        score += len(violations[violation_key]) * weights.get(
            weight_key, ROUND_TWO_DEFAULT_WEIGHTS[weight_key]
        )
    return score


DEFAULT_BRACKET_WEIGHTS = {
    "quarter_split": 200,
    "half_split": 150,
    "first_vs_first": 100,
    "top_easy_opponent": 70,
    "bottom_vs_bottom": 50,
    "country_first": 35,
    "country_half": 10,
    "country_quarter": 4,
    "base_first": 20,
}


def score_bracket_tiers(
    matches: Dict[int, List], number_of_matches: int, weights: Dict[str, int] = None, bounds=None, top_count=None
):
    """Return the bracket score split into ``(hard, matchup, distribution)``.

    Compare the tuples, not their sum: a weighted sum is not a priority order
    (review finding H4).  One winner-vs-runner-up (70) used to lose to three
    same-country pairings (105), and three of them (210) outweighed one quarter
    separation (200).  As a tuple each tier outranks everything below it
    whatever the counts, and the weights only trade off terms WITHIN a tier:

    * hard -- half/quarter separation and first-vs-first ("darf eigentlich
      nicht verletzt werden").
    * matchup -- a group winner earned a bye or a lowest-placed opponent, and two
      lowest-placed players should not meet ("1. gegen dritter oder freilos ist
      wichtiger als laenderverteilung").
    * distribution -- same-country and same-base pairings and the country spread
      over the halves and quarters.

    *bounds* is the bracket's ``(top, bottom)`` tier range for the half check;
    it is only needed for a partial state.  *top_count* is how many top-tier
    participants the bracket holds in total, likewise only needed for a partial
    state: first-vs-first is charged only above what the bracket cannot avoid
    (:func:`forced_first_vs_first`).
    """
    if weights is None:
        weights = DEFAULT_BRACKET_WEIGHTS

    def w(key):
        return weights.get(key, DEFAULT_BRACKET_WEIGHTS[key])

    first_vs_first = check_no_first_vs_first(matches)
    if first_vs_first:
        if top_count is None:
            top_count = _top_count(matches, first_vs_first[0][1].group_pos)
        forced = forced_first_vs_first(top_count, number_of_matches)
        first_vs_first, _ = split_first_vs_first(first_vs_first, forced)
    hard = (
        len(check_quarter_group_separation(matches, number_of_matches)) * w("quarter_split")
        + len(check_half_group_separation(matches, number_of_matches, bounds=bounds)) * w("half_split")
        + len(first_vs_first) * w("first_vs_first")
    )
    matchup = (
        len(check_top_easy_first_round(matches)) * w("top_easy_opponent")
        + len(check_no_bottom_vs_bottom(matches)) * w("bottom_vs_bottom")
    )
    # country_balance entries are (country, c0, c1, violation_amount); both
    # spreads are scored by magnitude.  The quarter spread is deliberately
    # weighted below country_half so balancing the halves stays more important.
    country_half_magnitude = sum(v[3] for v in check_country_balance_halves(matches, number_of_matches))
    country_quarter_magnitude = sum(v[-1] for v in check_country_balance_quarters(matches, number_of_matches))
    distribution = (
        len(check_country_conflicts_first_round(matches)) * w("country_first")
        + country_half_magnitude * w("country_half")
        + country_quarter_magnitude * w("country_quarter")
        + len(check_base_conflicts_first_round(matches)) * w("base_first")
    )
    # Three checks are deliberately absent from the tiers, for one shared reason:
    # none of them can be improved by the phase-5 Monte Carlo, so each would be a
    # constant -- and any bracket that cannot satisfy it would then never reach
    # score 0, defeating the early exits in all four phase-5 quarter loops.  All
    # three are enforced where they still can be, by bracket_drawer's Phase
    # 1/1b/1c objective (and the bye balance also by the degrade fill, which is
    # the one later phase that moves byes), and reported via
    # get_bracket_violations so both viewers still surface them.
    #   * check_bye_balance_halves -- outside the degrade fill the byes are locked
    #     into place by Phase 1/1b.  bracket_drawer scores it directly in
    #     assignment_quality_cost, where they are still being placed.
    #   * check_round_two_matchups -- every bye recipient sits opposite a BYE and
    #     every remaining free slot's partner is free too, so from Phase 2 on a
    #     placement can only leave a round-two side UNdecided, never change a
    #     decided one.  score_round_two exists for the drawer to call directly.
    #   * check_placement_balance_quarters -- the phase-5 Monte Carlo only permutes
    #     players WITHIN one quarter, so it cannot move a tier count between
    #     quarters at all; the quarters are settled by Phase 1/1b (bye recipients,
    #     locked) and Phase 2's capacity buckets (not score-driven).
    return hard, matchup, distribution


def score_bracket(matches: Dict[int, List], number_of_matches: int, weights: Dict[str, int] = None, top_count=None):
    """Return a weighted score for the bracket; lower is better.

    The sum of :func:`score_bracket_tiers`.  It stays an integer because
    Phase 1/1b/1c add it as a tiebreaker to their own penalty ladder, and the
    snapshots and viewers show it.  The phase-5 Monte Carlo and the degrade fill
    compare the tiers instead.
    """
    return sum(score_bracket_tiers(matches, number_of_matches, weights, top_count=top_count))


def validate_bracket_weights(weights: Dict[str, int] = None, round_two_weights: Dict[str, int] = None):
    """Return a list of human-readable ordering problems in the weight ladders.

    Across tiers the order is fixed by score_bracket_tiers; these are the orders
    the weights themselves still decide:

    * within the matchup tier top_easy_opponent outranks bottom_vs_bottom, and
      within the distribution tier country_first > country_half > country_quarter;
    * the three round-two tier weights sit strictly below every round-one matchup
      weight and strictly above every country weight (see score_round_two);
    * the round-two country term sits between country_half and country_quarter.

    An empty list means the ladders are consistent.  Missing keys fall back to
    the defaults, like score_bracket and score_round_two do.
    """
    w = {**DEFAULT_BRACKET_WEIGHTS, **(weights or {})}
    r2 = {**ROUND_TWO_DEFAULT_WEIGHTS, **(round_two_weights or {})}
    problems = []

    if not w["top_easy_opponent"] > w["bottom_vs_bottom"]:
        problems.append(
            f"top_easy_opponent ({w['top_easy_opponent']}) must be above "
            f"bottom_vs_bottom ({w['bottom_vs_bottom']})"
        )
    if not w["country_first"] > w["country_half"] > w["country_quarter"]:
        problems.append(
            f"country weights must descend: country_first ({w['country_first']}) > "
            f"country_half ({w['country_half']}) > country_quarter ({w['country_quarter']})"
        )

    tier_keys = ("round_two_first_vs_first", "round_two_top_easy_opponent", "round_two_bottom_vs_bottom")
    round_one_floor = min(w["first_vs_first"], w["top_easy_opponent"], w["bottom_vs_bottom"])
    country_ceiling = max(w["country_first"], w["country_half"], w["country_quarter"])
    for key in tier_keys:
        if not country_ceiling < r2[key] < round_one_floor:
            problems.append(
                f"{key} ({r2[key]}) must lie strictly between the highest country weight "
                f"({country_ceiling}) and the lowest round-one matchup weight ({round_one_floor})"
            )
    if not w["country_half"] > r2["round_two_country_first"] > w["country_quarter"]:
        problems.append(
            f"round_two_country_first ({r2['round_two_country_first']}) must lie strictly between "
            f"country_quarter ({w['country_quarter']}) and country_half ({w['country_half']})"
        )
    return problems

