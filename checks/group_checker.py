"""Checks related to group assignments in competitions."""
from collections import defaultdict
from models.player import players_by_start_number

def _distribution_severity(counts):
	"""
	Number of entries outside the ideal band [floor(n/G), ceil(n/G)] summed over all groups.
	Used to weight violations by how uneven a distribution is, not just whether it is uneven.
	"""
	total = sum(counts)
	lo = total // len(counts)
	hi = -(-total // len(counts))
	return sum(max(0, c - hi) + max(0, lo - c) for c in counts)

def check_country_distribution(competition, groups):
	"""
	For each country, ensure the difference between the group with the most and least participants is at most 1.
	Returns a list of (country, max_count, min_count, group_counts, severity) for violations.
	severity is the number of players outside the ideal per-group band (at least 1).
	"""
	violations = []
	all_group_nos = set(groups.keys())
	# Build country counts per group
	country_group_counts = defaultdict(lambda: defaultdict(int))  # country -> group_no -> count
	for group_no, members in groups.items():
		for member in members:
			# Ignore empty slots
			if member.start_number_a is None or member.start_number_a == "EMPTY":
				continue
			# Single or team
			a = players_by_start_number[member.start_number_a]
			country_group_counts[a.country][group_no] += 1
			if member.start_number_b is not None:
				b = players_by_start_number[member.start_number_b]
				country_group_counts[b.country][group_no] += 1
	# Determine allowed difference
	if competition in ('D', 'M'):
		allowed_diff = 2
	else:
		allowed_diff = 1
	# For each country, check max-min <= allowed_diff, including groups with 0
	for country, group_counts in country_group_counts.items():
		# Fill in zeros for groups where country is not present
		counts = [group_counts.get(group_no, 0) for group_no in all_group_nos]
		if not counts:
			continue
		if max(counts) - min(counts) > allowed_diff:
			severity = max(1, _distribution_severity(counts))
			violations.append((country, max(counts), min(counts), dict((g, group_counts.get(g, 0)) for g in all_group_nos), severity))
	return violations

def check_base_uniqueness(groups):
	"""
	Ensure no two opponents in a group have the same base.
	Returns a list of (competition_class, group_no, base, count) for violations.
	"""
	violations = []

	for group_no, members in groups.items():
		# Track which bases are represented by which teams/players in this group
		base_to_teams = {}
		for member in members:
			# Ignore empty slots
			if member.start_number_a is None or member.start_number_a == "EMPTY":
				continue
			# For a team, collect all unique bases in the team
			bases = set()
			a = players_by_start_number[member.start_number_a]
			if a.base is not None and a.base != "None":
				bases.add(a.base)
			if member.start_number_b is not None:
				b = players_by_start_number[member.start_number_b]
				if b.base is not None and b.base != "None":
					bases.add(b.base)
			for base in bases:
				if base not in base_to_teams:
					base_to_teams[base] = []
				base_to_teams[base].append(member)
		for base, team_list in base_to_teams.items():
			if len(team_list) > 1:
				violations.append((group_no, base, len(team_list)))
	return violations

def get_qttr_violations(groups):
	"""
	Check for violations in the distribution of players without a QTTR rating across groups (singles only).
	Returns a list of (competition_class, group_no, count_no_qttr) for groups with players lacking QTTR, only if the distribution is unbalanced.
	"""
	violations = []

	no_qttr_counts = {}
	for group_no, members in groups.items():
		count_no_qttr = 0
		for member in members:
			if member.start_number_a is None or member.start_number_a == "EMPTY":
				continue
			a = players_by_start_number[member.start_number_a]
			if a.qttr is None or a.qttr == "" or a.qttr == "None":
				count_no_qttr += 1
		no_qttr_counts[group_no] = count_no_qttr
	if no_qttr_counts:
		min_count = min(no_qttr_counts.values())
		max_count = max(no_qttr_counts.values())
		if max_count > min_count + 1:
			for group_no, count in no_qttr_counts.items():
				if count > min_count + 1:
					violations.append((group_no, count, no_qttr_counts))
	return violations

def check_team_country_distribution(groups):
	"""
	For doubles/mixed: Checks that full-country teams (e.g. <Germany, Germany>) and half-country teams (e.g. <Germany, Other>) are evenly distributed across groups.
	Returns a list of violations: (team_type, country, min_count, max_count, group_counts, severity)
	severity is the number of teams outside the ideal per-group band (at least 1).
	"""
	violations = []

	# country -> group_no -> count for full-country teams
	full_country_counts = {}
	# country -> group_no -> count for half-country teams
	half_country_counts = {}
	for group_no, members in groups.items():
		for member in members:
			if member.start_number_a is None or member.start_number_a == "EMPTY" or member.start_number_b is None:
				continue
			a = players_by_start_number[member.start_number_a]
			b = players_by_start_number[member.start_number_b]
			if a.country == b.country:
				# Full-country team
				country = a.country
				if country not in full_country_counts:
					full_country_counts[country] = {}
				if group_no not in full_country_counts[country]:
					full_country_counts[country][group_no] = 0
				full_country_counts[country][group_no] += 1
			else:
				# Half-country teams: count for each country
				for country in (a.country, b.country):
					if country not in half_country_counts:
						half_country_counts[country] = {}
					if group_no not in half_country_counts[country]:
						half_country_counts[country][group_no] = 0
					half_country_counts[country][group_no] += 1
	# Check for violations in full-country teams
	for country, group_counts in full_country_counts.items():
		counts = [group_counts.get(group_no, 0) for group_no in groups.keys()]
		if counts:
			min_count = min(counts)
			max_count = max(counts)
			if max_count > min_count + 1:
				severity = max(1, _distribution_severity(counts))
				violations.append(("full-country", country, min_count, max_count, dict(group_counts), severity))
	# Check for violations in half-country teams
	for country, group_counts in half_country_counts.items():
		counts = [group_counts.get(group_no, 0) for group_no in groups.keys()]
		if counts:
			min_count = min(counts)
			max_count = max(counts)
			if max_count > min_count + 1:
				severity = max(1, _distribution_severity(counts))
				violations.append(("half-country", country, min_count, max_count, dict(group_counts), severity))
	return violations