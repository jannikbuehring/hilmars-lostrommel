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
            "country_half": 10,
            "base_first": 20,
        }

    score = 0
    score += len(check_quarter_group_separation(matches, number_of_matches)) * weights.get("quarter_split", 200)
    score += len(check_half_group_separation(matches, number_of_matches)) * weights.get("half_split", 150)
    score += len(check_no_first_vs_first(matches)) * weights.get("first_vs_first", 100)
    country_violations = check_country_balance_halves(matches, number_of_matches)
    # country_violations entries are (country, c0, c1, violation_amount)
    country_violation_magnitude = sum(v[3] for v in country_violations) if country_violations else 0
    score += country_violation_magnitude * weights.get("country_half", 10)
    score += len(check_base_conflicts_first_round(matches)) * weights.get("base_first", 20)
    return score
