"""Parse DESIGN.md, the architect's intent, into plain data.

Format (see docs/design-md.md): a level-1 title, then level-2 sections. `Site`, `Constraints` and `Parameters`
hold `- key: value` bullets; `Programme` holds a Markdown table (Room | Area m² | Count | Storey); `Variants`
holds level-3 headings, each with `- key: value` overrides. `Adjacency` holds `- Room: other room` lines (or
`entrance`): rooms the architect wants next to each other. `Brief` and `Ideas` are free text for the agent.
Lengths are written with a unit (`m` or `mm`) and stored as integer millimetres: one unit in the model.
"""
from __future__ import annotations

import pathlib
import re

_LENGTH = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(mm|m)\s*$")
_BULLET = re.compile(r"^\s*-\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)\s*$")


def parse_length(text: str) -> int:
    """'1.30 m' -> 1300, '365 mm' -> 365. Raises ValueError for anything without a length unit."""
    m = _LENGTH.match(str(text))
    if not m:
        raise ValueError(f"not a length with a unit (m or mm): {text!r}")
    value = float(m.group(1).replace(",", "."))
    return int(round(value * 1000)) if m.group(2) == "m" else int(round(value))


def _value(text: str):
    try:
        return parse_length(text)
    except ValueError:
        pass
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _sections(text: str) -> tuple[str, dict[str, list[str]]]:
    title, current, out = "", None, {}
    for line in text.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            current = line[3:].strip().lower()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return title, out


def _bullets(lines: list[str]) -> dict:
    out = {}
    for line in lines:
        m = _BULLET.match(line)
        if m:
            out[m.group(1)] = _value(m.group(2))
    return out


def _programme(lines: list[str]) -> list[dict]:
    rows = [ln.strip() for ln in lines if ln.strip().startswith("|")]
    rooms = []
    for row in rows[2:]:  # header + separator
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 4:
            raise ValueError(f"programme row needs Room | Area m² | Count | Storey: {row!r}")
        name, area, count, storey = cells[:4]
        rooms.append({"name": name, "area_m2": float(area.replace(",", ".")), "count": int(count),
                      "storey": storey.lower()})
    return rooms


def _variants(lines: list[str]) -> dict[str, dict]:
    out, current = {}, None
    for line in lines:
        if line.startswith("### "):
            current = line[4:].strip()
            out[current] = {}
        elif current is not None:
            out[current].update(_bullets([line]))
    return out


def _adjacency(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        m = re.match(r"^\s*-\s*(.+?)\s*:\s*(.+?)\s*$", line)
        if m:
            out.append({"room": m.group(1), "next_to": m.group(2)})
    return out


def parse_design(text: str) -> dict:
    title, sec = _sections(text)
    for required in ("site", "programme"):
        if required not in sec:
            raise ValueError(f"DESIGN.md has no '## {required.capitalize()}' section")
    site = _bullets(sec["site"])
    for key in ("width", "depth"):
        if not isinstance(site.get(key), int):
            raise ValueError(f"Site needs '- {key}: <length> m'")
    return {
        "name": title,
        "brief": "\n".join(sec.get("brief", [])).strip(),
        "site": site,
        "programme": _programme(sec["programme"]),
        "constraints": _bullets(sec.get("constraints", [])),
        "parameters": _bullets(sec.get("parameters", [])),
        "ideas": "\n".join(sec.get("ideas", [])).strip(),
        "variants": _variants(sec.get("variants", [])),
        "adjacency": _adjacency(sec.get("adjacency", [])),
    }


def load_design(path) -> dict:
    return parse_design(pathlib.Path(path).read_text(encoding="utf-8"))


def effective_parameters(design: dict, variant: str | None = None) -> dict:
    """Constraints and parameters merged, then the named variant's overrides on top."""
    params = {**design["constraints"], **design["parameters"]}
    if variant is not None:
        params.update(design["variants"][variant])  # KeyError for an unknown variant
    return params
