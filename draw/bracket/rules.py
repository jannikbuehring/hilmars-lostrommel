"""Where a participant may go, given where its group's winner (the anchor) landed."""

from typing import TYPE_CHECKING

from models.bracket_geometry import allowed_quarters

if TYPE_CHECKING:
    from draw.bracket.context import BracketContext


def required_half(ctx: BracketContext, participant, top_half_map):
    """The half the separation rules force *participant* into, or None if free.

    *top_half_map* is group_no -> half of that group's winner.  The 2nd/3rd
    (delta 1/2) go to the opposite half, the 4th (delta 3) to the same one.
    """
    group_no = getattr(participant, "group_no", None)
    group_pos = getattr(participant, "group_pos", None)
    if group_no is None or group_pos is None:
        return None
    if group_no not in top_half_map:
        return None
    delta = group_pos - ctx.top_group_pos
    anchor_half = top_half_map[group_no]
    if delta in (1, 2):
        return 1 - anchor_half
    if delta == 3:
        return anchor_half
    return None


def allowed_for(ctx: BracketContext, group_top_quarter, participant, sibling_quarter=None):
    """allowed_quarters for *participant*, anchored on its group's top quarter.

    The one rule Phase 1b, 1c and 2 all place by; *sibling_quarter* is where the
    group's other 2nd/3rd already sits, if anywhere.
    """
    group_pos = getattr(participant, "group_pos", None)
    delta = group_pos - ctx.top_group_pos if group_pos is not None else None
    anchor = group_top_quarter.get(getattr(participant, "group_no", None))
    return allowed_quarters(delta, anchor, ctx.geo, sibling_quarter)
