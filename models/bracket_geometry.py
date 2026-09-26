"""Bracket geometry and the group-separation quarter rule, shared by drawer and checker.

This is the single source for "which half/quarter is this slot or match in" and
for "which quarters may a group member occupy, given where its winner sits".
The drawer's phases (1b bye distribution, 1c repair, 2 quarter assignment) and
the checker's quarter separation all derive their verdicts from here, so they
cannot drift apart.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class BracketGeometry:
    """Half/quarter layout of a first round with *number_of_matches* matches.

    At most 4 quarters, at least 2; each half holds quarters_per_half of them.
    A bracket with 2 first-round matches has only 2 quarters (one per half).
    """
    number_of_matches: int

    @property
    def bracket_size(self) -> int:
        return 2 * self.number_of_matches

    @property
    def num_quarters(self) -> int:
        return min(4, max(2, self.number_of_matches))

    @property
    def quarters_per_half(self) -> int:
        return max(1, self.num_quarters // 2)

    def match_quarter(self, match_index: int) -> int:
        """Return 0-3 for the quarter of a first-round match (1-based index)."""
        matches_per_quarter = max(1, self.number_of_matches // 4)
        return min(3, (match_index - 1) // matches_per_quarter)

    def quarter_half(self, quarter: int) -> int:
        """Return 0 for first half, 1 for second half."""
        return quarter // self.quarters_per_half

    def match_half(self, match_index: int) -> int:
        """Half of a match, derived from its quarter so the two never disagree."""
        return self.quarter_half(self.match_quarter(match_index))

    def half_quarters(self, half: int) -> List[int]:
        return [half * self.quarters_per_half + i for i in range(self.quarters_per_half)]

    @staticmethod
    def slot_to_match(slot: int) -> Tuple[int, int]:
        """Return (match index, side 0/1) for a 1-based slot."""
        return ((slot + 1) // 2, 0 if slot % 2 == 1 else 1)

    def slot_quarter(self, slot: int) -> int:
        return self.match_quarter(self.slot_to_match(slot)[0])

    def slot_half(self, slot: int) -> int:
        return self.match_half(self.slot_to_match(slot)[0])


def allowed_quarters(
    delta: Optional[int],
    anchor_quarter: Optional[int],
    geometry: BracketGeometry,
    sibling_quarter: Optional[int] = None,
) -> List[int]:
    """Quarters a group member may occupy, relative to its group winner's quarter.

    *delta* is the member's group_pos minus the bracket's top position, and
    *anchor_quarter* the quarter its group's top-placed member landed in.

    - delta 1/2 (2nd/3rd): the opposite half's quarters.  2nd and 3rd must use
      different quarters, so *sibling_quarter* -- the quarter of whichever of the
      two was placed first -- is excluded, unless that leaves nothing (a half with
      a single quarter: the half rule wins).
    - delta 3 (4th): the winner's own half, minus the winner's quarter unless that
      leaves nothing.
    - anything else, or no anchor yet: every quarter.
    """
    every_quarter = list(range(geometry.num_quarters))
    if delta is None or anchor_quarter is None:
        return every_quarter
    anchor_half = geometry.quarter_half(anchor_quarter)
    if delta in (1, 2):
        opposite = geometry.half_quarters(1 - anchor_half)
        return [q for q in opposite if q != sibling_quarter] or opposite
    if delta == 3:
        same = geometry.half_quarters(anchor_half)
        return [q for q in same if q != anchor_quarter] or same
    return every_quarter
