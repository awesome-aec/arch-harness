"""Geometry sanity: the model is buildable as drawn."""
import math

import pytest

from conftest import fail


@pytest.mark.rule(id="geometry/opening-fits-wall", kind="geometry")
def test_opening_fits_wall(model, door):
    """Geometry sanity (arch-harness): an opening lies within its host wall, along the wall (offset ≥ 0 and
    offset + width ≤ wall length) and in height (door height ≤ wall height). A failing door is never shrunk below
    its code minimum: raise or lengthen the wall instead."""
    walls = {w["id"]: w for w in model["walls"]}
    wall = walls.get(door["wall"])
    if wall is None:
        fail(f"door {door['id']} names a host wall {door['wall']} that does not exist")
    length = math.hypot(wall["x1"] - wall["x0"], wall["y1"] - wall["y0"])
    if door["offset"] < 0 or door["offset"] + door["width"] > length:
        fail(f"door {door['id']} ({door['offset']}+{door['width']} mm) does not fit wall {wall['id']} "
             f"({length:.0f} mm long)", wall_length=round(length), needed=door["offset"] + door["width"])
    if door["height"] > wall["height"]:
        fail(f"door {door['id']} height {door['height']} mm > wall {wall['id']} height {wall['height']} mm",
             wall_height=wall["height"], needed=door["height"])


@pytest.mark.rule(id="geometry/rooms-do-not-overlap", kind="geometry")
def test_rooms_do_not_overlap(space_pair):
    """Geometry sanity (arch-harness): two spaces on one storey share no floor area (touching edges allowed)."""
    a, b = space_pair
    dx = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    dy = min(a["y"] + a["d"], b["y"] + b["d"]) - max(a["y"], b["y"])
    if dx > 0 and dy > 0:
        fail(f"spaces {a['id']} and {b['id']} overlap by {dx} × {dy} mm", overlap_m2=dx * dy / 1e6)


@pytest.mark.rule(id="geometry/walls-keep-clear", kind="geometry")
def test_walls_keep_clear(wall_pair):
    """Geometry sanity (arch-harness): two parallel walls that face each other neither overlap nor stand closer
    than a door's clear width (DIN 18040-1 4.3.3.2: 90 cm) face to face; a narrower gap is a sliver nobody can
    enter or build. The generator gives such a rest to the room beside it."""
    from arch_harness.codes import MIN_CLEAR_BETWEEN_WALLS
    a, b = wall_pair
    across = (lambda w: w["y0"]) if a["y0"] == a["y1"] else (lambda w: w["x0"])
    clear = round(abs(across(a) - across(b)) - (a["thickness"] + b["thickness"]) / 2)
    if clear < MIN_CLEAR_BETWEEN_WALLS:
        what = "overlap" if clear < 0 else f"stand {clear} mm apart"
        fail(f"walls {a['id']} and {b['id']} {what} (at least {MIN_CLEAR_BETWEEN_WALLS} mm clear)",
             clear_mm=clear, required_mm=MIN_CLEAR_BETWEEN_WALLS)
