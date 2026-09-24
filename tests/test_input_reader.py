"""Tests for data_io/input_reader.py."""
from misc.config import config
from data_io.input_reader import read_draw_data, read_players

HEADER = "S_D_M;class;#groups;seeding;group_no;group_pos;for_main_round;for_consolation;startnumber_A;startnumber_B\n"


def test_read_draw_data_parses_main_and_consolation_round_flags(tmp_path):
    csv_file = tmp_path / "draw_input.csv"
    csv_file.write_text(
        HEADER
        + "S;M1;1;1000;1;1;1;;1001;\n"
        + "S;M1;1;999;1;2;;1;1002;\n"
        + "S;M1;1;998;1;3;0;0;1003;\n",
        encoding="utf-8",
    )

    if not config.has_section("files"):
        config.add_section("files")
    original_path = config["files"].get("draw_data_path")
    config["files"]["draw_data_path"] = str(csv_file)
    try:
        draw_data = read_draw_data()
    finally:
        if original_path is None:
            config.remove_option("files", "draw_data_path")
        else:
            config["files"]["draw_data_path"] = original_path

    assert [(row.main_round, row.consolation_round) for row in draw_data] == [
        (True, False),
        (False, True),
        (False, False),
    ]


def _read_with_config_path(key, csv_file, reader):
    if not config.has_section("files"):
        config.add_section("files")
    original_path = config["files"].get(key)
    config["files"][key] = str(csv_file)
    try:
        return reader()
    finally:
        if original_path is None:
            config.remove_option("files", key)
        else:
            config["files"][key] = original_path


def test_read_draw_data_strips_whitespace_around_fields(tmp_path):
    csv_file = tmp_path / "draw_input.csv"
    csv_file.write_text(HEADER + "S ; M1 ;1; 1000 ; 1 ; 2 ; 1 ;; 1001 ; \n", encoding="utf-8")

    row = _read_with_config_path("draw_data_path", csv_file, read_draw_data)[0]

    assert (row.competition, row.competition_class) == ("S", "M1")
    assert (row.seeding, row.group_no, row.group_pos) == (1000, 1, 2)
    assert row.start_number_a == 1001
    assert row.start_number_b is None


def test_read_players_strips_whitespace_around_fields(tmp_path):
    csv_file = tmp_path / "players.csv"
    csv_file.write_text(
        "Startnumber;Last_name;First_name;Country;PPP_chapter;Gender;QTTR\n"
        + " 1001 ; Wang ; Chuqin ;GER ; Base ; F; 2796 \n",
        encoding="utf-8",
    )

    player = _read_with_config_path("players_path", csv_file, read_players)[0]

    assert player.start_number == 1001
    assert (player.last_name, player.first_name) == ("Wang", "Chuqin")
    assert (player.country, player.base, player.gender, player.qttr) == ("GER", "Base", "F", 2796)
