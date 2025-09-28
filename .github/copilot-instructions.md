# Copilot Instructions for AI Agents

## Project Overview
- **Purpose:** Automates creation of group draws and knock-out brackets for table tennis tournaments.
- **Main entry point:** `hilmars_lostrommel.py` (or via built executable in `builds/`)
- **Key data:** Input files in `input/` (e.g., `players.csv`, `draw_input.csv`), configuration in `config.ini`.

## Architecture & Data Flow
- **Input/Output:**
  - Input: CSV files in `input/` (player and draw data)
  - Output: CSV files in `output/` (draw results, explanations)
- **Core modules:**
  - `models/`: Data models for players, teams, matches, groups, brackets
  - `data_io/`: Reading/writing input and output files
  - `draw/`: Algorithms for group and bracket drawing (e.g., backtracking for group assignment)
  - `viewer/`: Visualization and reporting (e.g., `group_viewer.py`, `bracket_viewer.py`)
  - `misc/`: Startup, menu, and initialization logic
- **Validation:**
  - `checks/validity_checker.py` runs data integrity checks before draw generation

## Developer Workflows
- **Run main program:**
  - `python hilmars_lostrommel.py` (ensure input files exist)
- **Build executable:**
  - Uses PyInstaller; see `.spec` file and `build/` output
- **Testing:**
  - No formal test suite detected; validate by running main script and checking output files
- **Debugging:**
  - Check logs/output in `output/` and `build/` directories

## Project-Specific Patterns
- **Backtracking:** Used for group assignment to ensure valid, fair draws
- **Config:** All runtime config in `config.ini` (not hardcoded)
- **Output explanations:** `output/output_explainer.md` documents output file structure
- **Separation of concerns:** Data models, IO, algorithms, and UI/view logic are in separate folders

## Integration & Dependencies
- **External:**
  - Standard Python 3.x, plus packages in `requirements.txt`
  - No external APIs; all data is local
- **Build:**
  - PyInstaller for packaging (see `hilmars_lostrommel.spec`)

## Examples
- To add a new draw algorithm, implement in `draw/`, update main logic in `hilmars_lostrommel.py`
- To change input format, update `data_io/input_reader.py` and document in `README.md`

---
For more details, see `README.md` and `output/output_explainer.md`.
