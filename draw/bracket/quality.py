"""How good a finished draw_bracket result is, read from its last snapshot."""

from checks.bracket_checker import check_bye_seeding_order
from models.snapshot import Snapshot

# The rules a finished bracket must not break ("darf eigentlich nicht verletzt
# werden").  Every other key of state.bracket_violations is a quality goal.
HARD_BRACKET_RULES = ("half_group_separation", "quarter_group_separation", "first_vs_first")
# Pairings the rules would forbid but the bracket's shape makes unavoidable (more
# top placements than matches, see forced_first_vs_first).  Shown, never counted.
FORCED_BRACKET_RULES = ("first_vs_first_forced", "round2_first_vs_first_forced")
# "Freilose, Gruppenerste, Gruppenzweite und Gruppendritte gleichmaessig auf die
# Haelften verteilen": a rule, not a quality goal, but one the shape can make
# unavoidable, so it gets its own report status ("imbalanced") below the hard ones.
HALF_BALANCE_RULES = ("bye_balance_halves", "placement_balance_halves")


def _describe_half_balance(rule, violation):
    """One readable line for a HALF_BALANCE_RULES violation tuple."""
    if rule == "bye_balance_halves":
        count_half0, count_half1, _amount = violation
        return f"byes {count_half0}/{count_half1} over the halves"
    group_pos, (count_half0, count_half1), _amount = violation
    return f"pos {group_pos}: {count_half0}/{count_half1} over the halves"


def _describe_hard_violation(rule, violation):
    """One readable line for a HARD_BRACKET_RULES violation tuple."""
    if rule in ("first_vs_first", *FORCED_BRACKET_RULES):
        match_idx, a, b = violation

        def who(p):
            return f"#{p.start_number_a} (group {p.group_no}, pos {p.group_pos})"

        return f"match {match_idx}: {who(a)} vs {who(b)}"
    group_no, text = violation
    return f"group {group_no}: {text}"


def bracket_quality(snapshots: list[Snapshot]) -> dict:
    """Summarise a finished draw_bracket result for the operator.

    Every return path of draw_bracket appends a snapshot of exactly the state it
    returns as its LAST snapshot, so the final violations are read from there
    instead of being re-checked.  Returns
    {"degraded": bool, "hard": {rule: [description]}, "forced": {rule: [description]},
    "bye_order": [description], "balance": [description], "soft_count": int};
    "hard" and "forced" only carry rules that actually have entries, one readable
    line each.  "forced" pairings are unavoidable and so count neither as hard nor
    as soft violations.  "balance" lists byes or tiers split more than one apart
    over the halves (HALF_BALANCE_RULES); they are not in "soft_count" either.

    "degraded" means the draw took the quarter_capacity_degrade path AND its fill
    did not repair it: a hard violation is left, or byes were handed out of
    seeding order ("bye_order") to get rid of one.  A fill that ends clean is a
    regular bracket.
    """
    violations = (snapshots[-1].violations or {}) if snapshots else {}
    final_matches = (snapshots[-1].state or {}) if snapshots else {}
    hard = {
        rule: [_describe_hard_violation(rule, v) for v in violations[rule]]
        for rule in HARD_BRACKET_RULES
        if violations.get(rule)
    }
    forced = {
        rule: [_describe_hard_violation(rule, v) for v in violations[rule]]
        for rule in FORCED_BRACKET_RULES
        if violations.get(rule)
    }
    balance = [_describe_half_balance(rule, v) for rule in HALF_BALANCE_RULES for v in violations.get(rule) or []]
    soft_count = sum(
        len(value)
        for key, value in violations.items()
        if key not in HARD_BRACKET_RULES
        and key not in FORCED_BRACKET_RULES
        and key not in HALF_BALANCE_RULES
        and isinstance(value, list)
    )
    group_positions = [
        p.group_pos
        for participants in final_matches.values()
        for p in participants
        if p not in (None, "BYE") and p.group_pos is not None
    ]
    bye_order = [
        f"pos {group_pos}: #{without_bye.start_number_a} (seeding {without_bye.seeding}) has no bye, "
        f"#{with_bye.start_number_a} (seeding {with_bye.seeding}) has one"
        for group_pos, without_bye, with_bye in (
            check_bye_seeding_order(final_matches, min(group_positions)) if group_positions else []
        )
    ]
    degraded = took_degrade_path(snapshots) and bool(hard or bye_order)
    return {
        "degraded": degraded,
        "hard": hard,
        "forced": forced,
        "bye_order": bye_order,
        "balance": balance,
        "soft_count": soft_count,
    }


def took_degrade_path(snapshots):
    return any(s.action == "quarter_capacity_degrade" for s in snapshots)


def result_rank(snapshots):
    """Lower is better: hard violations, then byes out of seeding order, then
    halves out of balance, then whether the draw needed the degrade fill."""
    quality = bracket_quality(snapshots)
    return (
        sum(len(v) for v in quality["hard"].values()),
        len(quality["bye_order"]),
        len(quality["balance"]),
        took_degrade_path(snapshots),
    )
