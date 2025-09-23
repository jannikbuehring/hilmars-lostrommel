# hilmars-lostrommel

A program for creating (table tennis) group draws and knock-out brackets

# Roadmap

- [x] Interactive mode for easy debugging
- [ ] Bracket draws
- [ ] Export 


# Configuration

To change config values, change values in the config.ini file

Configurable values:

# How to use

Prerequisites:

- players.csv
- draw_input.csv

In the beginning, there are some validity checks to make sure the data is correct
- No players have the same start number twice
- All players from the draw data exist
- All players are at least in one competition
- Male players only partake in male competitions, female players only partake in female competitions

# Group draw

- Backtracking algorithm is used to try all possible combinations if necessary

# Bracket draw