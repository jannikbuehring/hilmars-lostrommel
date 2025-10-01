"""Module for configuration management."""
import configparser
import random
import os
import logging

config = configparser.ConfigParser()

def initialize_config(base_dir):
    """Initialize configuration settings from config.ini file."""
    global mode

    config_dir = os.path.join(base_dir, "config")
    config_path = os.path.join(config_dir, "config.ini")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    config.read(config_path)

    log_level = config["settings"]["log_level"]
    random_seed = config["settings"]["random_seed"]

    if random_seed != '':
        random.seed(random_seed)

    # Basic configuration
    logging.basicConfig(
        level=int(log_level),                                   # minimum level to log
        format="%(asctime)s [%(levelname)s] %(message)s",       # log format
        datefmt="%Y-%m-%d %H:%M:%S"                             # timestamp format
    )
