"""A design project: a git repository holding DESIGN.md (intent) and model/ (the model and its renders).

Every round, variant and decision is a commit; each variant lives on its own branch `variant/<name>`.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

from .checks import kinds_line
from .design import effective_parameters, load_design
from .loop import run_loop
from .model import write_model
from .render.svg import plan_svg
from .render.usd import write_usd

MODEL_DIR = "model"
PROJECT_GITIGNORE = "# renders that are rebuilt from model.json, and local viewer state\nmodel/model.ifc\n.arch-harness/\n"


def git(project, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def init_project(source_dir, dest) -> pathlib.Path:
    """Copy an example's DESIGN.md into a new git repository and commit the intent."""
    dest = pathlib.Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    shutil.copy(pathlib.Path(source_dir) / "DESIGN.md", dest / "DESIGN.md")
    (dest / ".gitignore").write_text(PROJECT_GITIGNORE)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "config", "user.name", "arch-harness")
    git(dest, "config", "user.email", "arch-harness@localhost")
    commit(dest, "Intent: DESIGN.md")
    return dest


def commit(project, message: str) -> bool:
    git(project, "add", "-A")
    if not git(project, "status", "--porcelain").strip():
        return False
    git(project, "commit", "-q", "-m", message)
    return True


def current_variant(project) -> str | None:
    branch = git(project, "branch", "--show-current").strip()
    return branch.split("/", 1)[1] if branch.startswith("variant/") else None


def render(model: dict, model_dir) -> None:
    model_dir = pathlib.Path(model_dir)
    write_model(model, model_dir / "model.json")
    write_usd(model, model_dir / "usd")
    for st in model["storeys"]:
        (model_dir / f"plan-{st['id']}.svg").write_text(plan_svg(model, st["id"]), encoding="utf-8")


def params_for(project, variant: str | None = None, overrides: dict | None = None) -> tuple[dict, dict]:
    design = load_design(pathlib.Path(project) / "DESIGN.md")
    variant = variant if variant is not None else current_variant(project)
    params = effective_parameters(design, variant if variant in design["variants"] else None)
    params.update(overrides or {})
    return design, params


def build(project, variant: str | None = None, overrides: dict | None = None) -> dict:
    """Generate the massing for the project (current branch's variant unless named) and write every render."""
    from .generators.massing import generate
    design, params = params_for(project, variant, overrides)
    model = generate(design, params)
    render(model, pathlib.Path(project) / MODEL_DIR)
    return model


def _round_message(record: dict) -> str:
    state = "all rules pass" if record["passed"] else "failing"
    head = f"round {record['round']}: {state} ({kinds_line(record['by_kind'])})"
    revs = ", ".join(f"{r['param']} {r['from']}→{r['to']}" for r in record["revisions"])
    return head + (f"; revise {revs}" if revs else "")


def run_study(project, max_rounds: int = 5) -> dict:
    """Run the deterministic loop for every variant in DESIGN.md, each on its own branch; compare on main."""
    from .evaluate.cost_estimate import estimate
    from .plugins import data_source
    from .render.ifc import export_ifc
    project = pathlib.Path(project)
    design = load_design(project / "DESIGN.md")
    names = list(design["variants"]) or ["base"]
    source = data_source("illustrative-materials")
    results = []
    for name in names:
        git(project, "switch", "-q", "main")
        git(project, "switch", "-q", "-C", f"variant/{name}")
        params = effective_parameters(design, name if name in design["variants"] else None)
        model_dir = project / MODEL_DIR

        def on_round(record, model):
            render(model, model_dir)
            commit(project, _round_message(record))

        loop = run_loop(design, params, model_dir, max_rounds=max_rounds, on_round=on_round)
        entry = {"variant": name, "branch": f"variant/{name}", "converged": loop["converged"],
                 "reason": loop["reason"], "rounds": len(loop["rounds"]), "last": loop["rounds"][-1], "cost": None,
                 "round_log": [_round_message(r) for r in loop["rounds"]]}
        if loop["converged"]:
            ifc = export_ifc(loop["model"], model_dir / "model.ifc")
            entry["cost"] = estimate(ifc, source, outdir=model_dir / "cost")
            (model_dir / "cost" / "cost.json").write_text(json.dumps(entry["cost"], indent=1, default=str), encoding="utf-8")
            commit(project, f"evaluate {name}: EUR {entry['cost']['grand_total_eur']:,.0f}, "
                            f"{entry['cost']['carbon_kgco2e']:,.0f} kg CO2e (illustrative data)")
        else:
            commit(project, f"stop {name}: {loop['reason'][:200]}")
        results.append(entry)
    git(project, "switch", "-q", "main")
    (project / "comparison.md").write_text(comparison_markdown(design, results), encoding="utf-8")
    commit(project, "compare variants: " + ", ".join(
        f"{r['variant']} {'done' if r['converged'] else 'not converged'}" for r in results))
    return {"variants": results}


def comparison_markdown(design: dict, results: list[dict]) -> str:
    lines = [f"# Variants: {design['name']}", "",
             "| Variant | Branch | Rounds | Rules (code / geometry / brief) | Cost, materials (EUR) | EUR/m² | "
             "Carbon (kg CO2e) | Unpriced materials |", "|---|---|---:|---|---:|---:|---:|---|"]
    for r in results:
        k = r["last"]["by_kind"]
        rules = " / ".join(f"{k[x]['passed']} pass, {k[x]['failed']} fail" for x in ("code", "geometry", "brief"))
        c = r["cost"]
        if c:
            lines.append(f"| {r['variant']} | `{r['branch']}` | {r['rounds']} | {rules} | {c['grand_total_eur']:,.0f} | "
                         f"{c['eur_per_m2'] or 0:,.0f} | {c['carbon_kgco2e']:,.0f} | "
                         f"{', '.join(sorted(c['unpriced_materials'])) or 'none'} |")
        else:
            lines.append(f"| {r['variant']} | `{r['branch']}` | {r['rounds']} | {rules} | not estimated | | | |")
    lines += ["", "Cost basis: " + (next((r["cost"]["basis"] for r in results if r["cost"]), "no variant converged")),
              ""]
    for r in results:
        if not r["converged"]:
            lines.append(f"- **{r['variant']}** did not converge: {r['reason']}")
    return "\n".join(lines) + "\n"
