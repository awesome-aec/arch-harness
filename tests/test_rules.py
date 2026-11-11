"""The rules are pytest tests run against a model; these tests prove each rule fails when it should."""
import pytest

from arch_harness.checks import run_rules


def failures(report, rule=None):
    return [r for r in report["results"] if r["outcome"] == "failed" and (rule is None or r["rule"] == rule)]


def test_tiny_model_passes_all_three_kinds(model, write_model):
    report = run_rules(write_model(model))
    assert failures(report) == []
    assert report["passed"] is True
    for kind in ("code", "geometry", "brief"):
        assert report["by_kind"][kind]["failed"] == 0
        assert report["by_kind"][kind]["passed"] > 0


def test_every_rule_cites_a_source(model, write_model):
    report = run_rules(write_model(model))
    for r in report["results"]:
        assert r["source"], r["rule"]
        assert r["kind"] in ("code", "geometry", "brief")


def test_door_narrower_than_90_cm_fails_with_its_minimum(model, write_model):
    model["doors"][0]["width"] = 850
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.3.2/door-clear-width")
    assert f["element"] == "L0-D01" and f["kind"] == "code"
    assert f["data"] == {"actual": 850, "required": 900}


def test_door_lower_than_205_cm_fails(model, write_model):
    model["doors"][1]["height"] = 2000
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.3.2/door-clear-height")
    assert f["element"] == "L0-D02" and f["data"]["required"] == 2050


def test_corridor_narrower_than_150_cm_fails(model, write_model):
    model["spaces"][2]["d"] = 1300
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.2/corridor-width")
    assert f["element"] == "L0-C" and f["data"]["required"] == 1500


def test_corridor_longer_than_15_m_needs_a_passing_area(model, write_model):
    model["spaces"][2]["w"] = 16000
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.2/corridor-width")
    assert f["data"]["required"] == 1800


def test_building_inside_its_abstandsflaeche_fails(model, write_model):
    model["building"]["x"] = 2000  # 0.4 H = 1.2 m, but at least 3 m
    report = run_rules(write_model(model))
    [f] = failures(report, "MBO/6(5)/abstandsflaeche-on-plot")
    assert f["data"]["required"] == 3000 and f["data"]["side"] == "west"


def test_door_wider_than_its_wall_fails_geometry(model, write_model):
    model["doors"][0]["offset"] = 3500
    report = run_rules(write_model(model))
    [f] = failures(report, "geometry/opening-fits-wall")
    assert f["element"] == "L0-D01" and f["kind"] == "geometry"


def test_door_taller_than_its_wall_fails_geometry(model, write_model):
    model["walls"][0]["height"] = 2000
    report = run_rules(write_model(model))
    assert [f["element"] for f in failures(report, "geometry/opening-fits-wall")] == ["L0-D01"]


def test_overlapping_rooms_fail_geometry(model, write_model):
    model["spaces"][1]["x"] = 3000
    report = run_rules(write_model(model))
    [f] = failures(report, "geometry/rooms-do-not-overlap")
    assert f["element"] == "L0-S01|L0-S02"


def test_missing_programme_room_fails_brief(model, write_model):
    del model["spaces"][1]
    model["doors"].pop()
    model["walls"].pop()
    report = run_rules(write_model(model))
    [f] = failures(report, "brief/room-exists-at-area")
    assert f["element"] == "Room B#1" and f["kind"] == "brief"


def test_room_below_its_programme_area_fails_brief(model, write_model):
    model["spaces"][0]["w"] = 3000  # 15 m² < 20 m²
    report = run_rules(write_model(model))
    [f] = failures(report, "brief/room-exists-at-area")
    assert f["element"] == "Room A#1"
    assert f["data"] == {"actual_m2": 15.0, "required_m2": 20.0}


def test_a_kind_with_no_checks_is_not_reported_as_passed(model, write_model):
    model["spaces"] = [s for s in model["spaces"] if s["use"] == "corridor"]
    model["programme"] = []
    model["doors"], model["walls"] = [], []
    report = run_rules(write_model(model))
    assert report["by_kind"]["brief"]["passed"] == 0
    assert "brief" in report["unconfirmed_kinds"]
    assert report["passed"] is False


def test_a_rule_with_nothing_to_check_is_unconfirmed_not_passed(model, write_model):
    model["spaces"] = [s for s in model["spaces"] if s["use"] != "corridor"]  # the corridor rule has no element
    report = run_rules(write_model(model))
    assert report["by_kind"]["code"]["passed"] > 0  # the kind still passes on its other rules
    assert [u["rule"] for u in report["unconfirmed_rules"]] == ["DIN18040-1/4.3.2/corridor-width"]
    assert report["passed"] is False


def test_abstandsflaeche_rounds_up_like_the_generator(model, write_model):
    model["building"]["height"] = 9993  # 0.4 H = 3997.2 mm: 3997 mm is short
    model["building"]["x"] = 3997
    [f] = failures(run_rules(write_model(model)), "MBO/6(5)/abstandsflaeche-on-plot")
    assert f["data"]["required"] == 3998


def test_parallel_walls_closer_than_a_door_fail_geometry(model, write_model):
    """A partition 300 mm in front of another wall leaves a sliver nobody can enter: geometry fails."""
    model["walls"].append({"id": "L0-W03", "storey": "L0", "x0": 0, "y0": 5472, "x1": 4000, "y1": 5472,
                           "thickness": 115, "height": 3000, "external": False})
    report = run_rules(write_model(model))
    [f] = failures(report, "geometry/walls-keep-clear")
    assert f["element"] == "L0-W01|L0-W03" and f["data"]["clear_mm"] == 300


def test_overlapping_parallel_walls_fail_geometry(model, write_model):
    model["walls"].append({"id": "L0-W03", "storey": "L0", "x0": 2000, "y0": 5057, "x1": 3000, "y1": 5057,
                           "thickness": 115, "height": 3000, "external": False})
    report = run_rules(write_model(model))
    assert [f["element"] for f in failures(report, "geometry/walls-keep-clear")] == ["L0-W01|L0-W03"]


def test_a_room_longer_than_the_briefs_ratio_fails(model, write_model):
    model["parameters"]["max_room_ratio"] = 2
    model["spaces"][0].update(w=2000, d=5000)  # 2.5 : 1
    report = run_rules(write_model(model))
    assert [f["element"] for f in failures(report, "brief/room-proportion")] == ["L0-S01"]
    # the rule states its label once, with the brief's own number filled in
    assert {r["label"] for r in report["results"] if r["rule"] == "brief/room-proportion"} == {"No room longer than 2 : 1"}


def test_brief_rules_without_a_brief_statement_do_not_run(model, write_model):
    """No ratio and no adjacency in the brief: those rules check nothing and are not reported (not unconfirmed)."""
    report = run_rules(write_model(model))
    assert not {"brief/room-proportion", "brief/adjacency"} & {r["rule"] for r in report["results"]}
    assert report["passed"] is True


def test_adjacency_from_the_brief(model, write_model):
    """Room A and Room B share a partition: adjacent. Room A is not at the entrance end (x 0 is, after the wall)."""
    model["parameters"]["exterior_wall"] = 0
    model["building"]["x"] = 0
    model["adjacency"] = [{"room": "Room A", "next_to": "Room B"}, {"room": "Room B", "next_to": "entrance"}]
    report = run_rules(write_model(model))
    assert [f["element"] for f in failures(report, "brief/adjacency")] == ["Room B#1 next to entrance"]


def test_an_adjacency_naming_no_programme_room_fails_instead_of_dropping_out(model, write_model):
    """A misspelled room in the Adjacency section is a failure, never a rule that silently checks nothing."""
    model["adjacency"] = [{"room": "Waiting", "next_to": "entrance"}, {"room": "Room A", "next_to": "Lobby"}]
    report = run_rules(write_model(model))
    assert {f["element"] for f in failures(report, "brief/adjacency")} == {"Room A#1 next to Lobby", "Waiting#1 next to entrance"}


def test_an_adjacency_room_that_was_not_placed_fails(model, write_model):
    """The brief asks for two of a room and only one was built: the second one's adjacency fails, it is not skipped."""
    model["programme"][0]["count"] = 2
    model["adjacency"] = [{"room": model["programme"][0]["name"], "next_to": "entrance"}]
    report = run_rules(write_model(model))
    assert f"{model['programme'][0]['name']}#2 next to entrance" in [f["element"] for f in failures(report, "brief/adjacency")]


def test_a_failing_element_keeps_its_umlaut(model, write_model):
    """Room names are German as often as not: the failure names 'Büro', not pytest's escaped 'B\\xfcro'."""
    model["adjacency"] = [{"room": "Büro", "next_to": "entrance"}]
    report = run_rules(write_model(model))
    assert [f["element"] for f in failures(report, "brief/adjacency")] == ["Büro#1 next to entrance"]


def test_a_room_far_above_its_programme_area_fails_when_the_brief_caps_it(model, write_model):
    model["parameters"]["max_room_oversize"] = 1.25
    model["spaces"][0].update(w=6000, d=5000)  # 30 m² for a 20 m² room: 1.5 ×
    report = run_rules(write_model(model))
    [f] = failures(report, "brief/room-not-oversized")
    assert f["element"] == "L0-S01" and f["data"] == {"actual_m2": 30.0, "max_m2": 25.0}
