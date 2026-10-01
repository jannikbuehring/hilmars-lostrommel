"""Tests for hilmars_lostrommel.main's error handling (review finding Q12)."""

import logging

import pytest

import hilmars_lostrommel
from core.config import ConfigError


@pytest.fixture
def quiet_main(monkeypatch):
    monkeypatch.setattr(hilmars_lostrommel, "print_startup_info", lambda: None)
    monkeypatch.setattr(hilmars_lostrommel, "initialize_config", lambda base_dir, args: None)


def _run_main_failing_with(monkeypatch, error):
    def fail(results, export_html):
        raise error

    monkeypatch.setattr(hilmars_lostrommel, "initialize_data", fail)
    with pytest.raises(SystemExit) as exit_info:
        hilmars_lostrommel.main(["--no-menu"])
    assert exit_info.value.code == 1


def test_unexpected_error_logs_traceback(quiet_main, monkeypatch, caplog):
    with caplog.at_level(logging.ERROR):
        _run_main_failing_with(monkeypatch, RuntimeError("boom"))

    (record,) = caplog.records
    assert record.exc_info is not None
    assert "boom" in caplog.text
    assert "Traceback" in caplog.text


def test_config_error_logs_message_without_traceback(quiet_main, monkeypatch, caplog):
    with caplog.at_level(logging.ERROR):
        _run_main_failing_with(monkeypatch, ConfigError("[settings] random_seed must be a whole number, got 'x'"))

    (record,) = caplog.records
    assert record.exc_info is None
    assert "random_seed" in record.getMessage()
