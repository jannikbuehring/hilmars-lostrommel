"""Tests for misc/initializer.py's failure path (review finding H3)."""
import pytest

import misc.initializer as initializer
from misc.config import config


@pytest.fixture
def output_config(tmp_path):
    """Point every output path at tmp_path; initialize_config never runs under pytest."""
    out = tmp_path / "output"
    config["files"] = {
        "output_file_path": str(out / "output.csv"),
        "bracket_html_output_dir": str(out / "brackets"),
        "group_html_output_dir": str(out / "groups"),
    }
    yield out
    config.remove_section("files")


def test_failed_run_returns_false_and_leaves_no_stale_output(output_config, monkeypatch):
    out = output_config
    (out / "brackets").mkdir(parents=True)
    (out / "output.csv").write_text("previous run")
    (out / "brackets" / "S_M1_main_bracket.html").write_text("previous run")

    def missing():
        raise FileNotFoundError("players.csv")

    monkeypatch.setattr(initializer, "read_players", missing)

    assert initializer.initialize_data() is False

    # Nothing from the previous run is left where it would look current.
    assert not (out / "output.csv").exists()
    assert not (out / "brackets" / "S_M1_main_bracket.html").exists()
    assert (out / "previous" / "output.csv").read_text() == "previous run"
    assert (out / "previous" / "brackets" / "S_M1_main_bracket.html").exists()


def test_locked_previous_output_aborts_before_reading_input(output_config, monkeypatch):
    out = output_config
    out.mkdir(parents=True)
    (out / "output.csv").write_text("open in Excel")

    def locked(src, dst):
        raise PermissionError(13, "Permission denied", src)

    def must_not_run():
        raise AssertionError("the run must stop before reading input")

    monkeypatch.setattr("data_io.output_writer.os.replace", locked)
    monkeypatch.setattr(initializer, "read_players", must_not_run)

    assert initializer.initialize_data() is False
    assert (out / "output.csv").read_text() == "open in Excel"
