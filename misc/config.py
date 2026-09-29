"""Typed application settings, parsed once from config/config.ini.

Every module reads the shared `settings` object (`from misc.config import settings`)
instead of the raw ini file. A key left out of config.ini keeps the default below
(the same values as config/config_template.ini). An unknown key logs a warning,
so a typo cannot silently fall back to the default; a value that is not a whole
number where one is expected stops the run with a ConfigError.
"""

import configparser
import logging
import os
import random
from dataclasses import dataclass, field, fields

from checks.bracket_checker import DEFAULT_BRACKET_WEIGHTS, ROUND_TWO_DEFAULT_WEIGHTS, validate_bracket_weights


class ConfigError(ValueError):
    """config.ini holds a value that cannot be used."""


@dataclass
class FileSettings:
    """[files]"""

    draw_data_path: str = "input/draw_input.csv"
    players_path: str = "input/players.csv"
    output_file_path: str = "output/output.csv"
    bracket_html_output_dir: str = "output/brackets"
    group_html_output_dir: str = "output/groups"


@dataclass
class GeneralSettings:
    """[settings]"""

    log_level: int = logging.INFO
    # Kept as text: random.seed("123") and random.seed(123) produce different
    # draws, and existing seeds must keep reproducing the same draw.
    random_seed: str = ""


@dataclass
class GroupDrawSettings:
    """[group_draw]"""

    max_iterations: int = 20000
    max_no_improvement_iterations: int = 5000
    max_escape_attempts: int = 20
    max_seed_retries: int = 5
    country_violation_weight: int = 1
    team_country_violation_weight: int = 1
    base_violation_weight: int = 1
    qttr_violation_weight: int = 1
    html_max_snapshots: int = 20000


@dataclass
class BracketDrawSettings:
    """[bracket_draw]; each weight is read from the key `<name>_weight`."""

    max_attempts: int = 2000
    joint_batch_max_evaluations: int = 5000
    weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_BRACKET_WEIGHTS))
    round_two_weights: dict[str, int] = field(default_factory=lambda: dict(ROUND_TWO_DEFAULT_WEIGHTS))


@dataclass
class Settings:
    files: FileSettings = field(default_factory=FileSettings)
    general: GeneralSettings = field(default_factory=GeneralSettings)
    group_draw: GroupDrawSettings = field(default_factory=GroupDrawSettings)
    bracket_draw: BracketDrawSettings = field(default_factory=BracketDrawSettings)


# ini section -> Settings attribute
_SECTIONS = {
    "files": "files",
    "settings": "general",
    "group_draw": "group_draw",
    "bracket_draw": "bracket_draw",
}

settings = Settings()


def _parse_int(section, key, raw):
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"[{section}] {key} must be a whole number, got {raw!r}") from None


def parse_settings(parser: configparser.ConfigParser) -> tuple[Settings, list[str]]:
    """Build Settings from a parsed ini file. Returns (settings, warnings).

    An empty value keeps the default, like a missing key.
    """
    parsed = Settings()
    warnings = []
    for section in parser.sections():
        if section not in _SECTIONS:
            warnings.append(f"Unknown config section [{section}] is ignored")
            continue
        target = getattr(parsed, _SECTIONS[section])
        simple_keys = {f.name for f in fields(target)} - {"weights", "round_two_weights"}
        for key, raw in parser.items(section, raw=True):
            raw = raw.strip()
            weight_name = key.removesuffix("_weight")
            if isinstance(target, BracketDrawSettings) and key.endswith("_weight"):
                weight_table = next(
                    (t for t in (target.weights, target.round_two_weights) if weight_name in t),
                    None,
                )
                if weight_table is None:
                    warnings.append(f"Unknown config key [{section}] {key} is ignored")
                elif raw:
                    weight_table[weight_name] = _parse_int(section, key, raw)
                continue
            if key not in simple_keys:
                warnings.append(f"Unknown config key [{section}] {key} is ignored")
                continue
            if not raw and key != "random_seed":
                continue
            default = getattr(target, key)
            setattr(target, key, _parse_int(section, key, raw) if isinstance(default, int) else raw)
    warnings.extend(
        f"bracket_draw weights: {problem}"
        for problem in validate_bracket_weights(parsed.bracket_draw.weights, parsed.bracket_draw.round_two_weights)
    )
    return parsed, warnings


def apply_settings(new_settings: Settings):
    """Replace the shared settings in place, so every `from misc.config import settings` sees them."""
    for f in fields(Settings):
        setattr(settings, f.name, getattr(new_settings, f.name))


def reset_settings():
    """Back to the code defaults (used by the tests)."""
    apply_settings(Settings())


def initialize_config(base_dir):
    """Load config/config.ini into `settings`, seed `random` and configure logging."""
    config_path = os.path.join(base_dir, "config", "config.ini")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    parser = configparser.ConfigParser()
    parser.read(config_path)
    parsed, warnings = parse_settings(parser)
    apply_settings(parsed)

    if settings.general.random_seed != "":
        random.seed(settings.general.random_seed)

    logging.basicConfig(
        level=settings.general.log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for warning in warnings:
        logging.warning(warning)
