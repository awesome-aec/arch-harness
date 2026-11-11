"""Massing from the brief: footprint from the site, storeys from the programme area. Deterministic.

The section is double-loaded: a straight corridor with rooms on both sides, the core ('each' rooms) at the west
end of every storey so it stacks. The footprint is the buildable area (site minus the MBO § 6 Abstandsfläche for
the building height) shortened to the length the programme needs; storeys are the fewest that hold the
programme within max_storeys. The south strip is `room_depth` deep, the north strip `room_depth_north` (the same
unless stated); with two depths each room but the core takes first the side that makes it squarer. `order` (room names, comma
separated, one room per mention) places those rooms first; the rest follow in programme order. A wall stops at the underside of the slab above it (storey height minus slab). What does not fit is left out and said in `notes`: the rules then report it.
"""
from __future__ import annotations

import math

from ..codes import MIN_CLEAR_BETWEEN_WALLS
from ..codes import abstandsflaeche as setback  # the rule in rules/ checks the same function

GENERATOR = {"name": "massing-double-loaded", "version": "0.1"}
# Design defaults (not code minimums): used only when DESIGN.md does not state the parameter.
DEFAULTS = {"max_storeys": 3, "storey_height": 3200, "corridor_width": 1500, "door_width": 900, "door_height": 2050,
            "room_depth": 5000, "exterior_wall": 365, "interior_wall": 115, "slab_thickness": 220,
            "structure": "masonry"}
STEP = 100  # room widths and building length snap to 100 mm


def _depths(p: dict) -> tuple[int, int]:
    return p["room_depth"], p.get("room_depth_north", p["room_depth"])


def _instances(design: dict, n_storeys: int, order: str = "") -> list[dict]:
    each, fixed, anywhere = [], [], []
    for entry in design["programme"]:
        if entry["storey"] == "each":
            for st in range(n_storeys):
                for _ in range(entry["count"]):
                    each.append({"name": entry["name"], "area_m2": entry["area_m2"], "storey": st, "each": True})
        else:
            target = fixed if entry["storey"].isdigit() else anywhere
            for _ in range(entry["count"]):
                st = int(entry["storey"]) if entry["storey"].isdigit() else None
                target.append({"name": entry["name"], "area_m2": entry["area_m2"], "storey": st})
    rest = fixed + anywhere   # fixed before any storey, programme order
    ordered = []
    for name in (n.strip() for n in str(order or "").split(",") if n.strip()):
        room = next((r for r in rest if r["name"] == name), None)   # one room per mention
        if room is not None:
            rest.remove(room)
            ordered.append(room)
    return each + ordered + rest


def _room_width(area_m2: float, depth: int, max_ratio: float | None = None) -> int:
    """The width that gives the area at this depth; with a ratio cap in the brief, never narrower than depth / cap."""
    w = math.ceil(area_m2 * 1e6 / depth / STEP) * STEP
    return max(w, math.ceil(depth / max_ratio / STEP) * STEP) if max_ratio else w


def _assign(rooms: list[dict], n_storeys: int, inner_length: int, p: dict):
    """First fit into strips (storey, side). Returns ({(storey, side): [room, ...]}, [unplaced])."""
    used = {(st, side): 0 for st in range(n_storeys) for side in (0, 1)}
    strips = {k: [] for k in used}
    unplaced = []
    depths = _depths(p)
    for room in rooms:
        widths = [_room_width(room["area_m2"], d, p.get("max_room_ratio")) for d in depths]
        squarer = sorted((0, 1), key=lambda i: max(widths[i], depths[i]) / min(widths[i], depths[i]))
        sides = (0, 1) if depths[0] == depths[1] or room.get("each") else squarer  # the core stays south-west
        storeys = [room["storey"]] if room["storey"] is not None else range(n_storeys)
        for st in storeys:
            if st >= n_storeys:
                continue
            for side in sides:
                w = widths[side]
                gap = p["interior_wall"] if strips[(st, side)] else 0
                if used[(st, side)] + gap + w <= inner_length:
                    used[(st, side)] += gap + w
                    strips[(st, side)].append(dict(room, w=w))
                    break
            else:
                continue
            break
        else:
            unplaced.append(room)
    return strips, unplaced


def generate(design: dict, params: dict) -> dict:
    p = {**DEFAULTS, **params}
    te, ti, cw = p["exterior_wall"], p["interior_wall"], p["corridor_width"]
    sh = p["storey_height"]
    section = 2 * te + sum(_depths(p)) + 2 * ti + cw
    site = design["site"]
    notes = []
    choice = None
    candidates = [p["storeys"]] if "storeys" in p else range(1, p["max_storeys"] + 1)
    for n in candidates:
        s = setback(n * sh)
        lmax, bmax = site["width"] - 2 * s, site["depth"] - 2 * s
        if section > bmax:
            notes.append(f"{n} storey(s): the double-loaded section needs {section} mm but the buildable depth is "
                         f"{bmax} mm (site depth {site['depth']} mm minus 2 × Abstandsfläche {s} mm)")
            continue
        rooms = _instances(design, n, p.get("order"))
        strips, unplaced = _assign(rooms, n, lmax - 2 * te, p)
        choice = (n, s, lmax, bmax, rooms, strips, unplaced)
        if not unplaced:
            break
        area = sum(r["area_m2"] for r in unplaced)
        notes.append(f"{n} storey(s): {len(unplaced)} room(s) ({area:.0f} m²) do not fit in the buildable length "
                     f"{lmax} mm")
    if choice is None:  # nothing fits at all: an empty massing on the plot, the notes say why
        n = candidates[0] if "storeys" in p else 1
        s = setback(n * sh)
        return _model(design, p, n, site, s, s, site["width"] - 2 * s, max(site["depth"] - 2 * s, 0), {}, notes)
    n, s, lmax, bmax, rooms, strips, unplaced = choice
    if not unplaced:  # shorten to the length the programme needs (smallest that still fits, 100 mm steps)
        lo, hi = 2 * te + STEP, lmax
        while lo < hi:
            mid = (lo + hi) // 2 // STEP * STEP
            if mid <= lo:
                mid = lo
            if not _assign(rooms, n, mid - 2 * te, p)[1]:
                hi = mid
            else:
                lo = mid + STEP
        length = hi
        strips, _ = _assign(rooms, n, length - 2 * te, p)
    else:
        length = lmax
        for r in unplaced:
            notes.append(f"not placed: {r['name']} ({r['area_m2']} m²)")
    bx = s + (lmax - length) // 2 // 10 * 10
    by = s + (bmax - section) // 2 // 10 * 10
    return _model(design, p, n, site, bx, by, length, section, strips, notes)


def _model(design, p, n, site, bx, by, length, depth, strips, notes) -> dict:
    te, ti, cw, sh = p["exterior_wall"], p["interior_wall"], p["corridor_width"], p["storey_height"]
    rd, rdn = _depths(p)
    storeys = [{"id": f"L{i}", "name": f"Storey {i}", "elevation": i * sh, "height": sh} for i in range(n)]
    spaces, walls, doors, slabs = [], [], [], []
    rooms_built = bool(strips)
    for i in range(n):
        sid, z = f"L{i}", i * sh
        wn = iter(range(1, 10_000))
        def wall(x0, y0, x1, y1, t, external):
            w = {"id": f"{sid}-W{next(wn):03d}", "storey": sid, "x0": bx + x0, "y0": by + y0, "x1": bx + x1,
                 "y1": by + y1, "thickness": t, "height": sh - p["slab_thickness"], "external": external}
            walls.append(w)
            return w
        h = te // 2
        ext = [wall(h, h, length - h, h, te, True), wall(length - h, h, length - h, depth - h, te, True),
               wall(h, depth - h, length - h, depth - h, te, True), wall(h, h, h, depth - h, te, True)]
        slabs.append({"id": f"{sid}-SLAB", "storey": sid, "x": bx, "y": by, "w": length, "d": depth, "z": z,
                      "thickness": p["slab_thickness"], "role": "floor"})
        if not rooms_built:
            continue
        cy0 = te + rd + ti
        spaces.append({"id": f"{sid}-C", "name": "Corridor", "programme": None, "storey": sid, "use": "corridor",
                       "x": bx + te, "y": by + cy0, "w": length - 2 * te, "d": cw})
        if i == 0:
            west = ext[3]
            offset = cy0 + cw // 2 - p["door_width"] // 2 - h
            doors.append({"id": f"{sid}-D00", "storey": sid, "wall": west["id"], "offset": offset,
                          "width": p["door_width"], "height": p["door_height"], "space": f"{sid}-C"})
        k = 0
        for side in (0, 1):
            y0 = te if side == 0 else te + rd + 2 * ti + cw
            wall_y = te + rd + ti // 2 if side == 0 else te + rd + ti + cw + ti // 2
            sd = rd if side == 0 else rdn
            x = te
            strip = strips.get((i, side), [])
            for j, room in enumerate(strip):
                k += 1
                rid = f"{sid}-S{k:02d}"
                w = room["w"]
                rest = length - te - (x + w)
                if j == len(strip) - 1 and rest < ti + MIN_CLEAR_BETWEEN_WALLS:
                    w += rest   # a rest too narrow to enter goes to the last room, not to a doubled wall
                spaces.append({"id": rid, "name": room["name"], "programme": room["name"], "storey": sid,
                               "use": "room", "x": bx + x, "y": by + y0, "w": w, "d": sd})
                host = wall(x, wall_y, x + w, wall_y, ti, False)
                doors.append({"id": f"{sid}-D{k:02d}", "storey": sid, "wall": host["id"],
                              "offset": (w - p["door_width"]) // 2, "width": p["door_width"],
                              "height": p["door_height"], "space": rid})
                if x + w + ti <= length - te:   # partition to the next room (or to the empty rest of the strip)
                    wall(x + w + ti // 2, y0, x + w + ti // 2, y0 + sd, ti, False)
                x += w + ti
    slabs.append({"id": "ROOF", "storey": f"L{n - 1}", "x": bx, "y": by, "w": length, "d": depth, "z": n * sh,
                  "thickness": p["slab_thickness"], "role": "roof"})
    return {
        "schema": "arch-harness.model/0.1", "units": "mm", "generator": GENERATOR,
        "project": {"name": design["name"]},
        "site": {"width": site["width"], "depth": site["depth"]},
        "building": {"x": bx, "y": by, "w": length, "d": depth, "height": n * sh},
        "programme": design["programme"], "adjacency": design.get("adjacency", []), "parameters": p, "notes": notes,
        "storeys": storeys, "spaces": spaces, "walls": walls, "doors": doors, "slabs": slabs,
    }
