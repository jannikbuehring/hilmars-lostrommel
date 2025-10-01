"""Checks related to group assignments in competitions."""
from collections import defaultdict
from models.player import players_by_start_number

def check_country_distribution(competition, groups):
	"""
	For each country, ensure the difference between the group with the most and least participants is at most 1.
	Returns a list of (competition_class, country, max_count, min_count, group_counts) for violations.
	"""
	violations = []
	for competition_class, group_data in groups.items():
		group_dict = group_data["group"]
		all_group_nos = set(group_dict.keys())
		# Build country counts per group
		country_group_counts = defaultdict(lambda: defaultdict(int))  # country -> group_no -> count
		for group_no, members in group_dict.items():
			for member in members:
				# Single or team
				a = players_by_start_number[member.start_number_a]
				country_group_counts[a.country][group_no] += 1
				if member.start_number_b is not None:
					b = players_by_start_number[member.start_number_b]
					country_group_counts[b.country][group_no] += 1
		# Determine allowed difference
		if competition == "doubles" or competition == "mixed":
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
				violations.append((competition_class, country, max(counts), min(counts), dict((g, group_counts.get(g, 0)) for g in all_group_nos)))
	return violations

def check_base_uniqueness(groups):
	"""
	Ensure no two opponents in a group have the same base.
	Returns a list of (competition_class, group_no, base, count) for violations.
	"""
	violations = []
	for competition_class, group_data in groups.items():
		group_dict = group_data["group"]
		for group_no, members in group_dict.items():
			# Track which bases are represented by which teams/players in this group
			base_to_teams = {}
			for member in members:
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
					violations.append((competition_class, group_no, base, len(team_list)))
	return violations

def get_qttr_distributions(groups):
	"""Check that the distribution of players without a QTTR rating is balanced across groups. Only for singles.
	Returns a map of group_no -> count of players without QTTR"""
	
	qttr_distribution = []
	for competition_class, group_data in groups.items():
		group_dict = group_data["group"]
		# Count players without QTTR per group
		no_qttr_counts = {}
		for group_no, members in group_dict.items():
			count_no_qttr = 0
			for member in members:
				a = players_by_start_number[member.start_number_a]
				if a.qttr is None or a.qttr == "" or a.qttr == "None":
					count_no_qttr += 1
				if member.start_number_b is not None:
					b = players_by_start_number[member.start_number_b]
					if b.qttr is None or b.qttr == "" or b.qttr == "None":
						count_no_qttr += 1
			no_qttr_counts[group_no] = count_no_qttr
		# Only append if there is a violation
		if no_qttr_counts:
			min_count = min(no_qttr_counts.values())
			max_count = max(no_qttr_counts.values())
			if max_count > 0:
				min_groups = [g for g, v in no_qttr_counts.items() if v == min_count]
				max_groups = [g for g, v in no_qttr_counts.items() if v == max_count]
				qttr_distribution.append((competition_class, min_count, min_groups, max_count, max_groups))
	return qttr_distribution