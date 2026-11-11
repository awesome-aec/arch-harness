"""arch-harness command line.

  python -m arch_harness init --example clinic --out DIR                      a new design project (git) from an example
  python -m arch_harness demo [--example clinic] [--out build/demo-clinic]   deterministic study, no model, offline
  python -m arch_harness hook <after-step|before-settle|context|fork-variant> --project DIR [--name N]
  python -m arch_harness serve --project DIR                                 MCP server on stdio
  python -m arch_harness viewer --project DIR [--port 8765] [--film F.json]  live three.js viewer; /film replays a film
  python -m arch_harness film --project DIR [--project DIR2] --target T --out F.json   rounds already run, for a replay
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

from . import hooks
from .checks import kinds_line

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _demo(args):
    from .project import init_project, run_study
    out = pathlib.Path(args.out or ROOT / "build" / f"demo-{args.example}")
    if out.exists():
        shutil.rmtree(out)
    project = init_project(ROOT / "examples" / args.example, out)
    study = run_study(project, max_rounds=args.max_rounds)
    print(f"project: {project} (git: {len(study['variants'])} variant branch(es) + main)")
    for v in study["variants"]:
        print(f"\n== variant {v['variant']} on {v['branch']}: "
              + ("CONVERGED" if v["converged"] else "NOT CONVERGED") + f" in {v['rounds']} round(s)")
        for line in v["round_log"]:
            print(f"   {line}")
        print(f"   {v['reason']}")
        print("   final rules: " + kinds_line(v["last"]["by_kind"]))
        if v["cost"]:
            c = v["cost"]
            print(f"   cost (materials, illustrative data): EUR {c['grand_total_eur']:,.0f} = EUR "
                  f"{c['eur_per_m2'] or 0:,.0f}/m²; carbon {c['carbon_kgco2e']:,.0f} kg CO2e; unpriced: "
                  f"{', '.join(c['unpriced_materials']) or 'none'}")
    print(f"\ncomparison: {project / 'comparison.md'}")
    print(f"history:    git -C {project} log --all --oneline --graph")
    return 0 if all(v["converged"] for v in study["variants"]) else 2


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arch_harness", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--example", default="clinic")
    d.add_argument("--out")
    d.add_argument("--max-rounds", type=int, default=5)
    i = sub.add_parser("init")
    i.add_argument("--example", default="clinic")
    i.add_argument("--out", required=True)
    h = sub.add_parser("hook")
    h.add_argument("name", choices=["after-step", "before-settle", "context", "fork-variant"])
    h.add_argument("--project", default=".")
    h.add_argument("--name", dest="variant")
    h.add_argument("--max-rounds", type=int, default=5)
    h.add_argument("--since-round", type=int, default=0)
    s = sub.add_parser("serve")
    s.add_argument("--project", default=".")
    v = sub.add_parser("viewer")
    v.add_argument("--project", default=".")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--film")
    f = sub.add_parser("film")
    f.add_argument("--project", action="append", required=True)
    f.add_argument("--target", required=True)
    f.add_argument("--title")
    f.add_argument("--variant")
    f.add_argument("--final-only", action="store_true")
    f.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "demo":
        return _demo(args)
    if args.cmd == "init":
        from .project import init_project
        print(init_project(ROOT / "examples" / args.example, args.out))
        return 0
    if args.cmd == "hook":
        if args.name == "after-step":
            out = hooks.after_step(args.project)
        elif args.name == "before-settle":
            out = hooks.before_settle(args.project, args.max_rounds, args.since_round)
        elif args.name == "context":
            print(hooks.context(args.project))
            return 0
        else:
            if not args.variant:
                ap.error("fork-variant needs --name")
            out = hooks.fork_variant(args.project, args.variant)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if args.cmd == "serve":
        from .mcp_server import serve
        serve(args.project)
        return 0
    if args.cmd == "viewer":
        from .viewer import serve_viewer
        serve_viewer(args.project, args.port, args.film)
        return 0
    if args.cmd == "film":
        from .film import collect
        film = collect(args.project, args.target, args.title, args.variant, args.final_only)
        pathlib.Path(args.out).write_text(json.dumps(film, ensure_ascii=False), encoding="utf-8")
        print(f"{args.out}: {len(film['takes'])} take(s), {sum(len(t['frames']) for t in film['takes'])} frame(s)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
