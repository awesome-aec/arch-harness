"""The harness-neutral hook contract (four calls) and the variant study on git branches."""
import json
import shutil
import subprocess

import pytest

from arch_harness import hooks
from arch_harness.project import build, git, init_project, run_study


@pytest.fixture
def project(tmp_path, clinic_design_path):
    return init_project(clinic_design_path.parent, tmp_path / "clinic")


def test_init_project_is_a_git_repo_with_the_intent(project):
    assert (project / "DESIGN.md").exists()
    assert git(project, "log", "--format=%s").strip().splitlines()[-1].startswith("Intent")


def test_context_loads_design_md(project):
    text = hooks.context(project)
    assert "Neighbourhood health clinic" in text and "## Programme" in text
    assert "no model yet" in text


def test_after_step_runs_the_rules_and_records_a_round(project):
    build(project)
    step = hooks.after_step(project)
    assert step["round"] == 1 and step["passed"] is False
    assert "DIN18040-1/4.3.3.2/door-clear-width" in step["text"]
    record = json.loads((project / "model" / "rounds" / "round-01.json").read_text())
    assert record["passed"] is False
    # every rule with its counts, so a reader can show which guardrails a round met and which it hit
    assert record["rules"]["DIN18040-1/4.3.3.2/door-clear-width"]["failed"] > 0
    assert record["rules"]["geometry/rooms-do-not-overlap"] == {"kind": "geometry", "passed": record["rules"]["geometry/rooms-do-not-overlap"]["passed"], "failed": 0}
    assert record["rules"]["brief/room-exists-at-area"]["label"] == "Every room at its programme area"


def test_before_settle_blocks_while_rules_fail_then_releases(project):
    build(project)
    hooks.after_step(project)
    blocked = hooks.before_settle(project, max_rounds=5)
    assert blocked["settle"] is False and "door-clear-width" in blocked["reason"]
    build(project, overrides={"door_width": 900, "corridor_width": 1800})
    assert hooks.after_step(project)["passed"] is True
    done = hooks.before_settle(project, max_rounds=5)
    assert done["settle"] is True and "all three rule kinds pass" in done["reason"]


def test_before_settle_gives_up_honestly_at_the_round_limit(project):
    for _ in range(2):
        build(project)
        hooks.after_step(project)
    out = hooks.before_settle(project, max_rounds=2)
    assert out["settle"] is True and out["reason"].startswith("cannot converge")


def test_before_settle_counts_rounds_since_a_start(project):
    for _ in range(2):
        build(project)
        hooks.after_step(project)
    assert hooks.before_settle(project, max_rounds=2, since_round=2)["settle"] is False


def test_fork_variant_puts_a_variant_on_its_own_branch(project):
    out = hooks.fork_variant(project, "timber")
    assert out["branch"] == "variant/timber"
    assert git(project, "branch", "--show-current").strip() == "variant/timber"


def test_study_runs_each_variant_on_its_branch_with_cost(project):
    study = run_study(project, max_rounds=5)
    assert [v["variant"] for v in study["variants"]] == ["masonry", "timber"]
    for v in study["variants"]:
        assert v["converged"] is True and v["rounds"] == 2
        assert v["cost"]["grand_total_eur"] > 0 and v["cost"]["carbon_kgco2e"] > 0
        log = git(project, "log", "--format=%s", f"variant/{v['variant']}").splitlines()
        assert any(s.startswith("round 1") for s in log) and any(s.startswith("round 2") for s in log)
    assert git(project, "branch", "--show-current").strip() == "main"
    comparison = (project / "comparison.md").read_text()
    assert "masonry" in comparison and "timber" in comparison and "illustrative" in comparison.lower()


def test_status_counts_rounds_for_a_harness(project):
    assert hooks.status(project) == {"rounds": 0, "passed": None}
    build(project)
    hooks.after_step(project)
    assert hooks.status(project) == {"rounds": 1, "passed": False}
