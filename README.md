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

Group winners are placed first, then a rule engine plus genuine **backtracking** fills the remaining bye/quarter slots, keeping group winners/runners-up/etc. apart until later rounds and balancing seeding, country, and training-base conflicts. Details: [ARCHITECTURE.md § Algorithms](ARCHITECTURE.md#5-algorithms-draw).

# Configuration

Runtime behavior (file paths, log level, random seed, Monte Carlo tuning, bracket phase limits) is controlled by `config/config.ini`. Full key reference: [ARCHITECTURE.md § Configuration](ARCHITECTURE.md#8-configuration).

# Known issues

See [ARCHITECTURE.md § Known Issues](ARCHITECTURE.md#9-known-issues) for the current list of known bugs, dead code, and config mismatches.