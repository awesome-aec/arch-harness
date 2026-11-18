"""Code rules for a site in New South Wales: the LEP height of buildings and the Apartment Design Guide's separation."""
import pytest

from arch_harness.codes import adg_separation
from conftest import fail


@pytest.mark.rule(id="NSW/LEP-4.3/building-height", kind="code", code="NSW")
def test_lep_building_height(model, nsw_building):
    """Standard Instrument LEP cl 4.3(2): 'The height of a building on any land is not to exceed the maximum height
    shown for the land on the Height of Buildings Map'; the site's `height_limit` is that map's figure plus any bonus
    the site's SEPP grants (the architect states the sum). Simplification: the model's one building height."""
    limit = model["site"]["height_limit"]
    if nsw_building["height"] > limit:
        fail(f"building is {nsw_building['height']} mm high > the LEP limit {limit} mm",
             actual=nsw_building["height"], required=limit)


@pytest.mark.rule(id="NSW/ADG-3F-1/separation-to-boundary", kind="code", code="NSW")
def test_adg_separation_to_boundary(edge):
    """NSW Apartment Design Guide, Objective 3F-1 design criteria, separation to side and rear boundaries by storeys
    (codes.adg_separation). An edge is one part of the building facing a side or rear boundary: its distance and its
    storeys (a stepped building states one edge per step); a street frontage is not an edge."""
    required = adg_separation(edge["storeys"], edge.get("lower_density", False))
    if edge["distance"] < required:
        fail(f"{edge['side']} edge of {edge['storeys']} storeys is {edge['distance']} mm from the boundary < ADG 3F-1 "
             f"{required} mm", actual=edge["distance"], required=required, side=edge["side"])
