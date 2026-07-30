"""Checks related to single-elimination bracket assignments."""
from collections import defaultdict
from typing import Dict, List
from models.player import players_by_start_number


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


def check_half_group_separation(matches: Dict[int, List], number_of_matches: int):
    """
    Ensure that for each group the 1st/4th positions are placed in one half
    and 2nd/3rd in the other half. Returns list of violations as tuples:
      (group_no, details)
    """
    violations = []

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
            h = _match_half(match_idx, number_of_matches)
            if pos in (1, 4):
                group_pos_halves[group_no]["14"].add(h)
            if pos in (2, 3):
                group_pos_halves[group_no]["23"].add(h)

    for group_no, halves in group_pos_halves.items():
        h14 = halves["14"]
        h23 = halves["23"]
        # If any of the sets spans both halves -> violation
        if len(h14) > 1:
            violations.append((group_no, "positions 1/4 split across halves"))
        if len(h23) > 1:
            violations.append((group_no, "positions 2/3 split across halves"))
        # They must be in different halves
        if h14 & h23:
            violations.append((group_no, "positions 1/4 and 2/3 share a half"))

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


def check_no_first_vs_first(matches: Dict[int, List]):
    """Check that no bracket-highest placements meet each other in round one."""
    violations = []

    # Determine the top placement present in this bracket.
    # In the main bracket this will normally be 1, but in consolation it may be 2 or higher.
    group_positions = []
    for participants in matches.values():
        for p in participants:
            if p == "BYE" or p is None:
                continue
            if getattr(p, "group_pos", None) is not None:
                group_positions.append(p.group_pos)
    if not group_positions:
        return violations

    bracket_top_position = min(group_positions)

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


def check_top_easy_first_round(matches: Dict[int, List]):
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
    """
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


def check_no_bottom_vs_bottom(matches: Dict[int, List]):
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
    """
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


def score_bracket(matches: Dict[int, List], number_of_matches: int, weights: Dict[str, int] = None):
    """Return a weighted score for the bracket; lower is better."""
    if weights is None:
        weights = {
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

    score = 0
    score += len(check_quarter_group_separation(matches, number_of_matches)) * weights.get("quarter_split", 200)
    score += len(check_half_group_separation(matches, number_of_matches)) * weights.get("half_split", 150)
    score += len(check_no_first_vs_first(matches)) * weights.get("first_vs_first", 100)
    # Round-one matchup quality, all three deliberately ranked ABOVE the country
    # weights below ("1. gegen dritter oder freilos ist wichtiger als
    # länderverteilung") and below the structural separation weights above.  Keep
    # 2 * top_easy_opponent under min(half_split, quarter_split) so the soft
    # degrade path in _fill_residual_soft can never trade away a separation.
    score += len(check_top_easy_first_round(matches)) * weights.get("top_easy_opponent", 70)
    score += len(check_no_bottom_vs_bottom(matches)) * weights.get("bottom_vs_bottom", 50)
    score += len(check_country_conflicts_first_round(matches)) * weights.get("country_first", 35)
    country_violations = check_country_balance_halves(matches, number_of_matches)
    # country_violations entries are (country, c0, c1, violation_amount)
    country_violation_magnitude = sum(v[3] for v in country_violations) if country_violations else 0
    score += country_violation_magnitude * weights.get("country_half", 10)
    # Quarter-level country spread, deliberately weighted below country_half so
    # balancing the halves stays the more important objective.
    quarter_country_violations = check_country_balance_quarters(matches, number_of_matches)
    quarter_country_magnitude = sum(v[-1] for v in quarter_country_violations)
    score += quarter_country_magnitude * weights.get("country_quarter", 4)
    score += len(check_base_conflicts_first_round(matches)) * weights.get("base_first", 20)
    return score
