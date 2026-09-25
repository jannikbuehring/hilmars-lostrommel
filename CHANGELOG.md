# Changelog for hilmars-lostrommel

This projects adheres to the guidelines of [semantic versioning](https://semver.org/)
and [keeps a changelog](https://keepachangelog.com).

## Unreleased

### Added

- New `quarter_split_weight` key in `[bracket_draw]`, so the weight for quarter-group separation can be set in the config instead of being fixed at 200 (the default is still 200).

### Changed

- Brackets are now compared by rule tier instead of by one weighted sum: hard rules (half/quarter group separation, winner vs winner) first, then the winner/bottom-tier matchups, then country and base. A higher tier always wins, however large the numbers below it; the weights only trade off rules within one tier.
- The best-effort fill for over-tight brackets ("degraded") is now a local search that can also move "player vs BYE" matches and byes within a placement tier, instead of random reshuffles. Group winners never move. A bye moves to a lower-seeded player of the same tier only when that removes a hard-rule violation.
- Because the degrade fill now uses the random generator differently, the same seed draws different brackets than before, also in later classes.
- Winner-vs-winner matches that the bracket cannot avoid (more top-placed players than matches, e.g. a consolation of only group thirds) are no longer hard-rule violations. They are shown as "unavoidable first-vs-first" in the HTML page, the report details and the new `first_vs_first_forced` / `round2_first_vs_first_forced` entries. Only matches above that minimum count as violations.

### Deprecated

### Removed

### Fixed

- Countries in doubles/mixed brackets are spread evenly again when there are same-country teams (e.g. GER/GER). Such teams were excused on top of the doubles allowance, so a bracket with 5 country players in one half and 0 in the other counted as balanced. The country checks for halves and quarters now only use the doubles allowance.

### Security

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

- Initial release