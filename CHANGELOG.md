# Changelog for hilmars-lostrommel

This project adheres to the guidelines of [semantic versioning](https://semver.org/)
and [keeps a changelog](https://keepachangelog.com).

## Unreleased

### Added

- A warning at startup for every unknown key or section in `config.ini`, so a misspelled key no longer silently falls back to its default
- Command-line options `--config`, `--players`, `--draw-input`, `--output`, `--seed` and `--log-level`, which override the config file for one run
- `--no-html` to skip the HTML export and leave the existing HTML pages untouched
- `--no-menu` to exit after the draw, with exit code 1 if it did not complete, and `--version`

### Changed

- A config value that is not a whole number where one is expected now stops the run with a message naming the key. Before, a bracket weight such as `1000.0` silently fell back to its default
- Every config key is now optional. A missing key uses the default value shown in `config_template.ini`
- The bracket weight order is checked once at startup instead of once per bracket, so each warning appears only once

### Deprecated

### Removed

### Fixed

### Security

## 1.4.0 - 2026-09-29

### Added

- A live status line below the spinner while groups and brackets are drawn. It shows the class and what the draw is doing right now, and it disappears when the section is done
- Bracket HTML pages for brackets with more than 64 players show a second side bar right of the Q1–Q4 bar. It splits the bracket into segments of 16 players, labelled `1 / 8` … `8 / 8` for a 128-player bracket

### Changed

- The message "Could not achieve perfect group draw" is now written to the log instead of the terminal, where it broke the spinner line. The "Validating group draws" step still lists every remaining violation.

### Removed

- The terminal views of groups and brackets. Choosing a class under Groups or Bracket now opens its HTML page directly, which has the same snapshot stepper.
- Config key `mode` (`normal`/`interactive`), which only switched between those terminal views.
- Config key `max_draw_phase`. The bracket draw always runs all phases.

## 1.3.0 - 2026-09-26

### Added

- Draw report status `imbalanced`: a bracket without hard violations whose byes, group winners, runners-up or 3rd places are split more than one apart over the two halves. It sits between `ok` and `violations`, is listed on the terminal (`… : imbalanced: byes 8/6 over the halves`) and marked on the bracket's HTML page. Some such splits are structurally forced; the `details` column says which counts are off.
- `check_placement_balance_halves` in `checks/bracket_checker.py`: the per-half count of each tier `top..top+2` (relative, so a consolation's 4th/5th/6th), reported as `placement_balance_halves`.
- CI uploads the build as a zip to a Nextcloud share when the repository variable `NEXTCLOUD_SHARE_URL` is set. The zip includes `config/config.ini` only if `config_template.ini` changed since the previous release.

### Changed

- The exe and its config are built into `dist/hilmars_lostrommel_v<version>/`, and the exe is named `hilmars_lostrommel_v<version>.exe`. Only `config.ini` is shipped next to it; `config_template.ini` and other files in `config/` are no longer copied.
- Bracket draw: a draw that ends on the degrade path is drawn once more without the new half balance, from the same random state, and the better result is kept (fewest hard violations, then bye-order breaks, then half imbalances). Such draws take about twice as long; all others are unaffected.

### Fixed

- Bracket draw, Phase 1: the rule "Freilose, Gruppenerste, Gruppenzweite und Gruppendritte gleichmäßig auf die Hälften verteilen" was not enforced where it is decided. The group winners' halves fix both splits, but Phase 1 only balanced the byes already on the board, so draws came out with byes 8/6 or winners 4/2 and were reported `ok`. Phase 1 now charges the split each winner layout commits the rest of the draw to, and its winner lookahead scores the splits still reachable.

## 1.2.1 - 2026-09-26

### Added

- New `config/config_template.ini` that lists every config key with an explanation and its default value, and says which keys are required.

### Changed

- Bracket half/quarter geometry and the rule for which quarters a group member may occupy now live in one module, `models/bracket_geometry.py`. The drawer's Phases 1b, 1c and 2, the bracket checker and the HTML viewer all use it, replacing four separate copies of the rule and three copies of the geometry.
- The Windows exe built by CI now ships `config_template.ini` as its `config.ini`, so it always starts with the documented defaults instead of whichever `config.ini` happens to be committed.

### Fixed

- Bracket draw, Phase 2: in a bracket with only 2 first-round matches, a group's 4th place was treated as unconstrained and could land in the half opposite its group winner. It now stays in the winner's half.
- Bracket draw, Phase 2: a group's runner-up without a residual 3rd place ignored a 3rd place that had already received a bye in Phase 1b, and could land in the same quarter as it. It now avoids that quarter.
- The quarter-separation check computed the half of a quarter as `quarter // 2`, which is wrong for 2-match brackets, so a 4th place in the wrong half went unreported there. In the same brackets a 2nd/3rd pair that cannot be split (the opposite half has only one quarter) is no longer reported as a quarter violation.

## 1.2.0 - 2026-09-25

### Added

- New `quarter_split_weight` key in `[bracket_draw]`, so the weight for quarter-group separation can be set in the config instead of being fixed at 200 (the default is still 200).

### Changed

- A bracket that took the best-effort path is only reported as "degraded" when the result still breaks a hard rule or gives byes out of seeding order. A best-effort draw that ends clean counts as a regular bracket. Byes out of seeding order are now listed (terminal, report details, HTML notice).
- Fewer brackets need the best-effort path: when players below the group winners get byes (e.g. the best 5th places of a consolation), the half balance now counts the extra slot each such bye takes, and the bye repair pass checks that every group's remaining 2nd/3rd still fits its quarter. On the 2026 input this removes the best-effort path from 9 of 12 affected brackets, including S M1 consolation.
- The group-winner placement now looks ahead so that winners of one country are not forced into the same half by a later placement step.
- The drawn brackets change for the same seed, also in later classes.
- Brackets are now compared by rule tier instead of by one weighted sum: hard rules (half/quarter group separation, winner vs winner) first, then the winner/bottom-tier matchups, then country and base. A higher tier always wins, however large the numbers below it; the weights only trade off rules within one tier.
- The best-effort fill for over-tight brackets ("degraded") is now a local search that can also move "player vs BYE" matches and byes within a placement tier, instead of random reshuffles. Group winners never move. A bye moves to a lower-seeded player of the same tier only when that removes a hard-rule violation.
- Because the degrade fill now uses the random generator differently, the same seed draws different brackets than before, also in later classes.
- Winner-vs-winner matches that the bracket cannot avoid (more top-placed players than matches, e.g. a consolation of only group thirds) are no longer hard-rule violations. They are shown as "unavoidable first-vs-first" in the HTML page, the report details and the new `first_vs_first_forced` / `round2_first_vs_first_forced` entries. Only matches above that minimum count as violations.

### Fixed

- brackets with no spare slots no longer end up with broken half/quarter group separations and byes out of seeding order. In a bracket that is completely full, each quarter must have exactly as many free slots as the 3rd places sent there, and the bye placement could leave one quarter a slot short. The bye repair pass can now move a player with a bye into the other quarter of the same half to fix that, so these brackets no longer need the best-effort path. On the 2026 input with the configured seed, no bracket takes the best-effort path any more. The drawn brackets change for the same seed, also in later classes.
- Countries in doubles/mixed brackets are spread evenly again when there are same-country teams (e.g. GER/GER). Such teams were excused on top of the doubles allowance, so a bracket with 5 country players in one half and 0 in the other counted as balanced. The country checks for halves and quarters now only use the doubles allowance.

## 1.1.0 - 2026-09-25

### Added

- New input validation checks for the draw data that abort the run before drawing. They reject:
  - bracket entries flagged for both or neither of main round / consolation
  - `group_no` given without `group_pos` (or the other way round)
  - the same player twice in a class
  - a duplicate `group_pos` within a group
  - doubles/mixed entries without a partner, singles entries with one, and self-pairs
  - mixed pairs that are not one man and one woman
  - missing or inconsistent `#groups` within a class
  - group-stage entries without a seeding
  - classes with fewer group-stage entries than groups, or `#groups` below 1
- A draw report next to the output CSV (`<output name>_report.csv`) with one row per group class and per bracket and a status of `ok`, `violations`, `degraded` or `failed`
- Brackets that fell back to a best-effort layout, or that break a hard rule (group separation in the halves or quarters, two group winners meeting in round one), are now listed in red on the terminal and marked at the top of their HTML page. Before, they were reported as "Successfully created"

### Changed

- At the start of every run, the previous run's output CSV, report and HTML files are moved to a `previous` folder next to the output CSV
- The output CSV is written to a temporary file first and then renamed, so a crash never leaves a half-written file

### Fixed

- Surrounding whitespace in input fields is now trimmed. Before, `"GER "` counted as a separate country and `"F "` caused a false wrong-competition error
- Consolation brackets now keep a group winner and the 2nd and 3rd placed of its group in opposite halves, and report it when they are not. Before, the check only looked at absolute group positions 1 to 4. In a consolation bracket (positions 4, 5, 6) the rule was never checked, and a repair step moved 5th and 6th placed players into their group winner's half
- The group draw now returns the best grouping found in each attempt instead of the last one. Before, accepting worse swaps to escape a local minimum could end the attempt on a worse grouping than one it had already found. Escapes are also limited again: the budget now resets only when a new best grouping is found
- The group draw history no longer shows outdated violations after a worse swap was accepted
- A class with no more group-stage entries than groups no longer crashes the group draw
- A failing group draw of one class no longer aborts the whole run. The class is reported as a warning and left out, and all other classes are still drawn and exported
- A run that fails part-way no longer leaves the previous run's output CSV and HTML in place looking current. The terminal now shows a red banner when the draw did not complete, and "View HTML" for a bracket whose draw failed no longer opens the previous run's page
- An output file that is currently open is now detected before drawing, instead of making the run fail after the whole draw
- One failing HTML export no longer skips the HTML of all later classes

## 1.0.2 - 2026-09-24

### Changed

- Improved the group draw country violation heuristic. The severity of a violation is now taken into account instead of counting only the number of violations

## 1.0.1 - 2026-09-08

### Changed

- Improved the group draw HTML output layout to make it more readable

## 1.0.0 - 2026-09-08

### Added

- Initial release: group draws and knock-out brackets (main and consolation) for singles, doubles and mixed, written to one combined CSV, with HTML pages and an interactive menu to browse the results