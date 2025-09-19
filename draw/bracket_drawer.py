import math
import random
from models.player import Player
from models.player import players_by_start_number
from models.draw_data import DrawDataRow
from models.match import Match
from viewer.bracket_viewer import show_bracket_table
import logging

class BracketDrawer:
    def draw_bracket(self, class_subset: list["DrawDataRow"]):
        """
        Build a single-elimination bracket from seeded participants.
        class_subset: players advancing from groups
        players_by_start_number: dict[start_number] -> player object with .country and .base
        """

        # 1. Sort: prioritize group_pos (1st before 2nd), then seeding
        class_subset.sort(key=lambda p: (p.group_pos, -p.seeding))

        num_participants = len(class_subset)

        # 2. Find nearest power of 2 for bracket size
        bracket_size = 1 << (num_participants - 1).bit_length()
        byes = bracket_size - num_participants
        logging.debug(f"Bracket size: {bracket_size}, participants: {num_participants}, byes: {byes}")

        # 3. Create slots
        slots = [None] * bracket_size

        # 4. Place strongest seeds (split top 2 into different halves)
        slots[0] = class_subset[0]   # strongest seed at top-left
        if num_participants > 1:
            slots[bracket_size // 2] = class_subset[1]  # 2nd seed at bottom-left

        # 5. Place remaining players
        remaining = class_subset[2:]

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

        available_slots = [i for i in range(bracket_size) if slots[i] is None]

        for participant in remaining:
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