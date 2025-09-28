import math
import random
from typing import List, Optional
from models.player import Player
from models.player import players_by_start_number
from models.draw_data import DrawDataRow
from models.match import Match
from viewer.bracket_viewer import show_bracket_table
import logging

from models.draw_data import seeding_by_start_numbers

class BracketDrawer:
    def draw_bracket(self, class_subset: list["DrawDataRow"]):
        """
        Build a single-elimination bracket from seeded participants.
        class_subset: players advancing from groups
        """

        def can_place(participant, slot_index):
            """Check country/base conflict against the paired slot."""
            pair_index = slot_index - 1 if slot_index % 2 else slot_index + 1
            opponent = slots[pair_index] if 0 <= pair_index < len(slots) else None
            if not opponent or opponent == "BYE":
                return True

            # Player vs Player conflicts
            opp_a = players_by_start_number[opponent.start_number_a]
            pl_a = players_by_start_number[participant.start_number_a]
            if opp_a.country == pl_a.country:
                return False
            if opp_a.base == pl_a.base:
                return False

            # Team logic (if start_number_b is set)
            if hasattr(participant, "start_number_b") and participant.start_number_b:
                pl_b = players_by_start_number[participant.start_number_b]
                if hasattr(opponent, "start_number_b") and opponent.start_number_b:
                    opp_b = players_by_start_number[opponent.start_number_b]
                    if (opp_a.country == pl_a.country and opp_b.country == pl_b.country):
                        return False
                    if (opp_a.base == pl_a.base and opp_b.base == pl_b.base):
                        return False
            return True

        def bye_hierarchy(num_matches: int) -> List[List[int]]:
            """Return hierarchical subdivisions for bye placement.
            Example for num_matches=16:
                [[1], [16], [8,9], [4,5,12,13], [2,3,6,7,10,11,14,15]]
            """
            if num_matches < 2 or (num_matches & (num_matches - 1)) != 0:
                raise ValueError("num_matches must be a power of two >= 2")

            levels = int(math.log2(num_matches))
            groups: List[List[int]] = [[1], [num_matches]]

            # For each level L produce all seam pairs (boundary, boundary+1)
            # using block = num_matches // (2**L) and taking i odd only.
            for L in range(1, levels):
                block = num_matches // (2 ** L)
                group: List[int] = []
                # i goes 1..(2**L - 1); pick odd i to avoid duplicating seams from higher levels
                for i in range(1, 2 ** L):
                    if i % 2 == 1:
                        boundary = i * block
                        group.append(boundary)
                        group.append(boundary + 1)
                groups.append(group)

            return groups

        def generate_bye_order(num_matches: int) -> List[int]:
            """Flatten the hierarchy into the deterministic full order."""
            groups = bye_hierarchy(num_matches)
            order: List[int] = []
            for g in groups:
                order.extend(g)
            return order

        def pick_byes(num_matches: int, num_byes: int, seed: Optional[int] = None) -> List[int]:
            """Pick num_byes match indices following the hierarchy:
            - take entire groups while possible
            - if a group is larger than remaining byes, select randomly only within that group
            """
            if num_byes < 0:
                raise ValueError("num_byes must be >= 0")
            if num_byes == 0:
                return []

            full_groups = bye_hierarchy(num_matches)
            rng = random.Random(seed)
            result: List[int] = []

            for g in full_groups:
                remaining = num_byes - len(result)
                if remaining <= 0:
                    break
                if remaining >= len(g):
                    # take whole group (preserve the group's left-to-right order)
                    result.extend(g)
                else:
                    # choose exactly `remaining` items from this group at random,
                    # then append them in the group's natural (ascending) order
                    chosen = rng.sample(g, remaining)
                    chosen_sorted = sorted(chosen)   # group elements are ascending already
                    result.extend(chosen_sorted)
                    break

            return result

        for entry in class_subset:
            key = str(entry.start_number_a)
            if entry.start_number_b is not None:
                key += "/" + str(entry.start_number_b)
            entry.seeding = seeding_by_start_numbers[key]

        # 1. Sort: prioritize group_pos (1st before 2nd), then seeding
        class_subset.sort(key=lambda p: (p.group_pos, -p.seeding))

        num_participants = len(class_subset)

        # 2. Find nearest power of 2 for bracket size
        bracket_size = 1 << (num_participants - 1).bit_length()
        number_of_matches = bracket_size // 2
        byes = bracket_size - num_participants
        logging.debug(f"Bracket size: {bracket_size}, participants: {num_participants}, byes: {byes}")

        # 3. Create matches
        matches = {index: [] for index in range(1, number_of_matches + 1) }
        bye_slots = pick_byes(number_of_matches, byes)


        # 4. Slot in Byes
        for bye_slot in bye_slots:
            matches[bye_slot].append("BYE")


        for participant in class_subset:
            placed = False
            random.shuffle(available_slots)  # shuffle to add variety
            for idx in available_slots:
                if can_place(participant, idx):
                    slots[idx] = participant
                    available_slots.remove(idx)
                    placed = True
                    break

            if not placed:  # fallback if conflicts unavoidable
                idx = available_slots.pop()
                slots[idx] = participant
                logging.debug(f"Forced {participant} into slot {idx} despite conflict")

        # 6. Fill byes if needed
        for i in available_slots:
            if byes > 0:
                slots[i] = "BYE"
                byes -= 1

        # 7. Build first-round matches
        matches = []
        for i in range(0, len(slots), 2):
            p1 = slots[i]
            p2 = slots[i + 1] if i + 1 < len(slots) else None  # safe access
            matches.append(Match(p1, p2))

        # 8. Build following rounds by linking winners
        round_matches = matches
        while len(round_matches) > 1:
            next_round = []
            for i in range(0, len(round_matches), 2):
                match = Match()
                round_matches[i].next_match = match
                round_matches[i + 1].next_match = match
                next_round.append(match)
            round_matches = next_round

        show_bracket_table(matches)
        return matches  # entry point = list of first round matches