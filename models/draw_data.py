"""Data structures for draw data input."""

from dataclasses import dataclass

from models.player import players_by_start_number

# "A" or "A/B" -> seeding; filled by data_io.input_reader.read_draw_data, read by the bracket drawer.
seeding_by_start_numbers: dict[str, int] = {}


@dataclass(eq=False)
class DrawDataRow:
    """A row in the draw data input with already-parsed fields (parsing lives in data_io.input_reader)."""

    competition: str
    competition_class: str
    seeding: int | None
    amount_of_groups: int | None
    group_no: int | None
    group_pos: int | None
    main_round: bool
    consolation_round: bool
    start_number_a: int
    start_number_b: int | None

    def __repr__(self):
        return f"{self.competition} {self.competition_class} (Seeding: {self.seeding}, Player A: {self.start_number_a}, {players_by_start_number[self.start_number_a].country}. Player B: {self.start_number_b}, {players_by_start_number[self.start_number_b].country if self.start_number_b is not None else ''})"
