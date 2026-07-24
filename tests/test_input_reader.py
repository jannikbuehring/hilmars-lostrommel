"""Tests for data_io/input_reader.py."""
from misc.config import config
from data_io.input_reader import read_draw_data

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
