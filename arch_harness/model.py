"""The JSON model (schema/model.schema.json): canonical text, a structural check, and solids.

`solids()` is the geometry seam: every render (OpenUSD, IFC, viewer) builds from these axis-aligned boxes.
Exact B-rep geometry (NVIDIA usd-brep, milestone 2) replaces this function, not the model.
"""
from __future__ import annotations

import json
import pathlib

SCHEMA_PATH = pathlib.Path(__file__).parent / "schema" / "model.schema.json"
SCHEMA_ID = "arch-harness.model/0.1"


def dumps_model(model: dict) -> str:
    """Canonical text: sorted keys, one-space indent, trailing newline: stable git diffs."""
    return json.dumps(model, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def write_model(model: dict, path) -> pathlib.Path:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_model(model), encoding="utf-8")
    return path


def read_model(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def validate_model(model: dict) -> None:
    """Check the schema's required keys, consts, enums and integer types (a subset of JSON Schema, no dependency)."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def check(value, sch, where):
        if "const" in sch and value != sch["const"]:
            raise ValueError(f"{where}: expected {sch['const']!r}, got {value!r}")
        if "enum" in sch and value not in sch["enum"]:
            raise ValueError(f"{where}: {value!r} not in {sch['enum']}")
        t = sch.get("type")
        if t == "integer" and not isinstance(value, int):
            raise ValueError(f"{where}: expected an integer (mm), got {value!r}")
        if t == "object":
            if not isinstance(value, dict):
                raise ValueError(f"{where}: expected an object")
            for key in sch.get("required", []):
                if key not in value:
                    raise ValueError(f"{where}: missing '{key}'")
            for key, sub in sch.get("properties", {}).items():
                if key in value:
                    check(value[key], sub, f"{where}.{key}")
        if t == "array":
            if not isinstance(value, list):
                raise ValueError(f"{where}: expected an array")
            for i, item in enumerate(value):
                check(item, sch.get("items", {}), f"{where}[{i}]")

    check(model, schema, "model")


def required_rooms(model: dict) -> list[tuple[str, int, float]]:
    """Programme instances (name, k, area): storey 'each' means the count per storey."""
    out = []
    n_storeys = max(len(model.get("storeys", [])), 1)
    for entry in model.get("programme", []):
        count = entry["count"] * (n_storeys if entry["storey"] == "each" else 1)
        out += [(entry["name"], k, entry["area_m2"]) for k in range(1, count + 1)]
    return out


def storey_z(model: dict) -> dict[str, int]:
    return {s["id"]: s["elevation"] for s in model["storeys"]}


def solids(model: dict) -> list[dict]:
    """Axis-aligned boxes (mm) for every physical element and space, sorted by id."""
    z = storey_z(model)
    out = []
    walls = {w["id"]: w for w in model["walls"]}
    for w in model["walls"]:
        t2 = w["thickness"] / 2
        x0, x1 = sorted((w["x0"], w["x1"]))
        y0, y1 = sorted((w["y0"], w["y1"]))
        if y0 == y1:   # runs along x
            box = (x0, y0 - t2, x1, y1 + t2)
        else:          # runs along y
            box = (x0 - t2, y0, x1 + t2, y1)
        out.append({"id": w["id"], "kind": "wall", "storey": w["storey"], "external": w["external"],
                    "min": [box[0], box[1], z[w["storey"]]], "max": [box[2], box[3], z[w["storey"]] + w["height"]]})
    for d in model["doors"]:
        w = walls[d["wall"]]
        t2 = w["thickness"] / 2 + 10   # a little proud of the wall so it shows
        if w["y0"] == w["y1"]:
            sx = min(w["x0"], w["x1"]) + d["offset"]
            box = (sx, w["y0"] - t2, sx + d["width"], w["y0"] + t2)
        else:
            sy = min(w["y0"], w["y1"]) + d["offset"]
            box = (w["x0"] - t2, sy, w["x0"] + t2, sy + d["width"])
        out.append({"id": d["id"], "kind": "door", "storey": d["storey"], "wall": d["wall"],
                    "min": [box[0], box[1], z[d["storey"]]], "max": [box[2], box[3], z[d["storey"]] + d["height"]]})
    for s in model["slabs"]:
        out.append({"id": s["id"], "kind": "slab", "storey": s["storey"], "role": s["role"],
                    "min": [s["x"], s["y"], s["z"] - s["thickness"]], "max": [s["x"] + s["w"], s["y"] + s["d"], s["z"]]})
    for s in model["spaces"]:
        out.append({"id": s["id"], "kind": "space", "storey": s["storey"], "use": s["use"], "name": s["name"],
                    "min": [s["x"], s["y"], z[s["storey"]]],
                    "max": [s["x"] + s["w"], s["y"] + s["d"], z[s["storey"]] + 50]})
    return sorted(out, key=lambda b: b["id"])
