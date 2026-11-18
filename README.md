# arch-harness

Open infrastructure for developing architectural ideas with AI agents. **arch-harness is designed to work with
today's open-source agent harnesses through MCP**, a standard interface any harness can use.

Idea-first: the architect writes the intent in `DESIGN.md` (brief, room programme, site, constraints, ideas).
Agents generate building form from it, test every variant against building-code and brief rules, compare
variants by rules and cost, and the architect steers. Each variant lives on its own git branch, and the demo commits
every round. It runs on your own computer; with a local model no design data leaves it, and the viewer needs no internet
(three.js ships in the repo).

**Status:** first working demo (v0.0.1). Apache-2.0. An independent open-source project. Contributions from anyone are welcome.

**Who it is for:** architects and small offices who want to develop early design in rounds, on their own computer.
The engine stays open under Apache-2.0. Setting it up on an office's real project and keeping it running is offered by
DataDrivenAEC under the name ArchiLoops; nothing in this repository depends on that offer.

## The three parts

1. **Intent** — `DESIGN.md` ([format](docs/design-md.md)), and the model it produces: `model/model.json` in
   millimetres is the truth ([schema](arch_harness/schema/model.schema.json)); OpenUSD text layers (`.usda`, written
   canonically for stable git diffs), IFC4 (IfcOpenShell) and a floor-plan SVG the agent can read are renders of it.
2. **Domain, behind MCP** — one Python MCP server (`python -m arch_harness.mcp_server`) with four
   [plugin types](docs/plugin-contract.md):
   - **generators** turn intent into form (here: massing from the brief);
   - **rules** are pytest tests run after every step, each citing its source (here: DIN 18040-1 doors and
     corridors, MBO § 6 Abstandsfläche, geometry sanity, brief conformance; on a site whose model names `code: NSW`,
     the LEP height of buildings and the Apartment Design Guide's separation to boundaries instead of the German code rules);
   - **skills** describe design methods for the agent (Agent Skills format: `skills/`);
   - **data sources** bring open evidence into the design: public building records, carbon data such as
     ÖKOBAUDAT, local climate (here: one small local file of illustrative prices and carbon factors).
3. **The loop, in any harness** — a [hook contract](docs/hook-contract.md) of four calls: run the rules after a
   step, block settling while rules fail (bounded, with an honest reason when it cannot converge), load DESIGN.md
   as context, fork a variant onto its own git branch. Plus a live three.js viewer.

## Quick start

Needs git, conda (or mamba) and, for the agent adapter, Node ≥ 22.19.

```bash
git clone https://github.com/awesome-aec/arch-harness && cd arch-harness
conda env create -p .conda-ah -f environment.yml      # Python 3.12, IfcOpenShell 0.8.5, usd-core 26.8, pytest
.conda-ah/bin/python -m pytest                        # the unit tests, offline, no model, no key
```

## The demo

```bash
.conda-ah/bin/python -m arch_harness demo             # deterministic, offline: the clinic example, both variants
```

It copies `examples/clinic/DESIGN.md` (a two-storey neighbourhood health clinic) into `build/demo-clinic/`, a new
git repository, and runs the loop for each variant on its own branch: generate → check → revise → repeat. Round 1
uses the architect's sketch (doors 85 cm, corridor 1.30 m) and fails DIN 18040-1; the deterministic reviser sets
each parameter to its stated minimum (doors 90 cm, corridor 1.80 m because it is longer than 15 m without a
passing area); round 2 passes all three rule kinds. Each variant is then exported to IFC and costed (materials
and embodied carbon, illustrative data); `comparison.md` on `main` compares them.

```bash
git -C build/demo-clinic log --all --oneline --graph  # every round, variant and decision
.conda-ah/bin/python -m arch_harness demo --example tight-site   # a site too small: it says why, no false success
.conda-ah/bin/python -m arch_harness viewer --project build/demo-clinic   # live 3D view; click an element for its id
```

## Adapters

The domain never depends on one harness. An adapter maps the four hook calls onto a harness's own events.

- **pi** ([`adapters/pi`](adapters/pi/README.md)) — the first adapter: a pi package (extension + skills) for
  [pi](https://github.com/earendil-works/pi). Runs with any model pi supports, including local models via Ollama.
- Any MCP-capable harness can use the server and its tools directly; harnesses with shell hooks can call the
  contract as `python -m arch_harness hook …`.

## Not built yet

- Exact geometry: NVIDIA usd-brep solids (milestone 2). Today every element is a box; `arch_harness.model.solids()`
  is the seam that usd-brep replaces.
- More generators (floor layouts, structural grids), more rules (ten from public building law, daylight), a review
  agent comparing variants with the intent.
- A variants UI: comparing and steering variants in the viewer; pointing the agent at a clicked element
  (the viewer already records the selection for that).
- Real data sources (ÖKOBAUDAT, public building records, climate), an audit log beyond git, packaging.

## Credits

The cost estimate is ported from the author's own `model-cost` skill in
[aec-ai-workshop-2026](https://github.com/DataDrivenAEC/aec-ai-workshop-2026) (same author), released here under
Apache-2.0. One test downloads a sample IFC from
[buildingSMART Sample-Test-Files](https://github.com/buildingSMART/Sample-Test-Files) at test time (it is never
committed; the test is skipped when offline): credit to buildingSMART International. Built on
[IfcOpenShell](https://ifcopenshell.org), [OpenUSD](https://openusd.org), [three.js](https://threejs.org) and
[pi](https://github.com/earendil-works/pi). three.js 0.170.0 (MIT, its licence beside it) is included unchanged in
`arch_harness/viewer/vendor/three/`.

The DIN 18040-1 values are quoted from the public reproduction of DIN 18040-1:2010-10 by the Bavarian State
Ministry ("Planungsgrundlagen des barrierefreien Bauens", 2015), the MBO from its November 2002 version as last
amended on 23/24 November 2023. arch-harness checks a simplified model; it is not a building-permit review.

Licence: Apache-2.0
