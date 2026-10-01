"""The in-memory result of one run, shared by the pipeline and the menu."""

from dataclasses import dataclass, field

# (code in the draw input, label shown to the user)
COMPETITIONS = (("S", "Singles"), ("D", "Doubles"), ("M", "Mixed"))


@dataclass
class DrawResults:
    """Everything one run drew, keyed [competition][competition_class].

    groups[c][cls] holds `group`, `snapshots`, `draw_seconds` and, after
    validation, `violation_count`; brackets[c][cls] holds one section dict per
    `main`/`consolation` (see app.pipeline.draw_bracket_with_snapshot_fallback).
    `html_exported` is False when the run skipped the HTML export (--no-html),
    so the HTML pages on disk are not from this run.
    """

    groups: dict = field(default_factory=lambda: {code: {} for code, _ in COMPETITIONS})
    brackets: dict = field(default_factory=lambda: {code: {} for code, _ in COMPETITIONS})
    html_exported: bool = True
