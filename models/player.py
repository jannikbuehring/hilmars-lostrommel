"""Module defining the Player class and managing player instances."""

from dataclasses import dataclass

# for validation
players_list = []
players_by_start_number = {}


@dataclass(eq=False)
class Player:
    """A player with already-parsed fields (parsing lives in data_io.input_reader)."""

    start_number: int
    first_name: str
    last_name: str
    country: str
    base: str | None
    gender: str
    qttr: int | None

    def __post_init__(self):
        players_list.append(self)

    def __repr__(self):
        return f"[{self.start_number}] {self.first_name} {self.last_name} ({self.country}, {self.base if self.base is not None else 'No base'})"
