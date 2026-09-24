"""Tests for checks/group_checker.py."""
from models.player import Player
from models.draw_data import DrawDataRow
from checks.group_checker import check_country_distribution, check_team_country_distribution

from tests.conftest import populate_players_by_start_number


def build_single_groups(country_counts_per_group):
    """Build singles groups from a list of {country: count} dicts, one per group."""
    groups = {}
    start_number = 1
    for group_no, country_counts in enumerate(country_counts_per_group, start=1):
        groups[group_no] = []
        for country, count in country_counts.items():
            for _ in range(count):
                Player(start_number, f'First{start_number}', f'Last{start_number}', country, f'Base{start_number}', 'F', 1000)
                groups[group_no].append(DrawDataRow('S', 'S M3', '', '', '', '', True, False, start_number, ''))
                start_number += 1
    populate_players_by_start_number()
    return groups


def test_country_distribution_even_has_no_violation():
    groups = build_single_groups([{'GER': 3}, {'GER': 3}, {'GER': 3}, {'GER': 3}])

    assert check_country_distribution('S', groups) == []


def test_country_distribution_severity_grows_with_unevenness():
    severe = build_single_groups([{'GER': 6}, {'GER': 3}, {'GER': 2}, {'GER': 1}])
    severe_violations = check_country_distribution('S', severe)
    mild = build_single_groups([{'GER': 4}, {'GER': 3}, {'GER': 3}, {'GER': 2}])
    mild_violations = check_country_distribution('S', mild)

    assert [v[0] for v in severe_violations] == ['GER']
    assert severe_violations[0][4] == 6
    assert [v[0] for v in mild_violations] == ['GER']
    assert mild_violations[0][4] == 2


def test_country_distribution_severity_counts_missing_players():
    # 5 players over 4 groups: band is [1, 2]; the empty group is one below the band
    groups = build_single_groups([{'GER': 2}, {'GER': 2}, {'GER': 1}, {'SWE': 1}])

    violations = check_country_distribution('S', groups)

    assert [(v[0], v[4]) for v in violations] == [('GER', 1)]


def test_team_country_distribution_severity_at_least_one():
    groups = {}
    start_number = 1
    for group_no, team_count in enumerate([3, 1], start=1):
        groups[group_no] = []
        for _ in range(team_count):
            Player(start_number, 'A', 'A', 'GER', 'BaseA', 'F', 1000)
            Player(start_number + 1, 'B', 'B', 'GER', 'BaseB', 'M', 1000)
            groups[group_no].append(DrawDataRow('M', 'M M', '', '', '', '', True, False, start_number, start_number + 1))
            start_number += 2
    populate_players_by_start_number()

    violations = check_team_country_distribution(groups)

    assert [(v[0], v[1], v[5]) for v in violations] == [('full-country', 'GER', 2)]
