"""DESIGN.md is the intent: parsed into data in mm, no YAML, no hidden defaults."""
import pytest

from arch_harness.design import effective_parameters, load_design, parse_length


def test_lengths_parse_to_integer_millimetres():
    assert parse_length("40 m") == 40000
    assert parse_length("1.30 m") == 1300
    assert parse_length("0.85 m") == 850
    assert parse_length("365 mm") == 365
    with pytest.raises(ValueError):
        parse_length("wide")


def test_clinic_design_reads_every_section(clinic_design_path):
    d = load_design(clinic_design_path)
    assert d["name"] == "Neighbourhood health clinic"
    assert "health clinic" in d["brief"]
    assert d["site"]["width"] == 40000 and d["site"]["depth"] == 30000
    names = [r["name"] for r in d["programme"]]
    assert "Consultation room" in names
    consult = next(r for r in d["programme"] if r["name"] == "Consultation room")
    assert consult == {"name": "Consultation room", "area_m2": 16.0, "count": 6, "storey": "any"}
    assert d["constraints"]["max_storeys"] == 2
    assert d["constraints"]["storey_height"] == 3200
    assert d["parameters"]["door_width"] == 850
    assert "timber variant" in d["ideas"]
    assert set(d["variants"]) == {"masonry", "timber"}


def test_variant_overrides_parameters(clinic_design_path):
    d = load_design(clinic_design_path)
    base = effective_parameters(d)
    timber = effective_parameters(d, "timber")
    assert base["structure"] == "masonry" and base["exterior_wall"] == 365
    assert timber["structure"] == "timber" and timber["exterior_wall"] == 300
    assert timber["corridor_width"] == base["corridor_width"]


def test_unknown_variant_is_an_error(clinic_design_path):
    with pytest.raises(KeyError):
        effective_parameters(load_design(clinic_design_path), "glass")


def test_missing_site_is_reported(tmp_path):
    p = tmp_path / "DESIGN.md"
    p.write_text("# X\n\n## Programme\n| Room | Area m² | Count | Storey |\n|---|---|---|---|\n| A | 10 | 1 | any |\n")
    with pytest.raises(ValueError, match="Site"):
        load_design(p)


def test_adjacency_lines_become_pairs():
    """`## Adjacency` holds `- Room: other room` (or `entrance`): the rooms the architect wants next to each other."""
    from arch_harness.design import parse_design
    text = ("# t\n## Site\n- width: 20 m\n- depth: 20 m\n## Programme\n| Room | Area m² | Count | Storey |\n|---|---|---|---|\n"
            "| Reception and waiting | 60 | 1 | 0 |\n## Adjacency\n- Reception and waiting: entrance\n"
            "- Accessible WC: Reception and waiting\n")
    assert parse_design(text)["adjacency"] == [{"room": "Reception and waiting", "next_to": "entrance"},
                                                {"room": "Accessible WC", "next_to": "Reception and waiting"}]
