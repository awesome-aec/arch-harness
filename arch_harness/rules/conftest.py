"""Rule harness: load the model, parametrize rules over its elements, record one result per element.

A rule test requests one of these arguments and runs once per element:
  door, wall, corridor, room (spaces with use 'room'), side (the four building sides),
  space_pair (two spaces on one storey), required_room (one programme instance).
A rule fails by raising RuleFailure (via `fail`) so the result carries data (actual, required) the loop can use.
"""
from __future__ import annotations

import itertools
import json

import pytest

from arch_harness.model import required_rooms


class RuleFailure(AssertionError):
    def __init__(self, message: str, **data):
        super().__init__(message)
        self.data = data


def fail(message: str, **data):
    raise RuleFailure(message, **data)


def pytest_addoption(parser):
    parser.addoption("--ah-model", required=True, help="model.json to check")
    parser.addoption("--ah-report", required=True, help="where to write the JSON results")


def _model(config):
    if not hasattr(config, "_ah_model"):
        with open(config.getoption("--ah-model"), encoding="utf-8") as fh:
            config._ah_model = json.load(fh)
    return config._ah_model


def parallel_wall_pairs(walls):
    """Walls on one storey that run the same way and face each other along more than 1 mm of their length."""
    def along(w):
        return (w["y0"] == w["y1"], *sorted((w["x0"], w["x1"]) if w["y0"] == w["y1"] else (w["y0"], w["y1"])))
    for a, b in itertools.combinations(walls, 2):
        (ha, a0, a1), (hb, b0, b1) = along(a), along(b)
        if a["storey"] == b["storey"] and ha == hb and min(a1, b1) - max(a0, b0) > 1:
            yield a, b


def pytest_generate_tests(metafunc):
    m = _model(metafunc.config)
    by_storey = {}
    for s in m["spaces"]:
        by_storey.setdefault(s["storey"], []).append(s)
    sources = {
        "door": [(d, d["id"]) for d in m["doors"]],
        "wall": [(w, w["id"]) for w in m["walls"]],
        "corridor": [(s, s["id"]) for s in m["spaces"] if s["use"] == "corridor"],
        "room": [(s, s["id"]) for s in m["spaces"] if s["use"] == "room"],
        "side": [(s, "building:" + s) for s in ("west", "east", "south", "north")],
        "space_pair": [((a, b), f"{a['id']}|{b['id']}")
                       for spaces in by_storey.values() for a, b in itertools.combinations(spaces, 2)],
        "required_room": [(r, f"{r[0]}#{r[1]}") for r in required_rooms(m)],
        "wall_pair": [((a, b), f"{a['id']}|{b['id']}") for a, b in parallel_wall_pairs(m["walls"])],
        # brief statements: only what the architect wrote is checked
        "shaped_room": [(s, s["id"]) for s in m["spaces"] if s["use"] == "room"] if "max_room_ratio" in m["parameters"] else [],
        "sized_room": [(s, s["id"]) for s in m["spaces"] if s["use"] == "room" and s.get("programme")]
                      if "max_room_oversize" in m["parameters"] else [],
        # one check per programme instance the line names (one, if it names no programme room: that fails)
        "adjacent_pair": [((a["room"], k, a["next_to"]), f"{a['room']}#{k} next to {a['next_to']}")
                          for a in m.get("adjacency", [])
                          for k in range(1, max(1, sum(r[0] == a["room"] for r in required_rooms(m))) + 1)],
    }
    for name, items in sources.items():
        if name in metafunc.fixturenames:
            marker = metafunc.definition.get_closest_marker("rule")
            if not items and marker is not None and marker.kwargs.get("from_brief"):
                NOT_ASKED.add(metafunc.definition.name)  # the brief states nothing to check: not run, not unconfirmed
            metafunc.parametrize(name, [i[0] for i in items], ids=[i[1] for i in items])


NOT_ASKED: set[str] = set()


def pytest_collection_modifyitems(config, items):
    dropped = [i for i in items if i.originalname in NOT_ASKED]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = [i for i in items if i.originalname not in NOT_ASKED]


@pytest.fixture
def model(request):
    return _model(request.config)


def _element(item):
    cs = getattr(item, "callspec", None)
    return cs.id if cs else None


def pytest_configure(config):
    config._ah_results = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    marker = item.get_closest_marker("rule")
    if marker is None:
        return
    record = rep.when == "call" or (rep.when == "setup" and rep.outcome != "passed")
    if not record:
        return
    data, message, outcome = {}, "", rep.outcome
    if rep.skipped:  # e.g. an empty parameter set: nothing of this kind in the model
        outcome, message = "skipped", "no element to check"
    elif call.excinfo is not None:
        exc = call.excinfo.value
        message = str(exc).split("\n")[0]
        data = getattr(exc, "data", {})
        if not isinstance(exc, AssertionError):
            outcome, message = "error", f"rule error: {type(exc).__name__}: {message}"
    item.config._ah_results.append({
        "rule": marker.kwargs["id"],
        "kind": marker.kwargs["kind"],
        "element": None if outcome == "skipped" else _element(item),
        "outcome": outcome,
        "message": message,
        "data": data,
        "source": " ".join((item.function.__doc__ or "").split()),
        "label": marker.kwargs.get("label", "").format(**_model(item.config)["parameters"]),
    })


def pytest_sessionfinish(session):
    with open(session.config.getoption("--ah-report"), "w", encoding="utf-8") as fh:
        json.dump(session.config._ah_results, fh, indent=1)
