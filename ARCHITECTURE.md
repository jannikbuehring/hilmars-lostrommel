# Architecture

Technical reference for the **hilmars-lostrommel** codebase. This document complements `output/output_explainer.md` (authoritative CSV column reference) and `open_questions.md` (original German design notes for the bracket rules).

Generated from a full read of every module in `models/`, `data_io/`, `misc/`, `checks/`, `draw/`, `viewer/`, `tests/`, plus the config and sample data files, as of 2026-07-24.

## 1. Overview

A CLI tool that generates round-robin **group draws** and single-elimination **knock-out brackets** (main + consolation) for table-tennis tournaments, across singles/doubles/mixed competitions and multiple classes (M1/M2/M3, W1/W2/W3, X1/X2/X3, etc.). Input is CSV, output is CSV, and results are browsed through an interactive console menu.

- **Entry point:** `hilmars_lostrommel.py` → `misc.initializer.initialize_data()` (runs the whole read → validate → draw → export pipeline once) → `misc.menu.show_main_menu()` (interactive loop to browse the results).
- **Distribution:** packaged as a single console executable via PyInstaller (`hilmars_lostrommel.spec`); build artifacts land in `build/`, `dist/`, `builds/`.
- **No GUI, no network I/O.** Everything is local files + a terminal UI (`tabulate` for tables, `inquirer` for menus, `yaspin` for progress spinners).

## 2. Data flow / pipeline

`misc/initializer.py::initialize_data()` runs 8 stages in order, each wrapped in try/except with a `yaspin` spinner:

1. **Read players** — `data_io.input_reader.read_players()`. Aborts the whole run on `FileNotFoundError` or any exception.
2. **Read draw data** — `data_io.input_reader.read_draw_data()`, then split into 9 buckets: `{singles, doubles, mixed} × {all, group_stage (group_pos is None), bracket_stage (group_pos is not None)}`.
3. **Validity checks** (`checks/validity_checker.py`):
   - `check_all_players_only_exist_once()` — abort on duplicate start numbers. Also populates the `players_by_start_number` registry (see [§3](#3-core-data-model-models)).
   - `find_missing_players(draw_data)` — abort if draw data references an unknown player.
   - `find_players_not_in_draw_data(draw_data)` — warn-only (and currently buggy, see [§9](#9-known-issues)).
   - `find_players_in_wrong_competition(draw_data)` — prints errors but **does not abort** (see [§9](#9-known-issues)).
4. **Draw groups** — for each competition_class within group-stage data (separately for S/D/M), calls `draw.group_drawer.draw_groups_monte_carlo`.
5. **Validate group draws** — runs `check_country_distribution`, `check_base_uniqueness`, `check_team_country_distribution` (D/M only), `get_qttr_violations` (S only) from `checks/group_checker.py`. Violations are printed and warned, never abort.
6. **Draw brackets** — for each competition_class, splits bracket-stage data into `main_round_participants` / `consolation_round_participants`, calls `draw.bracket_drawer.draw_bracket` through a local wrapper `draw_bracket_with_snapshot_fallback`, which catches exceptions, records the failure (message + snapshots) in a `bracket_failures` list, logs it, and substitutes an empty bracket — **so one class's bracket failing does not abort the run**, unlike group-draw or validity failures.
7. **Prepare export** — `data_io.output_writer.prepare_export_from_group_draw` / `prepare_export_from_bracket_draw` flatten the internal dict structures into export rows.
8. **Write CSV** — `data_io.output_writer.write_to_csv` writes the combined `output.csv`.

Error-handling summary: **stages 1-4 abort the whole pipeline on failure; stage 6 isolates failures per competition class; stages 3(partial)/5 only warn.**

## 3. Core data model (`models/`)

### Active classes

| Class | File | Role |
|---|---|---|
| `Player` | `models/player.py` | One competitor: `start_number, first_name, last_name, country, base, gender, qttr`. Appends itself to module-global `players_list` on construction. |
| `DrawDataRow` | `models/draw_data.py` | One line of `draw_input.csv`: doubles as a group-stage seed entry (`group_pos is None`) or a bracket-stage entry (`group_pos` set). Registers seeding into module-global `seeding_by_start_numbers` (keyed `"A"` or `"A/B"`) as a side effect of construction. |
| `Snapshot` | `models/snapshot.py` | Generic audit-trail/undo-log entry (`action, groups, index, participants, violations, violation_score, initial_groups`) appended after every meaningful mutation during group Monte Carlo and bracket construction. Powers the interactive step-through viewer and failure diagnostics (see [§5](#5-algorithms-draw) and [§7](#7-viewer--cli-ux-viewer-miscmenupy)). |

**Module-level global registries** (implicit registry/singleton pattern — import/call order matters):
- `players_list`, `players_by_start_number` (`models/player.py`) — the latter is only populated by `checks.validity_checker.check_all_players_only_exist_once()`, *not* by `Player.__init__`. Anything that reads `players_by_start_number` (e.g. `DrawDataRow.__repr__`, the checkers, `output_writer`) requires that function to have run first.
- `seeding_by_start_numbers` (`models/draw_data.py`) — read later by `draw.bracket_drawer` to re-attach seeding to bracket-stage rows (whose CSV line has no seeding value; seeding is only given once, on the group-stage row).

**Actual runtime data shapes** (not the classes below):
- Groups = `dict[group_no, list[DrawDataRow | EmptySlot]]` (`EmptySlot` is a local placeholder class in `draw/group_drawer.py`, stripped before returning).
- Brackets = `dict[draw_number, [DrawDataRow_or_"BYE", DrawDataRow_or_"BYE"]]`.

### Dead code

`models/bracket.py` (`Bracket`), `models/match.py` (`Match`), `models/team.py` (`Team`), and `models/group.py` (`Group`) are **never instantiated anywhere** in `draw/`, `checks/`, `data_io/`, `misc/`, or `viewer/`. See [§9](#9-known-issues) for details, including a genuine crash-on-use bug in `Group`.

## 4. Input/output formats (`data_io/`)

Both readers in `data_io/input_reader.py` expect **semicolon-delimited** UTF-8 CSV, header line skipped, fields split positionally (no `csv` module / DictReader used for input).

- **`players.csv`** — positional fields: `start_number, last_name, first_name, country, base, gender, qttr`. Sample header (`input/players_2026_test.csv`, UTF-8 BOM): `Startnumber;Last_name;First_name;Country;PPP_chapter;Gender;QTTR`, e.g. `1001;Wang;Chuqin;CHN;China;M;2796`.
- **`draw_input.csv`** — positional fields: `competition, competition_class, amount_of_groups, seeding, group_no, group_pos, main_round, consolation_round, start_number_a, start_number_b`. Sample header (`input/draw_input_2026_20260626_test.csv`): `S_D_M;class;#groups;seeding;group_no;group_pos;for_main_round;for_consolation;startnumber_A;startnumber_B`. `main_round`/`consolation_round` are coerced with plain `bool(...)` on the raw string — any non-empty string (including `"0"`) is truthy.
- **`output.csv`** — written by `write_to_csv` with the fixed header `S_D_M, class, seeding, group_no, group_pos, for_main_round, for_consolation, draw_number, startnumber_A, last_name_A, country_A, PPP_chapter_A, startnumber_B, last_name_B, country_B, PPP_chapter_B, is_bye`. Column semantics are documented authoritatively (in German) in `output/output_explainer.md`.
- The per-class files under `output/` (`S_M1_groups.csv`, `S_M1_main.csv`, `S_M1_consolation.csv`, `example_output.csv`) are **reference/example outputs**, not something the current `output_writer.py` produces — it only ever writes one combined `output.csv`.
- ⚠️ `prepare_export_from_group_draw` only exports the **last member of each group**, not all members — see [§9](#9-known-issues).

## 5. Algorithms (`draw/`)

### Group draw — `draw/group_drawer.py::draw_groups_monte_carlo(class_subset, amount_of_groups)`

**This is a Monte-Carlo / simulated-annealing-style local search, not backtracking** (correcting `README.md`'s claim).

1. Read tuning parameters from `config[group_draw]` (see [§8](#8-configuration)).
2. **Outer loop over `max_seed_retries` random seeds**: each attempt reseeds `random` and runs a fresh optimization; the best (lowest violation score) result across attempts is kept, with early exit on a perfect score-0 solution.
3. **Deterministic seed placement**: `class_subset` sorted by `seeding` descending, split into batches of size `amount_of_groups`, distributed round-robin (batch `j` → `group_no = j+1`) — a standard "snake" seeding so seed 1..N lands one-per-group in order. Groups are padded to `ceil(n / amount_of_groups)` with `EmptySlot` placeholders.
4. **Violation scoring** (`checks/group_checker.py`, weighted sum, lower is better):
   - `check_country_distribution` — always; max/min country-count spread across groups must be ≤1 (singles) / ≤2 (doubles/mixed).
   - `check_base_uniqueness` — always; no two participants sharing a training base ("base"/club) in the same group.
   - `get_qttr_violations` — singles only; unrated (no-QTTR) players spread evenly (max ≤ min+1).
   - `check_team_country_distribution` — doubles/mixed only; full-country and half-country teams spread evenly (max ≤ min+1) per country.
5. **Swap loop** (`max_iterations`, default 20000): picks a random non-first batch (batch 0, the highest seeds, is never touched — it stays exactly as placed in step 3), swaps two groups' occupants at that batch index, rescoring:
   - Improvement → keep, reset stagnation counters, break early on score 0.
   - Equal → keep (sideways move).
   - Worse → normally revert; but once stuck for `max_no_improvement_iterations` with escape budget remaining (`max_escape_attempts`), accept the bad swap anyway as a perturbation to escape a local minimum.
   - Every swap/revert appends a `Snapshot(action='swap'|'revert', ...)`.
6. `EmptySlot`s are stripped before returning `(best_groups, best_snapshots)`. If no perfect solution is found after all seed retries, a warning is printed.

### Bracket draw — `draw/bracket_drawer.py::draw_bracket(class_subset)`

**This is where real backtracking lives** (correcting `README.md`, which attributes backtracking to group draw). A 5-phase pipeline; phase count is capped by `config[bracket_draw].max_draw_phase` (see [§8](#8-configuration) — **currently set to `1` in the live config, so only Phase 1 runs by default**).

1. **Phase 1 — place group-winners (`group_pos == top`)**, using `bye_hierarchy(num_slots)` (the classic power-of-two seeded-slot subdivision order). Batch 0 (slot 1) and the last batch (last slot) are placed deterministically (seed #1, #2); later batches use greedy scoring (`score_candidate_placement`, via `score_bracket`) plus heavy penalties for unbalancing top-seed density across quarters/halves. Each group's winner slot is recorded as the "anchor" (`_update_group_top`) for later rules. **Returns early here if `max_draw_phase <= 1`** (`draw/bracket_drawer.py:679`).
2. **Phase 2 — `assign_quarter_buckets`**: for every non-winner, `delta = group_pos - top_group_pos` decides its required quarter relative to its group's anchor:
   - delta=1 (runner-up) → opposite half from the anchor.
   - delta=2 (3rd) → opposite half, but the *other* quarter than the one chosen for delta=1 (so 2nd/3rd from a group can meet no earlier than the quarterfinal).
   - delta=3 (4th) → same half as the anchor, different quarter (so 1st/4th can meet no earlier than the semifinal).
   - Unconstrained players are bulk-assigned to whichever quarter has spare capacity. Ties broken by country-conflict cost (`_country_cost`). Raises `"quarter_capacity_impossible"` if capacity can't satisfy the requirements.
3. **Phase 3 — `place_seeded_batch_backtracking`**: genuine backtracking (`recurse(participant_index, group_index)`) places remaining bye recipients into their Phase-2-required quarters, trying scored candidate slots and undoing (`pop` snapshot, unlock slot) on failure before trying the next candidate. Raises `"bye_slot_failure"` if exhausted.
4. **Phase 4** — groups remaining (non-bye, non-winner) players into per-quarter candidate pools per their Phase-2 assignment; raises `"quarter_pool_size_mismatch"` if pool size doesn't match free slots.
5. **Phase 5** — per-quarter Monte Carlo refinement: each quarter shuffled independently, then iteratively (holding the other 3 quarters fixed) tries up to `max_attempts` random reshuffles of one quarter's pool, keeping the best-scoring arrangement (`score_bracket`), stopping early at score 0.

Every phase transition/attempt appends a `Snapshot`. On unrecoverable failure, `raise_with_failure_snapshot` attaches a diagnostic snapshot (with a `"failure"` key: message/type/phase/locked_slots) to the raised `ValueError` as `.snapshots`/`.failure_snapshot`, consumed by `misc/initializer.py`'s fallback wrapper and inspectable via the interactive viewer.

**Rule implementation cross-reference** (source: `open_questions.md`):

| Rule (open_questions.md) | Implemented in | Validated by |
|---|---|---|
| Group winners never meet round 1 | Phase 1 placement + delta=1 opposite-half rule | `check_no_first_vs_first` |
| Seeds/byes placed first | Phase 1, `bye_hierarchy` order | — |
| Country distribution across halves | Scored tie-breaking + `_country_cost` | `check_country_balance_halves` |
| No same-"base" opponents round 1 (soft) | Scored in `score_bracket` | `check_base_conflicts_first_round` |
| 2nd/3rd of a group separated until quarterfinal | delta=1/delta=2 opposite-quarter logic | `check_quarter_group_separation` |
| 1st/4th same half, different quarter (meet at earliest in semifinal) | delta=3 logic | `check_quarter_group_separation` |
| 1st/4th vs 2nd/3rd in opposite halves | — | `check_half_group_separation` |

## 6. Validation (`checks/`)

- **`validity_checker.py`** — pre-draw input sanity (see [§2](#2-data-flow--pipeline) stage 3).
- **`group_checker.py`** — `check_country_distribution`, `check_base_uniqueness`, `get_qttr_violations`, `check_team_country_distribution` (used both live during Monte Carlo scoring and again as a post-hoc report in `initializer.py`).
- **`bracket_checker.py`** — `check_half_group_separation`, `check_quarter_group_separation`, `check_no_first_vs_first`, `check_country_balance_halves`, `check_base_conflicts_first_round`, and `score_bracket(matches, number_of_matches, weights=None)` (default weights: `quarter_split=200, half_split=150, first_vs_first=100, country_half=10, base_first=20`). `draw_bracket` builds a `bracket_weights` dict from `config[bracket_draw]`'s `half_split_weight`/`first_vs_first_weight`/`country_half_weight`/`base_first_weight` (falling back to the defaults above) and passes it to every `score_bracket` call; there's still no `quarter_split_weight` config key, so that term stays fixed at 200.

## 7. Viewer / CLI UX (`viewer/`, `misc/menu.py`)

Console-only, via `tabulate` (tables) and `inquirer` (menus) — no GUI, no HTML output, no ASCII bracket trees.

- **Menu flow** (`misc/menu.py`): `show_main_menu()` → `View` → `{Players | Groups | Bracket}` → `{Singles | Doubles | Mixed}` → pick a drawn competition class → render via `viewer.group_viewer.show_groups` / `viewer.bracket_viewer.show_bracket`.
- **Display mode** is driven by `config["settings"]["mode"]` (`normal` = static table; `interactive` = step through `Snapshot`s one action at a time, with jump-to-next-improvement, jump-to-snapshot-number, and jump-to-final actions).
- `viewer/group_viewer.py`'s interactive replay reconstructs group state by starting from `snapshots[0].initial_groups` and replaying `swap`/`revert` actions up to the current index, rather than storing full state per snapshot.
- `viewer/bracket_viewer.py` additionally supports Windows `msvcrt`-based arrow-key navigation in a real TTY, falling back to line-based `input()` prompts otherwise; highlights the best quarter in green; falls back to plain `tabulate` format on `UnicodeEncodeError`.
- `viewer/player_viewer.py::show_players_table()` — flat player listing.
- `viewer/view_config.py` — single shared setting, `table_format = "rounded_outline"`, used by all three viewers.

## 8. Configuration (`config/config.ini`, `misc/config.py`)

Loaded once at startup by `misc.config.initialize_config(base_dir)`, which reads `<base_dir>/config/config.ini` into a module-level `configparser.ConfigParser()` singleton (imported as `from misc.config import config` throughout), seeds Python's global `random` module from `settings.random_seed` if set, and configures `logging.basicConfig` from `settings.log_level`.

| Section | Key | Meaning |
|---|---|---|
| `[files]` | `draw_data_path`, `players_path`, `output_file_path` | Input/output file locations. |
| `[settings]` | `log_level` | 10/20/30/40/50 = debug/info/warning/error/critical. |
| | `mode` | `normal` or `interactive` (viewer step-through). |
| | `random_seed` | If set, makes random outcomes deterministic. |
| `[group_draw]` | `max_iterations`, `max_no_improvement_iterations`, `max_escape_attempts`, `max_seed_retries` | Monte Carlo tuning (see [§5](#5-algorithms-draw)). |
| | `country_violation_weight`, `team_country_violation_weight`, `base_violation_weight`, `qttr_violation_weight` | Weights for the group violation score. |
| `[bracket_draw]` | `max_attempts` | Per-quarter Monte Carlo attempts in Phase 5. |
| | `max_draw_phase` | **1-5; how many of the 5 bracket phases to run.** |
| | `half_split_weight`, `first_vs_first_weight`, `country_half_weight`, `base_first_weight` | Weights for the bracket violation score (`score_bracket`); no `quarter_split_weight` key exists, so that term is fixed at 200. |

⚠️ **The live `config/config.ini` currently has `max_draw_phase = 1`** — meaning a normal run today only executes Phase 1 (top-group-pos/seed placement) of the bracket algorithm and returns early; runners-up, 3rd/4th place, and bye backtracking (Phases 2-5) do not run unless this is changed to `5`.

## 9. Known Issues

Concrete bugs, dead code, and config/behavior mismatches found while documenting this codebase. None of these have been fixed as part of this documentation pass.

- **Group export drops all but the last group member** — `data_io/output_writer.py:14-17`: the `for member in members:` loop (computing `player_a`/`player_b`) is indented one level deeper than the `export_line_to_add = SimpleNamespace()` block that follows it, so the export line is built and appended once per **group**, using only the last member's data, not once per member.
- **`dist/config/config.ini` is a stale build artifact** — points at old input filenames (`draw_input_2025.csv`, `players_2025.csv`) and is missing the `[bracket_draw]` section entirely. Harmless in practice: `bracket_drawer.py` reads config via `config.getint(..., fallback=...)`, so a build from `dist/` would silently use built-in defaults (`max_attempts=2000`, `max_draw_phase=5`) instead of the tuned live values.
- **`requirements.txt` is missing `readchar`** — `hilmars_lostrommel.spec` bundles it via `collect_all('readchar')` (needed for keypress reading, likely a transitive dependency of `inquirer`), but it isn't listed in `requirements.txt`.

## 10. Build

Packaged via **PyInstaller** (`hilmars_lostrommel.spec`): single console executable (no windowed/GUI mode), entry point `hilmars_lostrommel.py`, `collect_all('readchar')` to bundle that package's data/binaries/hidden imports, UPX compression enabled, no code signing. Build output in `build/hilmars_lostrommel/`; distributable artifacts in `dist/` and `builds/`.
