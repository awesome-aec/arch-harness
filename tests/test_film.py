"""Film: a replay of rounds a project already ran, read from its git history (no new run, no model)."""
import json
import pathlib
import threading
import urllib.request

import pytest

from arch_harness.film import collect, decision
from arch_harness.project import init_project, run_study
from arch_harness.viewer import make_server


@pytest.fixture(scope="module")
def clinic_study(tmp_path_factory):
    examples = pathlib.Path(__file__).resolve().parents[1] / "examples"
    project = init_project(examples / "clinic", tmp_path_factory.mktemp("film") / "clinic")
    run_study(project)
    return project


def test_film_replays_each_round_with_the_fix_and_its_reason(clinic_study):
    film = collect([clinic_study], target="Doors at least 90 cm", variant="masonry")
    assert film["target"] == "Doors at least 90 cm"
    (take,) = film["takes"]
    first, second = take["frames"]
    assert first["round"] == 1 and not first["passed"] and second["passed"]
    assert "L0-D01" in first["failing"] and not second["failing"]
    assert {r["param"]: (r["from"], r["to"]) for r in first["revisions"]}["corridor_width"] == (1300, 1800)
    corridor = lambda f: next(s for s in f["solids"] if s["id"] == "L0-C")
    width = lambda s: s["max"][1] - s["min"][1]
    assert width(corridor(first)) < width(corridor(second))  # the fix is in the geometry, not only in the text
    assert take["cost"]["grand_total_eur"] > 0 and not take["stopped"]


def test_a_film_with_no_rounds_is_refused_not_written(clinic_study):
    """A misspelled variant finds no rounds: say so, instead of writing a film the page cannot play."""
    with pytest.raises(ValueError, match="no rounds"):
        collect([clinic_study], target="t", variant="typo")


def test_final_only_keeps_one_frame_per_variant_for_comparing_options(clinic_study):
    film = collect([clinic_study], target="Compare", final_only=True)
    assert [t["variant"] for t in film["takes"]] == ["masonry", "timber"]
    assert all(len(t["frames"]) == 1 and t["frames"][0]["passed"] and t["cost"] for t in film["takes"])


def test_a_site_that_cannot_fit_stops_with_the_generators_reason(tmp_path, tight_design_path):
    project = init_project(tight_design_path.parent, tmp_path / "tight")
    run_study(project)
    (take,) = collect([project], target="Fit the programme")["takes"]
    assert take["stopped"] and take["cost"] is None
    assert any("buildable depth" in n for n in take["frames"][-1]["notes"])
    assert take["frames"][-1]["setback"] == 3000


def test_decision_lists_what_the_architect_changed_between_two_briefs():
    before = "## Parameters\n- room_depth: 4.0 m\n- door_width: 0.90 m\n## Programme\n| Office | 15 | 2 | any |\n"
    after = "## Parameters\n- room_depth: 3.7 m\n- door_width: 0.90 m\n## Programme\n| Office | 15 | 1 | any |\n"
    assert decision(before, after) == [
        {"key": "room_depth", "section": "Parameters", "from": "4.0 m", "to": "3.7 m"},
        {"key": "Office", "section": "Programme", "from": "15 | 2 | any", "to": "15 | 1 | any"},
    ]


def test_film_page_is_offline_and_serves_the_film(clinic_study, tmp_path):
    path = tmp_path / "film.json"
    path.write_text(json.dumps(collect([clinic_study], target="t", variant="masonry")))
    server = make_server(clinic_study, 0, film=path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/film", timeout=5).read().decode()
        assert "http://" not in page and "https://" not in page
        assert "const esc = " in page and "window.renderAt" in page
        data = json.loads(urllib.request.urlopen(base + "/api/film", timeout=5).read())
        assert data["takes"][0]["frames"][0]["round"] == 1
    finally:
        server.shutdown()


def test_film_page_accepts_a_query(clinic_study, tmp_path):
    """The recorder opens /film?capture=1: a query must not turn the page into a 404."""
    path = tmp_path / "film.json"
    path.write_text(json.dumps(collect([clinic_study], target="t", variant="masonry")))
    server = make_server(clinic_study, 0, film=path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/film?capture=1", timeout=5).read()
        assert b"window.renderAt" in page
    finally:
        server.shutdown()


def test_an_agents_reason_in_the_round_commit_is_shown_with_its_round(tmp_path, tight_design_path):
    """An agent driving the MCP tools commits each round with its reason under `Agent:`; the film shows it."""
    from arch_harness import hooks
    from arch_harness.project import build, commit
    project = init_project(tight_design_path.parent, tmp_path / "agent")
    hooks.fork_variant(project, "agent")
    build(project)
    hooks.after_step(project)
    commit(project, "round 1: failing\n\nAgent: the section needs 10.46 m, so I shorten the rooms.")
    build(project, overrides={"room_depth": 3700})
    hooks.after_step(project)
    commit(project, "round 2: failing")
    (take,) = collect([project], target="Fit the programme")["takes"]
    assert [f["agent"] for f in take["frames"]] == ["the section needs 10.46 m, so I shorten the rooms.", None]


def test_each_frame_lists_the_guardrails_from_the_brief_and_the_rules(clinic_study):
    """The brief becomes guardrails (each programme room, each code and geometry rule); a frame says which it met."""
    film = collect([clinic_study], target="t", variant="masonry")
    first, second = film["takes"][0]["frames"]
    rails = {g["id"]: g for g in first["guardrails"]}
    assert rails["DIN18040-1/4.3.3.2/door-clear-width"]["failed"] > 0
    assert rails["geometry/walls-keep-clear"]["failed"] == 0 and rails["geometry/walls-keep-clear"]["total"] > 0
    assert rails["brief:Consultation room"] == {"id": "brief:Consultation room", "kind": "brief",
                                                "label": "Consultation room", "failed": 0, "total": 6}
    assert all(g["failed"] == 0 for g in second["guardrails"])


def test_brief_statements_become_their_own_guardrails():
    """The room-shape limit is one guardrail; each adjacency line is one guardrail, failing per room instance."""
    from arch_harness.film import guardrails
    model = {"storeys": [{"id": "L0"}], "programme": [{"name": "WC", "area_m2": 8, "count": 2, "storey": "any"}],
             "adjacency": [{"room": "WC", "next_to": "entrance"}],
             "parameters": {"max_room_ratio": 2, "max_room_oversize": 1.25}}
    record = {"failures": [{"rule": "brief/adjacency", "kind": "brief", "element": "WC#2 next to entrance"}],
              "rules": {"brief/adjacency": {"kind": "brief", "passed": 1, "failed": 1},
                        "brief/room-proportion": {"kind": "brief", "passed": 2, "failed": 0, "label": "No room longer than 2 : 1"},
                        "brief/room-not-oversized": {"kind": "brief", "passed": 2, "failed": 0,
                                                     "label": "No room over 125% of its programme area"},
                        "brief/room-exists-at-area": {"kind": "brief", "passed": 2, "failed": 0}}}
    rails = {g["id"]: g for g in guardrails(model, record)}
    assert rails["adjacency:WC|entrance"] == {"id": "adjacency:WC|entrance", "kind": "adjacency",
                                              "label": "WC at the entrance", "failed": 1, "total": 2}
    assert rails["brief/room-proportion"]["kind"] == "shape" and rails["brief/room-proportion"]["total"] == 2
    # the label the rule states, as the round recorded it
    assert rails["brief/room-proportion"]["label"] == "No room longer than 2 : 1"
    assert rails["brief/room-not-oversized"]["label"] == "No room over 125% of its programme area"
    assert "brief/adjacency" not in rails and "brief/room-exists-at-area" not in rails
    assert rails["brief:WC"]["failed"] == 0   # an adjacency failure is not a missing room


def test_decision_keeps_sections_apart_and_repeated_lines():
    """An adjacency line named like a programme row is its own entry; two lines for one room are both kept."""
    before = "## Programme\n| Reception | 60 | 1 | 0 |\n"
    after = before + "## Adjacency\n- Reception: entrance\n- Reception: WC\n"
    assert decision(before, after) == [{"key": "Reception", "section": "Adjacency", "from": None, "to": "entrance; WC"}]
