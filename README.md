# hilmars-lostrommel

A CLI tool for creating (table tennis) group draws and knock-out brackets (main + consolation), for singles, doubles, and mixed competitions.

For the full technical breakdown (data flow, algorithms, data model, config keys, known bugs), see [ARCHITECTURE.md](ARCHITECTURE.md) — this README is a quick-start/overview only.

# How to use

Prerequisites (place in `input/`):

- `players.csv` — all players
- `draw_input.csv` — competition entries per player/team, referencing players by start number

Run `python hilmars_lostrommel.py` (or the pre-built executable in `builds/`), then use the interactive menu to browse Players / Groups / Bracket results.

Before drawing, validity checks run against the input data:
- No player has the same start number twice
- Every player referenced in the draw data exists
- Every imported player is entered in at least one competition
- Players only compete in matching-gender competitions

# Group draw

Highest seeds are spread one-per-group first, then a **Monte Carlo / simulated-annealing-style local search** (random swaps, escape-from-local-minimum, multi-seed restarts) optimizes the remaining placements to minimize country-distribution, shared-training-base, and QTTR-rating imbalances. Details: [ARCHITECTURE.md § Algorithms](ARCHITECTURE.md#5-algorithms-draw).

# Bracket draw

Group winners are placed first; when byes outnumber the winners the remaining byes are then distributed with the same balanced placer, and a rule engine plus Monte-Carlo refinement fills the rest — keeping group winners/runners-up/etc. apart until later rounds and balancing seeding, country, and training-base conflicts. Structurally over-tight brackets degrade to a best-effort layout instead of failing. Details: [ARCHITECTURE.md § Algorithms](ARCHITECTURE.md#5-algorithms-draw).

# Bracket viewer

Every bracket (all singles/doubles/mixed classes, main and consolation) is **exported to a self-contained HTML file** automatically at startup, into `output/brackets/`. From the Bracket menu, brackets can be viewed in the terminal, or **"View HTML"** opens the pre-exported file in the browser — an SVG bracket tree with an in-browser stepper through every draw snapshot, useful for verifying the draw logic on large brackets without terminal scroll/cutoff. Details: [ARCHITECTURE.md § Viewer / CLI UX](ARCHITECTURE.md#7-viewer--cli-ux-viewer-miscmenupy).

# Configuration

Runtime behavior (file paths, log level, random seed, Monte Carlo tuning, bracket phase limits) is controlled by `config/config.ini`. Full key reference: [ARCHITECTURE.md § Configuration](ARCHITECTURE.md#8-configuration).

# Known issues

See [ARCHITECTURE.md § Known Issues](ARCHITECTURE.md#9-known-issues) for the current list of known bugs, dead code, and config mismatches.