# Output file columns

| Column | Applies to | Meaning |
|---|---|---|
| `S_D_M` | all draws | S for singles, D for doubles, M for mixed doubles |
| `class` | all draws | M1 (2, 3) for men 1 (2, 3), W1 (2, 3) for women 1 (2, 3), X1 (2, 3) for mixed 1 (2, 3) |
| `seeding` | group stage only | The seeding from the input. A higher value means a stronger entry (e.g. 1000 = best player), so a classic seeding number (1 = best) must be inverted first. Main round and consolation rows leave this column blank: the seeding is taken from the group-stage row of the same player or pair, which therefore has to exist. |
| `group_no` | all draws | Group number of the player or pair in the group stage (group stage: drawn by the tool; main round and consolation: taken from the input) |
| `group_pos` | all draws | Final position of the player or pair in their group (singles: usually 1 to 6; doubles/mixed: usually 1 to 4; group stage: drawn by the tool; main round and consolation: taken from the input) |
| `for_main_round` | all draws | Input: 1 for the main round, otherwise blank or 0. Output: True in main round rows, False in consolation rows, blank in group-stage rows |
| `for_consolation` | all draws | Input: 1 for the consolation, otherwise blank or 0. Output: True in consolation rows, False in main round rows, blank in group-stage rows |
| `draw_number` | main round and consolation | The position in the knock-out bracket, so the bracket size is always a power of 2. In a 16-player bracket it is a number from 1 to 16, and the rows are ordered by it. |
| `startnumber_A` | all draws | Start number from the players file; singles: the player's start number, doubles/mixed: player A's start number; blank for a bye (see `is_bye`) |
| `last_name_A` | all draws | Last name from the players file; singles: of the player, doubles/mixed: of player A |
| `country_A` | all draws | Country from the players file; singles: of the player, doubles/mixed: of player A |
| `PPP_chapter_A` | all draws | PPP chapter (training base) from the players file; singles: of the player, doubles/mixed: of player A |
| `startnumber_B` | doubles and mixed | Player B's start number from the players file |
| `last_name_B` | doubles and mixed | Player B's last name from the players file |
| `country_B` | doubles and mixed | Player B's country from the players file |
| `PPP_chapter_B` | doubles and mixed | Player B's PPP chapter from the players file |
| `is_bye` | main round and consolation | True if the position is a bye (then only `S_D_M`, `class`, `for_main_round`, `for_consolation` and `draw_number` are filled), otherwise False; blank in group-stage rows |
