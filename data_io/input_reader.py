from core.config import settings
from models.draw_data import DrawDataRow
from models.player import Player


def _parse_bool(value: str) -> bool:
    """Parse a CSV boolean flag ('1' = True, anything else = False)."""
    return value.strip() == "1"


def _parse_optional_int(value: str) -> int | None:
    """Parse an optional integer field ('' = None)."""
    return int(value) if value != "" else None


def read_draw_data() -> list[DrawDataRow]:
    """Read draw data from the specified CSV file and return a list of DrawDataRow objects."""
    draw_data_file_path = settings.files.draw_data_path
    with open(draw_data_file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        draw_data = []
        for line in lines[1:]:
            (
                competition,
                competition_class,
                amount_of_groups,
                seeding,
                group_no,
                group_pos,
                main_round,
                consolation_round,
                start_number_a,
                start_number_b,
            ) = [field.strip() for field in line.strip().split(";")]
            draw_data.append(
                DrawDataRow(
                    competition=competition,
                    competition_class=competition_class,
                    seeding=_parse_optional_int(seeding),
                    amount_of_groups=_parse_optional_int(amount_of_groups),
                    group_no=_parse_optional_int(group_no),
                    group_pos=_parse_optional_int(group_pos),
                    main_round=_parse_bool(main_round),
                    consolation_round=_parse_bool(consolation_round),
                    start_number_a=int(start_number_a),
                    start_number_b=_parse_optional_int(start_number_b),
                )
            )
        return draw_data


def read_players() -> list[Player]:
    """Read player data from the specified CSV file and return a list of Player objects."""
    player_file_path = settings.files.players_path
    with open(player_file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        players = []
        for line in lines[1:]:
            start_number, last_name, first_name, country, base, gender, qttr = [
                field.strip() for field in line.strip().split(";")
            ]
            players.append(
                Player(
                    start_number=int(start_number),
                    first_name=first_name,
                    last_name=last_name,
                    country=country,
                    base=base if base != "" else None,
                    gender=gender,
                    qttr=_parse_optional_int(qttr),
                )
            )
        return players
