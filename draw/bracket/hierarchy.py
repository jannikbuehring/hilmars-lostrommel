"""The seeded-slot hierarchy the group winners and byes are placed down."""


def bye_hierarchy(num_slots: int) -> list[list[int]]:
    """Return hierarchical subdivisions for seeded slot placement.

    Level 0 is slot 1, level 1 the last slot, and every further level the slots
    at both sides of the next finer block boundaries -- the strongest slots first.
    """
    if num_slots < 2 or (num_slots & (num_slots - 1)) != 0:
        raise ValueError("num_slots must be a power of two >= 2")

    levels = num_slots.bit_length() - 1
    groups: list[list[int]] = [[1], [num_slots]]

    for level in range(1, levels):
        block = num_slots // (2**level)
        group: list[int] = []
        for idx in range(1, 2**level):
            if idx % 2 == 1:
                boundary = idx * block
                group.append(boundary)
                group.append(boundary + 1)
        groups.append(group)

    return groups


def winner_level_slots(hierarchy_groups, top_sorted):
    """id(winner) -> the hierarchy level (slot list) Phase 1 places it on.

    The winners fill the levels in seeding order, as many per level as it has
    slots; the returned lists are the very objects in *hierarchy_groups*.
    """
    level_slots = {}
    start = 0
    for hierarchy_group in hierarchy_groups:
        for participant in top_sorted[start : start + len(hierarchy_group)]:
            level_slots[id(participant)] = hierarchy_group
        start += len(hierarchy_group)
    return level_slots
