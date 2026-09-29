"""Ensures the repo root is importable as a package root (models, checks, draw, ...)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: full-size draws that take seconds each; skip with -m 'not slow'",
    )
