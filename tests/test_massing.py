"""The massing generator: footprint from the site, storeys from the programme, deterministic."""
import json

from arch_harness.checks import run_rules
from arch_harness.design import effective_parameters, load_design
from arch_harness.generators.massing import generate
from arch_harness.model import dumps_model, validate_model


def by_kind(report, kind):
    return [r for r in report["results"] if r["kind"] == kind and r["outcome"] == "failed"]


def test_generation_is_deterministic(clinic_design_path):
    d = load_design(clinic_design_path)
    p = effective_parameters(d)
    assert dumps_model(generate(d, p)) == dumps_model(generate(d, p))


def test_clinic_massing_respects_the_site_and_needs_two_storeys(clinic_design_path, write_model):
    d = load_design(clinic_design_path)
    m = generate(d, effective_parameters(d))
    validate_model(m)
    assert [s["id"] for s in m["storeys"]] == ["L0", "L1"]
    assert m["building"]["height"] == 6400
    report = run_rules(write_model(m))
    assert by_kind(report, "geometry") == []
    assert by_kind(report, "brief") == []
    assert [r for r in by_kind(report, "code") if r["rule"].startswith("MBO")] == []


def test_first_sketch_parameters_fail_the_code_rules(clinic_design_path, write_model):
    d = load_design(clinic_design_path)
    report = run_rules(write_model(generate(d, effective_parameters(d))))
    rules = {r["rule"] for r in by_kind(report, "code")}
    assert rules == {"DIN18040-1/4.3.3.2/door-clear-width", "DIN18040-1/4.3.2/corridor-width"}


def test_a_small_programme_fits_one_storey(clinic_design_path):
    d = load_design(clinic_design_path)
    d["programme"] = [{"name": "Office", "area_m2": 15.0, "count": 4, "storey": "any"}]
    m = generate(d, effective_parameters(d))
    assert len(m["storeys"]) == 1


def test_the_core_stacks_on_every_storey(clinic_design_path):
    d = load_design(clinic_design_path)
    m = generate(d, effective_parameters(d))
    cores = [s for s in m["spaces"] if s["programme"] == "Stair and lift core"]
    assert len(cores) == 2
    assert {(s["x"], s["y"], s["w"], s["d"]) for s in cores} == {(cores[0]["x"], cores[0]["y"], cores[0]["w"], cores[0]["d"])}


def test_fixed_storey_rooms_stay_on_their_storey(clinic_design_path):
    d = load_design(clinic_design_path)
    m = generate(d, effective_parameters(d))
    assert {s["storey"] for s in m["spaces"] if s["programme"] == "Treatment room"} == {"L0"}


def test_tight_site_reports_why_it_does_not_fit(tight_design_path):
    d = load_design(tight_design_path)
    m = generate(d, effective_parameters(d))
    assert any("buildable depth" in n for n in m["notes"])
    assert [s for s in m["spaces"] if s["use"] == "room"] == []


def test_model_json_is_canonical(clinic_design_path):
    d = load_design(clinic_design_path)
    text = dumps_model(generate(d, effective_parameters(d)))
    assert text == json.dumps(json.loads(text), sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def _overlap(a, b):
    return all(min(a["max"][i], b["max"][i]) - max(a["min"][i], b["min"][i]) > 0 for i in range(3))


def structural_clashes(model):
    """Wall/slab pairs sharing volume (doors sit in their wall's opening, spaces are not material)."""
    from arch_harness.model import solids
    parts = [b for b in solids(model) if b["kind"] in ("wall", "slab")]
    return [(a["id"], b["id"]) for i, a in enumerate(parts) for b in parts[i + 1:] if a["kind"] != b["kind"] and _overlap(a, b)]


def test_clash_check_catches_a_slab_inside_a_wall(model):
    model["slabs"] = [{"id": "S", "storey": "L0", "x": 0, "y": 0, "w": 9000, "d": 9000, "z": 3000, "thickness": 220,
                       "role": "floor"}]
    assert structural_clashes(model) == [("L0-W01", "S"), ("L0-W02", "S"), ("L0-W09", "S")]


def test_walls_stop_at_the_underside_of_the_slab_above(clinic_design_path):
    d = load_design(clinic_design_path)
    for variant in (None, "timber"):
        m = generate(d, effective_parameters(d, variant))
        assert structural_clashes(m) == []
        assert {w["height"] for w in m["walls"]} == {m["parameters"]["storey_height"] - m["parameters"]["slab_thickness"]}


def test_a_strip_that_ends_short_of_the_wall_gives_its_rest_to_the_last_room(tight_design_path, write_model):
    """Room depth 3.77 m on the tight plot left a partition 25 mm in front of the east wall (a doubled wall):
    the generator gives a rest narrower than the walls' clear minimum to the last room instead."""
    d = load_design(tight_design_path)
    m = generate(d, {**effective_parameters(d), "room_depth": 3770})
    report = run_rules(write_model(m))
    assert [r for r in report["results"] if r["rule"] == "geometry/walls-keep-clear" and r["outcome"] == "failed"] == []


def test_two_room_depths_put_each_room_on_the_side_that_makes_it_squarer(clinic_design_path):
    d = load_design(clinic_design_path)
    m = generate(d, {**effective_parameters(d), "room_depth": 6500, "room_depth_north": 4000})
    rooms = {s["programme"]: s for s in m["spaces"] if s["use"] == "room"}
    assert rooms["Reception and waiting"]["d"] == 6500 and rooms["Accessible WC"]["d"] == 4000
    b = m["building"]
    assert b["d"] == 2 * 365 + 6500 + 4000 + 2 * 115 + d["parameters"]["corridor_width"]


def test_order_places_the_named_rooms_first(clinic_design_path):
    d = load_design(clinic_design_path)
    m = generate(d, {**effective_parameters(d), "order": "Community room, Reception and waiting"})
    strips = {}
    for s in sorted((s for s in m["spaces"] if s["storey"] == "L0" and s["use"] == "room"), key=lambda s: s["x"]):
        strips.setdefault(s["y"], []).append(s["programme"])
    south, north = (strips[y] for y in sorted(strips))
    assert south[:2] == ["Stair and lift core", "Community room"]   # the core stacks first, then the order
    assert north[0] == "Reception and waiting"


def test_the_model_carries_the_briefs_adjacency(clinic_design_path):
    d = {**load_design(clinic_design_path), "adjacency": [{"room": "Storage", "next_to": "Office"}]}
    assert generate(d, effective_parameters(d))["adjacency"] == [{"room": "Storage", "next_to": "Office"}]


def test_the_core_stays_at_the_south_west_by_the_entrance_with_two_depths(clinic_design_path):
    d = load_design(clinic_design_path)
    m = generate(d, {**effective_parameters(d), "room_depth": 4000, "room_depth_north": 6500})
    cores = [s for s in m["spaces"] if s["programme"] == "Stair and lift core"]
    assert {(s["x"], s["y"]) for s in cores} == {(m["building"]["x"] + 365, m["building"]["y"] + 365)}


def test_order_keeps_rooms_fixed_to_a_storey_ahead_of_rooms_for_any_storey(clinic_design_path):
    """Naming one room first must not let the other 'any storey' rooms take the ground floor before the rooms fixed
    to it (the consultation rooms went downstairs ahead of the treatment rooms)."""
    from arch_harness.generators.massing import _instances
    d = load_design(clinic_design_path)
    names = [r["name"] for r in _instances(d, 2, "Accessible WC") if not r.get("each")]
    assert names[0] == "Accessible WC"
    assert names.index("Physiotherapy") < names.index("Consultation room")


def test_a_room_is_never_drawn_narrower_than_the_briefs_ratio_allows(clinic_design_path):
    """With max_room_ratio 2, a 15 m² office on a 6.5 m deep side is 3.3 m wide (21 m²), not a 2.4 m sliver."""
    d = load_design(clinic_design_path)
    m = generate(d, {**effective_parameters(d), "room_depth": 6500, "max_room_ratio": 2})
    office = next(s for s in m["spaces"] if s["programme"] == "Office")
    assert office["w"] == 3300


def test_order_names_one_room_per_mention(clinic_design_path):
    """'Accessible WC' once in the order places one WC first; the second keeps its programme place."""
    from arch_harness.generators.massing import _instances
    d = load_design(clinic_design_path)
    names = [r["name"] for r in _instances(d, 2, "Accessible WC, Storage") if not r.get("each")]
    assert names[:2] == ["Accessible WC", "Storage"] and names.count("Accessible WC") == 2
    assert names.index("Accessible WC", 1) > names.index("Office")
