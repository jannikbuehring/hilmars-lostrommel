# Architecture

Technical reference for the **hilmars-lostrommel** codebase. This document complements `output/output_explainer.md` (authoritative CSV column reference) and `rules.md` (German domain rules for the group and bracket draw, kept locally and gitignored, so it is not part of the repository).

## 1. Overview

A CLI tool that generates round-robin **group draws** and single-elimination **knock-out brackets** (main + consolation) for table-tennis tournaments, across singles/doubles/mixed competitions and multiple classes (M1/M2/M3, W1/W2/W3, X1/X2/X3, etc.). Input is CSV; output is one combined CSV, a draw report, and a self-contained HTML file per group class and per bracket, which a console menu opens in the browser.

- **Entry point:** `hilmars_lostrommel.py` → `app.cli.parse_args()` (command-line overrides, see [§8](#8-configuration)) → `core.config.initialize_config()` → `app.pipeline.initialize_data(results)` (runs the whole read → validate → draw → export pipeline once, filling a `DrawResults`) → `app.menu.show_main_menu(results)` (interactive loop to browse the results).
- **Package layering:** `core/` (`config`, `version`) is the foundation that every other package may import, and it imports nothing from `app/`. `app/` (`pipeline`, `menu`, `cli`, `banner`, `progress_spinner`) sits on top: it orchestrates `data_io`, `checks`, `draw` and `viewer`, and only `hilmars_lostrommel.py` imports it. `DrawResults` and `COMPETITIONS` live in `models/draw_results.py`, so the menu does not depend on the pipeline.
- **Version:** `core/version.py` (`APP_NAME`, `__version__`) is the single source of truth, read by the startup banner, the HTML exports and the PyInstaller spec. Releases are tagged `v<version>`; the CI build runs on those tags.
- **Distribution:** a single console executable built by PyInstaller (`hilmars_lostrommel.spec`), see [§10](#10-build). No pre-built exe is committed.
- **No GUI, no network I/O** at runtime. Everything is local files plus a terminal UI (`tabulate` for tables, `inquirer` for menus, `yaspin` for progress spinners).

## 2. Data flow / pipeline

`app/pipeline.py::initialize_data(results)` runs its stages in order, each with a spinner. Every per-competition stage loops over `COMPETITIONS` (S/D/M) and stores its results in `results.groups[competition][class]` and `results.brackets[competition][class]`. It returns `True` when it reached the end (possibly with warnings) and `False` when a stage aborted the run. On `False`, or on an exception that escapes into `main()`, `hilmars_lostrommel.py` prints a red banner saying that no current output was written, and then opens the menu anyway.

0. **Archive the previous run** — `output_writer.archive_previous_outputs()` moves the last run's output CSV, report and generated HTML into `previous/` next to the output CSV (emptied first, so it only holds the run before this one). This runs first so that an aborted run can never leave old files looking current. A `PermissionError` (typically `output.csv` open in Excel) aborts here with "close it and restart", instead of after the whole draw.
1. **Read players** — `data_io.input_reader.read_players()`. Aborts on any error.
2. **Read draw data** — `read_draw_data()`, split into `{singles, doubles, mixed} × {all, group_stage, bracket_stage}` (a row is bracket-stage when `group_pos` is set).
3. **Validity checks** (`checks/validity_checker.py`, see [§6](#6-validation-checks)) — all fatal except the "player not entered anywhere" warning. `check_all_players_only_exist_once()` also populates the `players_by_start_number` registry (see [§3](#3-core-data-model-models)).
4. **Draw groups** — per class, `draw.group_drawer.draw_groups_monte_carlo` via the wrapper `draw_groups_with_fallback`. A failing class is logged, listed in the spinner's `WARN` line and left out of everything downstream; the other classes continue.
5. **Validate group draws** — runs the `checks/group_checker.py` checks on the result. Violations are printed and counted for the report, never fatal.
6. **Draw brackets** — per class and per `main`/`consolation`, `draw.bracket_drawer.draw_bracket` via the wrapper `draw_bracket_with_snapshot_fallback`, the single choke point where every bracket is drawn. A failure is logged and replaced by an empty bracket, so the other classes continue. The wrapper returns `matches`, `snapshots`, `draw_seconds` and `quality`.

   **Draw quality is surfaced, not just stored.** `quality` comes from `bracket_drawer.bracket_quality(snapshots)` and holds `degraded`, `hard` (violated rules of `HARD_BRACKET_RULES`: half separation, quarter separation, first-vs-first), `bye_order`, `balance` (half-balance lines such as `byes 8/6 over the halves`) and `soft_count`. It is read from the last snapshot, because every return path of `draw_bracket` appends a snapshot of the state it returns. `report_bracket_section` ends a section in `WARN` and prints one red line per problem whenever a bracket failed, degraded, broke a hard rule, handed byes out of seeding order or has unbalanced halves.
7. **Prepare export** — `output_writer.prepare_export_from_group_draw` / `prepare_export_from_bracket_draw` flatten the results into rows: **one row per group member** and **one row per bracket slot** (not per match). `_iter_bracket_slots` is the inverse of `bracket_drawer.slot_to_match`. Failed brackets (`matches == {}`) are skipped.
8. **Write CSV and draw report** — `write_to_csv` and `write_report_csv(prepare_report(...))`, both via `_write_csv_atomically` (write `<path>.tmp`, then `os.replace`), so a crash never leaves a half-written file.
9. **Export HTML** — `export_group_html` (to `output/groups/`) and `export_bracket_html` (to `output/brackets/`) for every drawn class. A shared `run_meta` dict (version, total run time, timestamp, random seed) feeds the footers. Each file is exported in its own try/except.

Error-handling summary: **stages 0-3 abort the whole pipeline (as does an unexpected error in stages 4-8); stages 4, 6 and 9 isolate failures per class; stage 5 and the unused-player check only warn.** Because of stage 0, every abort leaves no output behind that could be mistaken for the current run's.

## 3. Core data model (`models/`)

| Class | File | Role |
|---|---|---|
| `Player` | `models/player.py` | One competitor: `start_number, first_name, last_name, country, base, gender, qttr`. Appends itself to the module-global `players_list` on construction. |
| `DrawDataRow` | `models/draw_data.py` | One line of `draw_input.csv`: a group-stage entry (`group_pos is None`) or a bracket-stage entry (`group_pos` set). Registers its seeding into the module-global `seeding_by_start_numbers` (keyed `"A"` or `"A/B"`) on construction. |
| `Snapshot` | `models/snapshot.py` | Audit-trail entry (`action, groups, index, participants, violations, violation_score, state`) appended after every meaningful step of the group and bracket draws. Powers the HTML step-through viewers and failure diagnostics. |
| `BracketGeometry`, `allowed_quarters` | `models/bracket_geometry.py` | The single source for half/quarter geometry and for the group-separation quarter rule. The drawer places by it, `bracket_checker` checks by it, and the HTML viewer groups quarters by it, so the three cannot drift apart. |

**Module-level registries** (import/call order matters):
- `players_list`, `players_by_start_number` (`models/player.py`). The latter is only populated by `check_all_players_only_exist_once()`, not by `Player.__init__`, so anything that reads it requires that check to have run.
- `seeding_by_start_numbers` (`models/draw_data.py`) — used by the bracket drawer to re-attach seeding to bracket-stage rows, which carry none in the CSV.

**Runtime data shapes:**
- Groups = `dict[group_no, list[DrawDataRow]]` (padded internally with `EmptySlot` placeholders, stripped before returning).
- Brackets = `dict[match_number, [DrawDataRow | "BYE", DrawDataRow | "BYE"]]`.

## 4. Input/output formats (`data_io/`)

Both readers expect **semicolon-delimited** UTF-8 CSV (a BOM is fine), skip the header and split fields positionally. Every field is stripped of surrounding whitespace.

- **`players.csv`** — `start_number, last_name, first_name, country, base, gender, qttr`. Sample: `input/players_example.csv`, header `Startnumber;Last_name;First_name;Country;PPP_chapter;Gender;QTTR`.
- **`draw_input.csv`** — `competition, competition_class, amount_of_groups, seeding, group_no, group_pos, main_round, consolation_round, start_number_a, start_number_b`. Sample: `input/draw_input_example.csv`, header `S_D_M;class;#groups;seeding;group_no;group_pos;for_main_round;for_consolation;startnumber_A;startnumber_B`. The round flags are `True` only for the value `1`. The structural rules are enforced by `find_draw_data_errors` (see [§6](#6-validation-checks)).
- **`output.csv`** — fixed header `HEADERS`, semicolon-delimited, encoded `utf-8-sig` so German names survive opening in Excel. Column semantics are documented in `output/output_explainer.md`. Three points the format hinges on:
  - **`draw_number` is a bracket *slot*, not a match** — the position in the knock-out bracket, `1..bracket_size`. Group rows leave it empty.
  - **The `_B` columns are the doubles/mixed *partner***, never the opponent. Blank in singles.
  - **`is_bye`** is `True` on a bye slot (only competition, class, round flags and `draw_number` are filled), `False` on a real bracket slot, and blank on group rows. The round flags follow the same pattern.
- **Draw report** (`<output stem>_report.csv`, path from `report_file_path()`), same delimiter and encoding. Header `REPORT_HEADERS`: `S_D_M, class, draw, status, half_group_separation, quarter_group_separation, first_vs_first, other_violations, details`. One row per group class (`draw = groups`) and per bracket (`main`/`consolation`).
  - `status` is `ok`, `imbalanced` (no hard violation, but byes or tiers split more than one apart over the halves; some such splits are forced, see [§9](#9-known-issues)), `violations`, `degraded` (best-effort bracket that still breaks a hard rule or the bye seeding order) or `failed`. Bracket precedence: `degraded` > `violations` > `imbalanced` > `ok`.
  - The three rule columns count hard-rule violations; `other_violations` counts the rest. `details` joins the violation texts, `bye_order: …` and `imbalanced: …` lines, or the failure message.

  The report exists so that `output.csv` can keep its fixed format while a problematic draw is still visible outside the terminal and the HTML.
- `output/example_output.csv` is a reference example, not something the current code produces.

## 5. Algorithms (`draw/`)

### Progress reporting

Both drawers take an optional `progress` callable that receives one plain-language status line. The pipeline shows it as the second line of `app/progress_spinner.py::DetailSpinner`, a yaspin subclass that redraws a two-line frame, truncates the detail to the terminal width and only draws it on a TTY. Messages are plain ASCII because the Windows console code page may lack `–` or `·`. The group drawer reports per seed attempt and every `PROGRESS_INTERVAL` swap steps; the bracket drawer reports per phase and every tenth of its long loops.

### Group draw — `draw/group_drawer.py::draw_groups_monte_carlo(class_subset, amount_of_groups, progress=None)`

A Monte-Carlo / simulated-annealing-style local search.

1. Read tuning parameters from `settings.group_draw` (see [§8](#8-configuration)).
2. **Outer loop over `max_seed_retries` random seeds.** The best result across attempts is kept; a score of 0 exits early.
3. **Deterministic seed placement:** entries sorted by `seeding` descending (higher = stronger), split into batches of `amount_of_groups`, and distributed so the N strongest land one per group. Groups are padded with `EmptySlot`.
4. **Violation scoring** (weighted sum from `checks/group_checker.py`, lower is better): country spread, shared training base, unrated players (singles), team country spread (doubles/mixed).
5. **Swap loop** (`max_iterations`): swap two groups' occupants at a random batch index, except batch 0 (the top seeds, never moved). Improvements and sideways moves are kept; worse swaps are reverted, except that after `max_no_improvement_iterations` without progress up to `max_escape_attempts` bad swaps are accepted to escape a local minimum. Every swap/revert appends a `Snapshot`. With a single batch there is nothing to swap, so the placement from step 3 is returned directly.
6. Each seed returns the **best state it visited**, and the snapshot list is cut back to that step, so replaying it in the viewer lands on the returned groups.

### Bracket draw — `draw/bracket_drawer.py::draw_bracket(class_subset, progress=None)`

`draw_bracket` runs one full draw (`_draw_bracket_attempt(..., half_balance=True)`). If that draw ends on the degrade path, it draws once more **without the projected bye/tier half balance**, from the same RNG state, and keeps the better result by `_result_rank` (hard violations, then bye-order breaks, then half-balance lines, then whether the degrade path was needed). A separation is therefore never paid for an even split. `phase1_only=True` stops after Phase 1 (tests only).

Each attempt is a phased pipeline. Group positions are handled **relative to the bracket**: `top` is the best `group_pos` present (1 in a main draw, 4 in a consolation), and `delta = group_pos - top`.

1. **Phase 1 — place the group winners** on the seeded slots of `bye_hierarchy(num_slots)` (the classic power-of-two seeding order, e.g. `[1] [16] [8,9] [4,5,12,13] …`). The first two are fixed; every later batch is assigned **jointly** by `place_batch` (exact search when the assignment count fits `joint_batch_max_evaluations`, otherwise a hill-climb seeded with the greedy result). Candidates are ranked by a strict penalty ladder, highest first:
   - `half_load_cost` — keeps the halves *fillable*: each winner forces its 2nd/3rd into the opposite half and its 4th into its own, and a bye takes a second slot, so the drawer balances this net load rather than the raw winner count.
   - `combined_excess` (in `placement_penalty`) — winners + byes per quarter, at most one above the minimum.
   - `bye_half` and `tier_half` (`projected_half_balance_units`) — the byes and the tiers `top..top+2` evenly over the halves (rules.md). Both splits are decided by the winners' halves long before the other players are placed, so the term charges the split the partial state is already *committed to*, and only the part the remaining slack can no longer close.
   - `tier_quarter_excess` — each tier evenly over the two quarters of its half.
   - `score_bracket + score_round_two` — tiebreakers (countries, matchups, round-two quality).

   `winner_country_lookahead` adds the best winner-country split still reachable over the halves when at most `WINNER_LOOKAHEAD_MAX_PENDING` winners remain. The quality terms are evaluated once on the finished trial assignment (`assignment_quality_cost`) rather than per step, because a per-step marginal can charge a legal final split for the order it was built in. The ladder's weights are constants, not config keys: their correctness depends on the strict ordering. Winners are locked and never move again; each group's winner slot becomes its **anchor**.

   **Why `check_no_first_vs_first` cannot fire:** `bye_hierarchy` is a perfect bipartition of the first-round matches, and two winners could only meet if Phase 1 reached the last batch, which needs more winners than half the slots. Every group sends at least two players, so that never happens with valid input. The check is kept as a defensive validator; in practice the winner's opponent is governed by `check_top_easy_first_round`.

2. **Phase 1b — remaining byes** (only when byes outnumber winners). Bye recipients continue down the same `bye_hierarchy` in seeding order, each masked to the quarters its group's anchor allows. A chunk is admitted only while it still has a perfect matching to the free slots (`_max_matching`), so the chunk is the highest-seeded one that can actually be placed. Recipients the hierarchy cannot host fall back to required quarter → required half → any free slot.

   **Round-two matchups.** With many byes almost every first-round match is a walkover, so `derive_round_two_matches` builds the virtual round two (a side is known only when its feeder was a bye) and grades it with the same checkers. Tier bounds are passed explicitly (`bounds=`), because a partial bracket cannot show them.

3. **Phase 1c — `repair_bye_placements`**, the only pass with a global view of what Phase 1/1b locked in. It swaps two **non-winner bye recipients**, which is capacity-neutral (both slots stay `(player, BYE)`), or moves one bye recipient with its BYE into a free match in the other quarter of its half, which is only allowed when it lowers `residual_overflow` (players whose forced quarter cannot hold them). Candidates are ranked by `(residual_overflow, cost)`. The separations are a hard gate: a step may reduce them, never increase them. The pass is deterministic best-improvement and consumes no randomness, so it does not shift later random choices. It runs only when Phase 1b ran.

4. **Phase 2 — `assign_quarter_buckets`** for the remaining non-bye players, by `delta` relative to the anchor:
   - delta=1 (runner-up) → opposite half.
   - delta=2 (3rd) → opposite half, other quarter than its runner-up (they meet no earlier than the quarterfinal). The map that enforces this is seeded from the board, because the runner-up may already have been placed with a bye.
   - delta=3 (4th) → same half, other quarter (no earlier than the semifinal).
   - Forced players go first, then "solo" runners-up (no 3rd in the group), which have a free choice and take what is left. Unconstrained players fill spare capacity, ties broken by `_country_cost`. There is deliberately no tier tiebreaker: capacity decides almost every case, and one was tried and only made country spread worse.
   - **`rebalance_bottom_tier_quarters`** then exchanges the quarters of a group's runner-up and 3rd where that gives a winner in some quarter a bottom-tier opponent (`check_top_easy_first_round`). The exchange is capacity-neutral and keeps both separations. It does not apply to 4-tier brackets, whose bottom tier sits in the anchor's own half.
5. **Phases 3 and 5** — the remaining players are pooled per quarter, and each quarter is refined by Monte Carlo (`max_attempts` reshuffles within the quarter, early exit at score 0). Arrangements are compared by **`score_bracket_tiers`**, a tuple `(hard, matchup, distribution)`, so a separation always outranks a matchup and a matchup always outranks country spread. Because this only permutes players *within* a quarter, any rule about who faces whom depends on Phase 2 having routed the right players into that quarter.

**Graceful degradation (`_fill_residual_soft`).** When the residual players cannot be packed into their required quarters, the draw does not abort. A `"quarter_capacity_degrade"` snapshot marks the switch, and a local search fills every free slot, starting from the best of a few random fills and hill-climbing with three moves that never touch a group winner (swap two winner-free matches, move a BYE between same-position players, swap two non-winners). Its objective is lexicographic: hard tier, then bye seeding order, then `assignment_quality_cost` (without the tier-half term), then matchup and distribution; it restarts from the best state when it plateaus. If the fill ends clean, the bracket counts as regular; otherwise it is flagged as `degraded` on the terminal, in the report and in its HTML. Genuine structural failures (occupied fixed seed slot, un-placeable byes) still raise.

On an unrecoverable failure, `raise_with_failure_snapshot` attaches a diagnostic snapshot to the raised `ValueError`, which the pipeline's wrapper records.

**Rule implementation cross-reference** (source: `rules.md`):

| Rule (rules.md) | Implemented in | Validated by |
|---|---|---|
| Group winners never meet round 1 | Structurally impossible via `bye_hierarchy`; defensive check only | `check_no_first_vs_first` |
| Group winners get a BYE or a lowest-placed round-1 opponent (outranks country) | Phase 2 `rebalance_bottom_tier_quarters` + `score_bracket` | `check_top_easy_first_round` |
| Two lowest-placed players never meet round 1 (soft) | `score_bracket` | `check_no_bottom_vs_bottom` |
| No same-country opponents round 1 (soft) | `score_bracket` | `check_country_conflicts_first_round` |
| Seeds/byes placed first | Phase 1, `bye_hierarchy` order | — |
| Byes evenly spread across the halves | Phase 1/1b/1c `assignment_quality_cost` | `check_bye_balance_halves` (reported; status `imbalanced`) |
| Winners, runners-up and 3rd places evenly spread across the halves | Same; decided by the winners' halves in Phase 1 | `check_placement_balance_halves` (reported; status `imbalanced`) |
| Each tier evenly over the two quarters of its half | Phase 1/1b/1c `assignment_quality_cost` | `check_placement_balance_quarters` (reported only) |
| With many byes, round two follows the round-one matchup rules | Phase 1/1b/1c `score_round_two` | `check_round_two_matchups` (reported only) |
| Country distribution across halves, then quarters | `score_bracket` + `_country_cost` | `check_country_balance_halves`, `check_country_balance_quarters` |
| No same-base opponents round 1 (soft) | `score_bracket` | `check_base_conflicts_first_round` |
| 2nd/3rd of a group separated until the quarterfinal | Phase 2 delta=1/2 logic | `check_quarter_group_separation` |
| 1st/4th same half, different quarter | Phase 2 delta=3 logic | `check_quarter_group_separation` |
| 1st/4th vs 2nd/3rd in opposite halves (relative to `top`) | Phase 1/1b/2 delta logic; hard gate in Phase 1c | `check_half_group_separation` |

## 6. Validation (`checks/`)

- **`validity_checker.py`** — pre-draw input checks: duplicate, missing and unused players; gender per competition; and `find_draw_data_errors`, which collects the structural checks: round flags (exactly one for bracket rows, none for group rows), `group_no`/`group_pos` set together, no duplicate player per class and stage, no duplicate `group_pos` per group, valid partners, one man and one woman per mixed pair, one consistent `#groups` per class, a seeding on every group-stage row, and at least `#groups` group-stage entries. All are fatal except the unused-player warning.
- **`group_checker.py`** — `check_country_distribution`, `check_base_uniqueness`, `get_qttr_violations`, `check_team_country_distribution`. Used both for scoring during the Monte Carlo search and for the post-draw report.
- **`bracket_checker.py`** — the separation, matchup, country, base and balance checks listed in the table in [§5](#5-algorithms-draw), the round-two family (`derive_round_two_matches`, `check_round_two_matchups`, `score_round_two`), and `score_bracket` / `score_bracket_tiers`.

Key invariants:
- **Tiers are relative to the bracket.** `_bracket_position_bounds` derives `top`/`bottom` from the `group_pos` values present, so a consolation (positions 4..6) is checked like a main draw (1..3). Callers that only see a partial bracket pass the true bounds via `bounds=`.
- **Three-tier guard.** `check_top_easy_first_round` and `check_no_bottom_vs_bottom` only apply with at least three tiers (singles). With two tiers "bottom" is the runner-up, and the rules would restate first-vs-first or flag forced pairings.
- **The score and `get_bracket_violations` agree**, because each guard lives inside its checker. The exceptions are the checks that are **reported but never scored** (`check_bye_balance_halves`, `check_placement_balance_halves`, `check_placement_balance_quarters`, `check_round_two_matchups`): no phase that optimises `score_bracket` can change them, so scoring them would only block the `score == 0` early exits. Phase 1/1b/1c enforce them instead.
- **Weight ladder.** Across tiers, `score_bracket_tiers` fixes the order in code. Within a tier, `validate_bracket_weights` checks `top_easy_opponent > bottom_vs_bottom` and `country_first > country_half > country_quarter`, and that the round-two weights sit between the country weights and the round-one matchup weights (they are added to one flat tiebreaker in Phase 1/1b/1c). `draw_bracket` logs a warning per problem; the order inside the hard tier is not checked.

## 7. Viewer / CLI UX (`viewer/`, `app/menu.py`)

- **Menu flow** (`app/menu.py`): `View` → `{Players | Groups | Bracket}` → `{Singles | Doubles | Mixed}` → class (→ main/consolation for brackets). Groups and brackets open the class's pre-exported HTML page in the browser, re-exporting only if the file is missing. For a bracket whose draw failed, the menu says so. Players is printed as a terminal table (`viewer/player_viewer.py`).
- **`viewer/viewer_shared.py`** holds what both viewers and exporters share: `open_in_browser` and `participant_display_fields`.
- **Group HTML** (`viewer/group_html_exporter.py`) — one self-contained file per class, `output/groups/{competition}_{class}_groups.html`. One group card per row, with an offline stepper through the draw history that opens on the final groups. Group snapshots are deltas (one swap/revert each), so the payload is delta-encoded: a `roster`, an `initial` state and small `steps`. `tests/test_group_html_exporter.py` replays the payload and asserts it lands on the drawn groups. `html_max_snapshots` caps the history by folding the oldest steps into `initial`.
- **Bracket HTML** (`viewer/bracket_html_exporter.py`) — one self-contained file per bracket, `output/brackets/{competition}_{class}_{type}_bracket.html`. It shows the **first round only**, grouped by quarter (Q1–Q4, plus 16-player segments for brackets over 64 players), with every snapshot embedded and an offline stepper. The strongest 25% of players are highlighted. A red notice follows the heading when the draw degraded or broke a hard rule.
- Both pages end with a provenance footer: app version, draw time, total run time, random seed and timestamp.

## 8. Configuration (`config/config.ini`, `core/config.py`)

`config/config.ini` is gitignored, so every machine keeps its own. Copy `config/config_template.ini` (which carries the code defaults) to `config/config.ini` before the first run. The CI build ships the template, so a local config with other weights or another seed draws the same input differently from the shipped exe.

`core.config.initialize_config(base_dir, args)` parses the file (or the one given with `--config`) once into the typed `Settings` dataclass, shared as `from core.config import settings` (for example `settings.bracket_draw.max_attempts`). It then seeds `random` from `random_seed` if set and configures logging from `log_level`. A missing key or an empty value keeps the default. An unknown key or section is logged as a warning, so a typo does not silently fall back to the default. A value that is not a whole number where one is expected stops the run with a `ConfigError` naming the key. The bracket weight order is checked once here (`validate_bracket_weights`), with a warning per problem.

Command-line arguments (`app/cli.py`, `--help` lists them) take precedence over the file for one run: `--players`, `--draw-input`, `--output`, `--seed` and `--log-level` override the matching keys (`core.config.apply_cli_overrides`), before `random` is seeded and logging is configured. `--output` does not move the HTML directories. `--no-html` skips the HTML export and leaves the HTML pages of earlier runs where they are (`archive_previous_outputs(include_html=False)`); `DrawResults.html_exported` is then False and the menu offers only Players. `--no-menu` exits after the draw with exit code 1 if it did not complete.

| Section | Key | Meaning |
|---|---|---|
| `[files]` | `draw_data_path`, `players_path`, `output_file_path` | Input/output file locations. |
| | `bracket_html_output_dir`, `group_html_output_dir` | HTML export directories (default `output/brackets`, `output/groups`). |
| `[settings]` | `log_level` | 10/20/30/40/50 = debug/info/warning/error/critical. |
| | `random_seed` | If set, makes the draw reproducible. |
| `[group_draw]` | `max_iterations`, `max_no_improvement_iterations`, `max_escape_attempts`, `max_seed_retries` | Monte Carlo tuning (see [§5](#5-algorithms-draw)). |
| | `country_violation_weight`, `team_country_violation_weight`, `base_violation_weight`, `qttr_violation_weight` | Weights for the group violation score. |
| | `html_max_snapshots` | Cap on the history embedded in the group HTML (default 20000). |
| `[bracket_draw]` | `max_attempts` | Per-quarter Monte Carlo attempts. |
| | `joint_batch_max_evaluations` | Budget for the joint batch assignment in Phase 1/1b. |
| | `half_split_weight`, `quarter_split_weight`, `first_vs_first_weight` | Hard tier. |
| | `top_easy_opponent_weight`, `bottom_vs_bottom_weight` | Matchup tier. Keep the first above the second. |
| | `country_first_weight`, `country_half_weight`, `country_quarter_weight`, `base_first_weight` | Distribution tier. Keep `country_first > country_half > country_quarter`. |
| | `round_two_first_vs_first_weight`, `round_two_top_easy_opponent_weight`, `round_two_bottom_vs_bottom_weight` | `score_round_two`. Must lie strictly between the highest country weight and the lowest round-one matchup weight. |
| | `round_two_country_first_weight` | Round-two same-country pairing, between `country_quarter_weight` and `country_half_weight`. |

The Phase 1 penalty ladder (see [§5](#5-algorithms-draw)) is deliberately not configurable, and neither is Phase 1c, which runs until no step improves.

## 9. Known Issues

- **The tests only exercise the default weights.** `tests/conftest.py` resets `settings` to the defaults before every test, so the weights a local `config/config.ini` sets are never tested. `validate_bracket_weights` does not check the hard tier's order.
- **Some tight layouts still take the degrade path.** Small or uneven shapes (for example 4 groups where one group lacks its 3rd, or 4-tier brackets with short groups) can end up in `_fill_residual_soft`. Some of these end clean, some keep a hard violation; all are flagged in the terminal, the report and the HTML.
- **Some `imbalanced` brackets are structurally forced.** For example, 3 groups of 3rd/4th places with one group short (5 players, 8 slots): the half holding two 3rd places and their byes is full, so both 4ths go to the other half. The report cannot tell a forced split from an avoidable one, so check `details` before redrawing.
- **`check_placement_balance_quarters` can be non-zero even when Phase 1/1b/1c did all they could**, because the tiers they do not place are decided by Phase 2's capacity buckets. It mostly affects small brackets where a quarter is one or two matches.
- **Module-level global state.** The registries in [§3](#3-core-data-model-models) are filled as a side effect of construction or of specific calls, and `settings` is a module-level object read by every module rather than passed in.

## 10. Build

PyInstaller (`hilmars_lostrommel.spec`) builds a single console executable from `hilmars_lostrommel.py`, bundling `readchar` via `collect_all`. The output goes to `dist/hilmars_lostrommel_v<version>/`, containing `hilmars_lostrommel_v<version>.exe` and `config/config.ini`.

The exe reads `config/config.ini` next to itself (`get_base_dir()` in `hilmars_lostrommel.py`), not from the onefile bundle, which is only extracted to a temp directory. The spec therefore rebuilds the versioned folder after `EXE()`: it moves the exe in and copies only `config/config.ini`. A local build ships the local config; CI copies `config/config_template.ini` to `config/config.ini` first, so the CI exe starts from the reviewed defaults.

CI (`.github/workflows/build-exe.yml`) runs on `v*` tags and uploads the versioned folder as a workflow artifact. When the repository variable `NEXTCLOUD_SHARE_URL` is set (a public share link with uploads allowed), it also uploads a zip over WebDAV. The zip contains `config/config.ini` only when `config/config_template.ini` changed since the previous `v*` tag, so a release does not overwrite the config users already keep in the share.
