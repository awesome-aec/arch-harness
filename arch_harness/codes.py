"""Code values shared by a generator and the rule that checks it: one home each."""


def abstandsflaeche(height: int) -> int:
    """MBO § 6 Abs. 5 Satz 1: depth 0,4 H, at least 3 m, in whole mm rounded up (never below the stated depth)."""
    return max(3000, -(-2 * height // 5))


# Geometry sanity (arch-harness, not a code paragraph): two parallel walls leave at least a door's clear width
# between their faces (DIN 18040-1 4.3.3.2: 90 cm), or the gap is a sliver nobody can enter or build.
MIN_CLEAR_BETWEEN_WALLS = 900
