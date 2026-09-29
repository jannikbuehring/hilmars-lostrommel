"""Tests for misc/config.py: parsing config.ini into typed settings."""

import configparser

import pytest

from misc.config import ConfigError, Settings, parse_settings


def _parse(text):
    parser = configparser.ConfigParser()
    parser.read_string(text)
    return parse_settings(parser)


def test_missing_keys_keep_the_defaults():
    parsed, warnings = _parse("[files]\n[settings]\n[group_draw]\n[bracket_draw]\n")

    assert parsed == Settings()
    assert warnings == []


def test_values_are_parsed_to_their_types():
    parsed, warnings = _parse(
        """
[files]
players_path = data/players.csv
[settings]
log_level = 10
random_seed = 123456
[group_draw]
max_iterations = 500
[bracket_draw]
max_attempts = 100
country_half_weight = 11
round_two_country_first_weight = 10
"""
    )

    assert parsed.files.players_path == "data/players.csv"
    assert parsed.general.log_level == 10
    # Kept as text, so existing seeds reproduce the same draw.
    assert parsed.general.random_seed == "123456"
    assert parsed.group_draw.max_iterations == 500
    assert parsed.bracket_draw.max_attempts == 100
    assert parsed.bracket_draw.weights["country_half"] == 11
    assert parsed.bracket_draw.round_two_weights["round_two_country_first"] == 10
    assert warnings == []


def test_empty_value_keeps_the_default():
    parsed, _ = _parse("[settings]\nrandom_seed =\n[bracket_draw]\nmax_attempts =\n")

    assert parsed.general.random_seed == ""
    assert parsed.bracket_draw.max_attempts == Settings().bracket_draw.max_attempts


def test_misspelled_keys_and_sections_are_reported():
    parsed, warnings = _parse("[group_draw]\nmax_iteration = 5\n[bracket_draw]\ncountry_halve_weight = 3\n[extra]\n")

    assert parsed == Settings()
    assert warnings == [
        "Unknown config key [group_draw] max_iteration is ignored",
        "Unknown config key [bracket_draw] country_halve_weight is ignored",
        "Unknown config section [extra] is ignored",
    ]


def test_value_that_is_not_a_whole_number_is_an_error():
    with pytest.raises(ConfigError, match=r"\[bracket_draw\] half_split_weight must be a whole number, got '1000.0'"):
        _parse("[bracket_draw]\nhalf_split_weight = 1000.0\n")


def test_broken_weight_order_is_reported():
    _, warnings = _parse("[bracket_draw]\nbottom_vs_bottom_weight = 80\n")

    assert any(w.startswith("bracket_draw weights:") for w in warnings)


def test_template_parses_without_warnings():
    parser = configparser.ConfigParser()
    parser.read("config/config_template.ini")

    parsed, warnings = parse_settings(parser)

    assert parsed == Settings()
    assert warnings == []
