"""Ensures the repo root is importable as a package root (models, checks, draw, ...)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
