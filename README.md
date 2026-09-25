# hilmars-lostrommel

A CLI tool for creating (table tennis) group draws and knock-out brackets (main + consolation), for singles, doubles, and mixed competitions.

For the full technical breakdown (data flow, algorithms, data model, config keys, known bugs), see [ARCHITECTURE.md](ARCHITECTURE.md) — this README is a quick-start/overview only.

# How to use

Prerequisites (place in `input/`):

- `players.csv` — all players
- `draw_input.csv` — competition entries per player/team, referencing players by start number

Run `python hilmars_lostrommel.py` (or the pre-built executable in `builds/`), then use the interactive menu to browse Players / Groups / Bracket results.

Surrounding whitespace is trimmed from every input field (so `"GER "` is read as `GER`). Before drawing, validity checks run against the input data. Every check aborts the run, except the "entered in at least one competition" check, which only warns:
- No player has the same start number twice
- Every player referenced in the draw data exists
- Every imported player is entered in at least one competition (warning only)
- Players only compete in matching-gender competitions
- A row with a group result (`group_pos`) is flagged for exactly one of main round / consolation; a group-stage row is flagged for neither
- `group_no` and `group_pos` are either both set or both blank
- No player appears twice in the same class and stage (neither as a single entry nor across two teams)
- No `group_pos` occurs twice in the same group
- Doubles and mixed entries have a partner, singles entries don't, and nobody is paired with themselves
- Every mixed pair is one man and one woman
- All group-stage rows of a class give the same, non-empty `#groups`
- Every group-stage row has a seeding
- A class has at least as many group-stage entries as `#groups` (so no group is empty)

# Group draw

Highest seeds are spread one-per-group first, then a **Monte Carlo / simulated-annealing-style local search** (random swaps, escape-from-local-minimum, multi-seed restarts) optimizes the remaining placements to minimize country-distribution, shared-training-base, and QTTR-rating imbalances. If the group draw of one class fails, that class is reported as a warning and left out, and the other classes are still drawn and exported. Details: [ARCHITECTURE.md § Algorithms](ARCHITECTURE.md#5-algorithms-draw).

# Bracket draw

Group winners are placed first, each seeding batch assigned as a whole rather than player by player; when byes outnumber the winners the remaining byes continue down the same seeded-slot hierarchy, a repair pass then swaps them around to fix anything no single batch could see, and a rule engine plus Monte-Carlo refinement fills the rest — keeping group winners/runners-up/etc. apart until later rounds, spreading the byes evenly over the two halves and each placement tier evenly over the two quarters of its half, and balancing seeding, training-base conflicts, and country distribution across both the halves and (less strongly) the quarters. Round-one matchups are also graded on their own: a group winner has earned a **bye or a lowest-placed opponent**, two lowest-placed players should not be wasted on each other, and same-country and same-base pairings are avoided — in that priority order, all of them ranked above the country distribution. When byes dominate, **round two is graded by the same rules** (more weakly than round one), because a draw where nearly every first-round match is a walkover only really begins in round two. Structurally over-tight brackets degrade to a best-effort layout instead of failing; that layout is found by a local search that still ranks the separation rules above everything else. Details: [ARCHITECTURE.md § Algorithms](ARCHITECTURE.md#5-algorithms-draw).

# Output

Every run writes `output/output.csv` — one semicolon-delimited file covering all competitions, with one row per group member and one row per **bracket slot** (`draw_number` is the Rasterzahl of the KO field, `1..bracket_size`). The `_A`/`_B` columns are the two players of a doubles/mixed pair, not the two sides of a match. Column reference: `output/output_explainer.md` (German) and [ARCHITECTURE.md § Input/output formats](ARCHITECTURE.md#4-inputoutput-formats-data_io).

Next to it, every run writes a **draw report** (`output/<output name>_report.csv`) with one row per group class and per bracket and a `status` of `ok`, `violations`, `degraded` or `failed`. A bracket whose best-effort layout still breaks a hard rule or gives a bye to a lower seed than a player without one (`degraded`), or that breaks a hard rule (group separation in the halves or quarters, or two group winners meeting in round one), is also listed in **red on the terminal** and marked at the top of its HTML page. Check the report before posting a draw.

At the start of every run, the previous run's output CSV, report and HTML files are moved to `output/previous/`. If the run then fails, there is no output that could be mistaken for a current one, and the terminal shows a red "The draw did NOT complete" banner. If `output.csv` is open in Excel, the run stops right away and asks you to close it.

# Group viewer

Every group draw (all singles/doubles/mixed classes) is **exported to a self-contained HTML file** automatically at startup, into `output/groups/`. From the Groups menu, groups can be viewed in the terminal, or **"View HTML"** opens the pre-exported file in the browser — one group card per row so no column is ever cut off, with an in-browser stepper through the Monte Carlo draw history. The page opens on the final groups. Details: [ARCHITECTURE.md § Viewer / CLI UX](ARCHITECTURE.md#7-viewer--cli-ux-viewer-miscmenupy).

# Bracket viewer

Every bracket (all singles/doubles/mixed classes, main and consolation) is **exported to a self-contained HTML file** automatically at startup, into `output/brackets/`. From the Bracket menu, brackets can be viewed in the terminal, or **"View HTML"** opens the pre-exported file in the browser — an SVG bracket tree with an in-browser stepper through every draw snapshot, useful for verifying the draw logic on large brackets without terminal scroll/cutoff. Each exported file ends with a provenance footer recording the app version that produced it, how long that specific bracket took to draw, the total run time, the random seed, and a timestamp. Details: [ARCHITECTURE.md § Viewer / CLI UX](ARCHITECTURE.md#7-viewer--cli-ux-viewer-miscmenupy).

# Configuration

Runtime behavior (file paths, log level, random seed, Monte Carlo tuning, bracket phase limits) is controlled by `config/config.ini`. Full key reference: [ARCHITECTURE.md § Configuration](ARCHITECTURE.md#8-configuration).

# Known issues

See [ARCHITECTURE.md § Known Issues](ARCHITECTURE.md#9-known-issues) for the current list of known bugs, dead code, and config mismatches.