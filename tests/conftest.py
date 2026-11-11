"""Shared fixtures for the unit tests (not the rules: those live in arch_harness/rules)."""
import copy
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


@pytest.fixture
def clinic_design_path():
    return EXAMPLES / "clinic" / "DESIGN.md"


@pytest.fixture
def tight_design_path():
    return EXAMPLES / "tight-site" / "DESIGN.md"


def tiny_model():
    """A hand-built one-storey model in mm that passes every rule: two rooms off a corridor."""
    return {
        "schema": "arch-harness.model/0.1",
        "units": "mm",
        "project": {"name": "tiny"},
        "site": {"width": 30000, "depth": 30000},
        "building": {"x": 5000, "y": 5000, "w": 10000, "d": 12000, "height": 3000},
        "programme": [
            {"name": "Room A", "area_m2": 20, "count": 1, "storey": "any"},
            {"name": "Room B", "area_m2": 20, "count": 1, "storey": "any"},
        ],
        "parameters": {},
        "storeys": [{"id": "L0", "name": "Storey 0", "elevation": 0, "height": 3000}],
        "spaces": [
            {"id": "L0-S01", "name": "Room A", "programme": "Room A", "storey": "L0", "use": "room",
             "x": 0, "y": 0, "w": 4000, "d": 5000},
            {"id": "L0-S02", "name": "Room B", "programme": "Room B", "storey": "L0", "use": "room",
             "x": 4115, "y": 0, "w": 4000, "d": 5000},
            {"id": "L0-C", "name": "Corridor", "programme": None, "storey": "L0", "use": "corridor",
             "x": 0, "y": 5115, "w": 8115, "d": 1500},
        ],
        "walls": [
            {"id": "L0-W01", "storey": "L0", "x0": 0, "y0": 5057, "x1": 4000, "y1": 5057,
             "thickness": 115, "height": 3000, "external": False},
            {"id": "L0-W02", "storey": "L0", "x0": 4115, "y0": 5057, "x1": 8115, "y1": 5057,
             "thickness": 115, "height": 3000, "external": False},
            {"id": "L0-W09", "storey": "L0", "x0": 0, "y0": 6672, "x1": 8115, "y1": 6672,
             "thickness": 115, "height": 3000, "external": False},  # the corridor's far side, 1500 mm clear
        ],
        "doors": [
            {"id": "L0-D01", "storey": "L0", "wall": "L0-W01", "offset": 1500, "width": 900, "height": 2050,
             "space": "L0-S01"},
            {"id": "L0-D02", "storey": "L0", "wall": "L0-W02", "offset": 1500, "width": 900, "height": 2050,
             "space": "L0-S02"},
        ],
        "slabs": [],
    }


@pytest.fixture
def model():
    return copy.deepcopy(tiny_model())


@pytest.fixture
def write_model(tmp_path):
    def _write(m):
        p = tmp_path / "model.json"
        p.write_text(json.dumps(m))
        return p
    return _write
