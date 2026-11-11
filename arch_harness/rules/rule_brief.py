"""Brief conformance: the model delivers the programme written in DESIGN.md."""
import pytest

from conftest import fail


@pytest.mark.rule(id="brief/room-exists-at-area", kind="brief", label="Every room at its programme area")
def test_room_exists_at_area(model, required_room):
    """Brief conformance (DESIGN.md, section Programme): every programme room exists, as often as its count says
    (storey 'each' = once per storey), with a clear floor area of at least its programme area."""
    name, k, area_m2 = required_room
    spaces = sorted((s for s in model["spaces"] if s.get("programme") == name), key=lambda s: s["id"])
    if len(spaces) < k:
        fail(f"programme room '{name}' #{k} is missing ({len(spaces)} placed)", placed=len(spaces))
    s = spaces[k - 1]
    actual = round(s["w"] * s["d"] / 1e6, 2)
    if actual < area_m2:
        fail(f"'{name}' #{k} ({s['id']}) has {actual} m² < {area_m2} m²", actual_m2=actual, required_m2=area_m2)


@pytest.mark.rule(id="brief/room-proportion", kind="brief", from_brief=True, label="No room longer than {max_room_ratio} : 1")
def test_room_proportion(model, shaped_room):
    """Brief conformance (DESIGN.md, Constraints `max_room_ratio`): no room is more than that many times as long as
    it is wide; a sliver room is hard to furnish and to light."""
    limit, s = model["parameters"]["max_room_ratio"], shaped_room
    ratio = max(s["w"], s["d"]) / min(s["w"], s["d"])
    if ratio > limit + 1e-9:
        fail(f"{s['name']} ({s['id']}) is {s['w'] / 1000:.2f} × {s['d'] / 1000:.2f} m, {ratio:.1f} : 1 > {limit} : 1",
             ratio=round(ratio, 2), max_ratio=limit)


def _next_to(a: dict, b: dict, wall: int) -> bool:
    """Same storey, and either side by side through one partition or facing across the corridor (1 m of overlap)."""
    if a["storey"] != b["storey"] or a is b:
        return False
    overlap = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    if a["y"] == b["y"]:
        return -overlap <= wall + 1
    return overlap >= 1000


@pytest.mark.rule(id="brief/adjacency", kind="brief", from_brief=True, label="Each room next to the room the brief names")
def test_adjacency(model, adjacent_pair):
    """Brief conformance (DESIGN.md, section Adjacency): each room stated there lies next to the room it names
    (sharing a partition, or facing it across the corridor), or, for `entrance`, in the first bay inside the
    entrance on the ground storey."""
    room, k, other = adjacent_pair
    p, names = model["parameters"], {e["name"] for e in model["programme"]}
    for name in {room, other} - {"entrance"} - names:
        fail(f"'{name}' in the Adjacency section is not a programme room", next_to=other)
    spaces = sorted((s for s in model["spaces"] if s.get("programme") == room), key=lambda s: s["id"])
    if len(spaces) < k:
        fail(f"'{room}' #{k} is not placed, so it cannot be next to {other}", next_to=other)
    space = spaces[k - 1]
    if other == "entrance":
        inner_west = model["building"]["x"] + p.get("exterior_wall", 0)
        if not (space["storey"] == model["storeys"][0]["id"] and space["x"] == inner_west):
            fail(f"{space['name']} ({space['id']}) is not in the first bay inside the entrance", next_to=other)
        return
    if not any(s.get("programme") == other and _next_to(space, s, p["interior_wall"]) for s in model["spaces"]):
        fail(f"{space['name']} ({space['id']}) is not next to a {other}", next_to=other)


@pytest.mark.rule(id="brief/room-not-oversized", kind="brief", from_brief=True,
                  label="No room over {max_room_oversize:.0%} of its programme area")
def test_room_not_oversized(model, sized_room):
    """Brief conformance (DESIGN.md, Constraints `max_room_oversize`): no room is larger than its programme area
    times that factor; a room drawn far beyond its brief is floor area paid for and not used."""
    s = sized_room
    brief = next(e["area_m2"] for e in model["programme"] if e["name"] == s["programme"])
    actual, cap = round(s["w"] * s["d"] / 1e6, 2), round(brief * model["parameters"]["max_room_oversize"], 2)
    if actual > cap:
        fail(f"{s['name']} ({s['id']}) has {actual} m², more than {cap} m² ({brief} m² in the brief)",
             actual_m2=actual, max_m2=cap)
