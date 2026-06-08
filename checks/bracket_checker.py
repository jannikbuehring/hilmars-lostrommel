"""Checks related to single-elimination bracket assignments."""
from collections import defaultdict
from typing import Dict, List
from models.player import players_by_start_number


def _match_half(match_index: int, number_of_matches: int) -> int:
    """Return 0 for first half, 1 for second half."""
    half = 0 if match_index <= (number_of_matches // 2) else 1
    return half


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


def check_no_first_vs_first(matches: Dict[int, List]):
    """Check that no first-place from groups meet each other in round one."""
    violations = []
    for match_idx, participants in matches.items():
        if len(participants) < 2:
            continue
        a, b = participants[0], participants[1]
        if a == "BYE" or b == "BYE":
            continue
        try:
            if a.group_pos == 1 and b.group_pos == 1:
                violations.append((match_idx, a, b))
        except Exception:
            continue
    return violations


def check_country_balance_halves(matches: Dict[int, List], number_of_matches: int):
    """Compute country counts per half and flag large imbalances.
    Returns list of (country, count_half0, count_half1)
    """
    counts = defaultdict(lambda: [0, 0])
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
            if p.start_number_b is not None:
                b = players_by_start_number[p.start_number_b]
                counts[b.country][half] += 1

    violations = []
    for country, (c0, c1) in counts.items():
        if abs(c0 - c1) > 1:
            violations.append((country, c0, c1))
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
        weights = {"half_split": 50, "first_vs_first": 100, "country_half": 10, "base_first": 20}

    score = 0
    score += len(check_half_group_separation(matches, number_of_matches)) * weights.get("half_split", 50)
    score += len(check_no_first_vs_first(matches)) * weights.get("first_vs_first", 100)
    score += len(check_country_balance_halves(matches, number_of_matches)) * weights.get("country_half", 10)
    score += len(check_base_conflicts_first_round(matches)) * weights.get("base_first", 20)
    return score
