# Changelog for hilmars-lostrommel

This projects adheres to the guidelines of [semantic versioning](https://semver.org/)
and [keeps a changelog](https://keepachangelog.com).

## Unreleased

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

### Changed

### Deprecated

### Removed

### Fixed

- Surrounding whitespace in input fields is now trimmed. Before, `"GER "` counted as a separate country and `"F "` caused a false wrong-competition error
- The group draw now returns the best grouping found in each attempt instead of the last one. Before, accepting worse swaps to escape a local minimum could end the attempt on a worse grouping than one it had already found. Escapes are also limited again: the budget now resets only when a new best grouping is found
- The group draw history no longer shows outdated violations after a worse swap was accepted
- A class with no more group-stage entries than groups no longer crashes the group draw
- A failing group draw of one class no longer aborts the whole run. The class is reported as a warning and left out, and all other classes are still drawn and exported

### Security

## 1.0.2 - 2026-09-24

### Changed

- Improved the group draw country violation heuristic. The severity of a violation is now taken into account instead of counting only the number of violations

## 1.0.1 - 2026-09-08

### Changed

- Improved the group draw HTML output layout to make it more readable


## 1.0.0 - 2026-09-08

- Initial release