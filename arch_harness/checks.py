"""Run the rules (pytest) against a model and return one structured report."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

RULES_DIR = pathlib.Path(__file__).parent / "rules"
PACKAGE_PARENT = pathlib.Path(__file__).resolve().parents[1]  # so a rule can import arch_harness.codes
KINDS = ("code", "geometry", "brief")


def run_rules(model_path) -> dict:
    """Run every rule on model_path. `passed` is true only when every rule and every kind ran at least one check and
    none failed; a rule or kind with nothing checked is listed in `unconfirmed_rules` / `unconfirmed_kinds`, never
    reported as passing."""
    with tempfile.TemporaryDirectory() as tmp:
        report = pathlib.Path(tmp) / "rules.json"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(RULES_DIR), "-c", str(RULES_DIR / "pytest.ini"),
             "--rootdir", str(RULES_DIR), "-q", "--no-header", "-p", "no:randomly",
             f"--ah-model={pathlib.Path(model_path).resolve()}", f"--ah-report={report}"],
            capture_output=True, text=True, cwd=RULES_DIR,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(PACKAGE_PARENT), os.environ.get("PYTHONPATH")]))})
        if not report.exists():
            raise RuntimeError(f"rules did not run (rc={proc.returncode}): {proc.stdout[-2000:]}{proc.stderr[-2000:]}")
        results = json.loads(report.read_text())
    by_kind = {k: {"passed": 0, "failed": 0, "error": 0, "skipped": 0} for k in KINDS}
    for r in results:
        by_kind[r["kind"]][r["outcome"]] += 1
    unconfirmed = [k for k in KINDS if by_kind[k]["passed"] + by_kind[k]["failed"] + by_kind[k]["error"] == 0]
    bad = sum(by_kind[k]["failed"] + by_kind[k]["error"] for k in KINDS)
    checked = {r["rule"] for r in results if r["outcome"] != "skipped"}
    unconfirmed_rules = sorted(({"rule": r["rule"], "kind": r["kind"]} for r in results if r["rule"] not in checked),
                               key=lambda u: u["rule"])
    return {"passed": bad == 0 and not unconfirmed and not unconfirmed_rules, "by_kind": by_kind,
            "unconfirmed_kinds": unconfirmed, "unconfirmed_rules": unconfirmed_rules, "results": results}


def failures(report: dict) -> list[dict]:
    return [r for r in report["results"] if r["outcome"] in ("failed", "error")]


def fail_text(report_or_record: dict, limit: int = 12) -> str:
    """The one summary of what is wrong: failing elements, then rules with nothing to check. Works on a report
    (`results`) or a round record (`failures`)."""
    fails = report_or_record["failures"] if "failures" in report_or_record else failures(report_or_record)
    lines = [f"- [{f['kind']}] {f['rule']} @ {f['element']}: {f['message']}" for f in fails[:limit]]
    if len(fails) > limit:
        lines.append(f"- … and {len(fails) - limit} more")
    lines += [f"- [{u['kind']}] {u['rule']}: unconfirmed, no element to check"
              for u in report_or_record.get("unconfirmed_rules", [])]
    return "\n".join(lines)


def kinds_line(by_kind: dict) -> str:
    return ", ".join(f"{k} {by_kind[k]['passed']} passed/{by_kind[k]['failed']} failed" for k in KINDS)


def next_round(rounds_dir) -> int:
    """The number after the last round file in rounds_dir (1 when there is none)."""
    numbers = [int(p.stem.split("-")[1]) for p in pathlib.Path(rounds_dir).glob("round-*.json")]
    return max(numbers, default=0) + 1


def rule_counts(report: dict) -> dict:
    """Every rule with its kind, its label if it states one, and how many of its checks passed and failed (an error counts as failed)."""
    out = {}
    for r in report["results"]:
        c = out.setdefault(r["rule"], {"kind": r["kind"], "passed": 0, "failed": 0, **({"label": r["label"]} if r.get("label") else {})})
        if r["outcome"] == "passed":
            c["passed"] += 1
        elif r["outcome"] in ("failed", "error"):
            c["failed"] += 1
    return dict(sorted(out.items()))


def write_round(rounds_dir, report: dict, params: dict, revisions: list, **extra) -> dict:
    """Build the round record (the one shape) and write it as the next round-NN.json; return it."""
    rounds_dir = pathlib.Path(rounds_dir)
    rounds_dir.mkdir(parents=True, exist_ok=True)
    n = next_round(rounds_dir)
    record = {"round": n, "parameters": {k: params[k] for k in sorted(params)}, "passed": report["passed"],
              "by_kind": report["by_kind"], "unconfirmed_kinds": report["unconfirmed_kinds"],
              "unconfirmed_rules": report["unconfirmed_rules"],
              "failures": [{k: f[k] for k in ("rule", "kind", "element", "message")} for f in failures(report)],
              "rules": rule_counts(report), "revisions": revisions, **extra}
    (rounds_dir / f"round-{n:02d}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    return record
