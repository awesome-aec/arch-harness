"""Film: a replay of the rounds a design project already ran, read from its git history.

Every round the study runs is a commit (`round N: ...`), with model.json and the round's record beside it; a variant ends
with `evaluate ...` when it converged (cost in model/cost/cost.json); a last round that still fails is a stop. `collect` turns those commits
into frames for the viewer's /film page: no new run, no model, nothing invented. Several projects in a row are the
architect's decisions: the difference between their DESIGN.md files is shown as the decision between them. An agent
driving the MCP tools writes its reason in the round's commit body (`Agent: ...`); the film shows it with that round.

  python -m arch_harness film --project DIR [--project DIR2 ...] --target "the goal" [--variant V] [--final-only] --out film.json
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

from .codes import abstandsflaeche
from .model import required_rooms, solids
from .project import MODEL_DIR

_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|(.*)\|\s*$")
_BULLET = re.compile(r"^-\s*([\w ]+?)\s*:\s*(.+?)\s*$")
_AGENT = re.compile(r"^Agent:\s*(.+)$", re.M)  # an agent's reason, in the body of its round commit


def _git(project, *args: str) -> str:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=True).stdout


def _show(project, rev: str, path: str) -> str:
    return _git(project, "show", f"{rev}:{path}")


def guardrails(model: dict, record: dict) -> list[dict]:
    """The brief as guardrails: each programme room, each adjacency line, then each other rule, with how many of its checks
    failed in this round. Rules come from the round's own counts (`rules`); a round recorded before that field
    lists only the rules that failed."""
    instances = [r[0] for r in required_rooms(model)]
    out = []
    for entry in model.get("programme", []):
        total = instances.count(entry["name"])
        failed = sum(1 for f in record["failures"]
                     if f["rule"] == "brief/room-exists-at-area" and (f.get("element") or "").split("#")[0] == entry["name"])
        out.append({"id": f"brief:{entry['name']}", "kind": "brief", "label": entry["name"], "failed": failed,
                    "total": total})
    for adj in model.get("adjacency", []):
        label = f"{adj['room']} at the entrance" if adj["next_to"] == "entrance" else f"{adj['room']} next to {adj['next_to']}"
        total = max(1, instances.count(adj["room"]))  # as many checks as the rule runs: one, if it names no room
        failed = sum(1 for f in record["failures"] if f["rule"] == "brief/adjacency"
                     and (f.get("element") or "").split("#")[0] == adj["room"]
                     and (f.get("element") or "").endswith(f" next to {adj['next_to']}"))
        out.append({"id": f"adjacency:{adj['room']}|{adj['next_to']}", "kind": "adjacency", "label": label,
                    "failed": failed, "total": total})
    counts = dict(record.get("rules") or {})
    for f in record["failures"]:
        counts.setdefault(f["rule"], {"kind": f["kind"], "passed": 0, "failed": 1})
    for rule, c in counts.items():
        if rule in ("brief/room-exists-at-area", "brief/adjacency"):  # shown per room and per adjacency line above
            continue
        out.append({"id": rule, "kind": "shape" if c["kind"] == "brief" else c["kind"], "label": c.get("label") or rule,
                    "failed": c["failed"], "total": c["passed"] + c["failed"]})
    return out


def _frame(model: dict, record: dict) -> dict:
    building = model.get("building")
    failing = sorted({part for f in record["failures"] for part in (f.get("element") or "").split("|") if part})
    return {"round": record["round"], "passed": record["passed"], "by_kind": record["by_kind"],
            "failures": [{k: f.get(k) for k in ("rule", "kind", "element", "message")} for f in record["failures"][:60]],
            "failing": failing, "revisions": record.get("revisions", []), "notes": record.get("generator_notes", []),
            "parameters": record.get("parameters", {}), "guardrails": guardrails(model, record),
            "solids": solids(model), "site": model["site"],
            "building": building, "storeys": model.get("storeys", []),
            "setback": abstandsflaeche(building["height"]) if building else None}


def _takes(project, variant: str | None, final_only: bool) -> list[dict]:
    project = pathlib.Path(project)
    branches = _git(project, "for-each-ref", "--format=%(refname:short)", "refs/heads/variant/").split()
    takes = []
    for branch in sorted(branches):
        name = branch.split("/", 1)[1]
        if variant and name != variant:
            continue
        frames, cost = [], None
        for entry in _git(project, "log", "--reverse", "--format=%H%x09%s%x09%b%x1e", branch).split("\x1e"):
            if not entry.strip():
                continue
            sha, subject, body = entry.strip("\n").split("\t", 2)
            if subject.startswith("round "):
                model = json.loads(_show(project, sha, f"{MODEL_DIR}/model.json"))
                rounds = sorted(_git(project, "ls-tree", "--name-only", sha, f"{MODEL_DIR}/rounds/").split())
                agent = _AGENT.search(body)
                frames.append(_frame(model, json.loads(_show(project, sha, rounds[-1]))) | {"agent": agent and agent[1]})
            elif subject.startswith("evaluate "):
                cost = json.loads(_show(project, sha, f"{MODEL_DIR}/cost/cost.json"))
        takes.append({"project": str(project.name), "variant": name, "frames": frames[-1:] if final_only else frames,
                      "stopped": bool(frames) and not frames[-1]["passed"], "cost": cost,
                      "design": _show(project, branch, "DESIGN.md")})
    return takes


def _entries(text: str) -> dict:
    """The brief's bullets (`- key: value`) and table rows (`| key | ... |`), as (section, key) → value; a key
    repeated in one section (two adjacency lines for one room) keeps every value, joined by '; '."""
    out, section = {}, ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif m := _BULLET.match(line.strip()):
            k = (section, m[1])
            out[k] = f"{out[k]}; {m[2]}" if k in out else m[2]
        elif (m := _ROW.match(line.strip())) and not set(m[2]) <= set("-| "):
            out[(section, m[1])] = " | ".join(c.strip() for c in m[2].split("|"))
    return out


def decision(before: str, after: str) -> list[dict]:
    """What the architect changed in DESIGN.md between two briefs, in the order of the new brief."""
    old, new = _entries(before), _entries(after)
    return [{"key": k, "section": sec, "from": old.get((sec, k)), "to": v}
            for (sec, k), v in new.items() if old.get((sec, k)) != v]


def collect(projects, target: str, title: str | None = None, variant: str | None = None,
            final_only: bool = False) -> dict:
    takes = []
    for project in projects:
        for take in _takes(project, variant, final_only):
            take["decision"] = decision(takes[-1]["design"], take["design"]) if takes else []
            takes.append(take)
    if not takes:
        raise ValueError(f"no rounds to replay in {', '.join(map(str, projects))}" + (f" (variant {variant})" if variant else ""))
    for take in takes:
        del take["design"]
    return {"title": title, "target": target, "takes": takes}
