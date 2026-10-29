from __future__ import annotations

import math
from copy import deepcopy
import pytest
from shapely.geometry import Polygon, Point, box

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.generation import generate_exterior
from app.components.elia_engine.service import run_elia
from app.components.elia_engine.solar_planner import plan_solar_pv, _extract_roof_surfaces
from app.components.elia_engine.elevated_features import plan_elevated_features, _extract_balconies, _extract_terraces
from app.components.elia_engine.solar import fetch_live_solar_conditions, calculate_solar_samples, extract_master_location
from app.components.elia_engine.output import build_updated_master


def _make_phase5_master(
    with_balcony=True,
    with_terrace=True,
    with_pitched_roof=False,
    certified=True,
    land_coords=None,
    house_coords=None,
):
    land = land_coords or [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]]
    house = house_coords or [[15.0, 10.0], [28.0, 10.0], [28.0, 22.0], [15.0, 22.0], [15.0, 10.0]]
    
    balconies = []
    if with_balcony:
        balconies.append({
            "id": "balcony_f2_south",
            "json_id": "balcony_f2_south",
            "type": "balcony",
            "floor_id": "floor_2",
            "elevation_m": 3.4,
            "coordinates": [[[16.0, 10.0], [20.0, 10.0], [20.0, 8.2], [16.0, 8.2], [16.0, 10.0]]],
            "structural_certified": certified,
            "access_door": [18.0, 10.0],
        })

    terraces = []
    if with_terrace:
        terraces.append({
            "id": "terrace_roof_flat",
            "json_id": "terrace_roof_flat",
            "type": "roof",
            "roof_type": "flat",
            "floor_id": "roof",
            "elevation_m": 6.8,
            "coordinates": [[[15.0, 10.0], [22.0, 10.0], [22.0, 18.0], [15.0, 18.0], [15.0, 10.0]]],
            "live_load_certified": certified,
            "access_door": [16.0, 11.0],
        })

    roofs = []
    if with_pitched_roof:
        roofs.append({
            "id": "roof_pitch_south",
            "json_id": "roof_pitch_south",
            "type": "roof",
            "roof_type": "pitched",
            "pitch_deg": 22.0,
            "azimuth_deg": 180.0,
            "elevation_m": 7.2,
            "coordinates": [[[22.0, 10.0], [28.0, 10.0], [28.0, 18.0], [22.0, 18.0], [22.0, 10.0]]],
        })

    walls = [
        {
            "id": "wall_south_01",
            "json_id": "wall_south_01",
            "type": "wall",
            "orientation": "south",
            "length_m": 12.0,
            "height_m": 3.5,
            "start_point": [15.0, 10.0],
            "end_point": [27.0, 10.0],
        }
    ]

    structural_evidence = {}
    if certified:
        structural_evidence = {
            "balcony_allowance_kg_m2": 250.0,
            "roof_allowance_kg_m2": 350.0,
            "remaining_capacity_kg_m2": 50.0,
            "proposed_load_kg_m2": 25.0,
            "solar_load_certified": True,
            "engineer_license": "SL-ENG-2024-8841",
            "revision": 1,
        }

    return {
        "project_id": "p_phase5_test",
        "units": "m",
        "land_boundary_polygon": land,
        "house_exterior_polygon": house,
        "site_location": {"latitude": 6.9271, "longitude": 79.8612, "timezone": "Asia/Colombo"},
        "north_angle": 0.0,
        "road_facing": "south",
        "road_access_edge": 0,
        "main_entrance": [20.0, 10.0],
        "balconies": balconies,
        "terraces": terraces,
        "roofs": roofs,
        "walls": walls,
        "structural_evidence": structural_evidence,
    }


# =========================================================================
# 1. CANONICAL ELEVATED-SURFACE CONTEXT
# =========================================================================

def test_mixed_pitched_roof_and_usable_flat_terrace_distinguished():
    master = _make_phase5_master(with_terrace=True, with_pitched_roof=True)
    roof_surfaces = _extract_roof_surfaces(master)
    assert len(roof_surfaces) == 2

    flat_surf = next(s for s in roof_surfaces if s["json_id"] == "terrace_roof_flat")
    pitched_surf = next(s for s in roof_surfaces if s["json_id"] == "roof_pitch_south")

    assert flat_surf["is_flat"] is True
    assert flat_surf["pitch_deg"] == 0.0
    assert pitched_surf["is_flat"] is False
    assert pitched_surf["pitch_deg"] == 22.0
    assert pitched_surf["azimuth_deg"] == 180.0


def test_absent_surface_distinguished_from_missing_evidence():
    # Master without balconies
    master_no_balc = _make_phase5_master(with_balcony=False)
    balconies = _extract_balconies(master_no_balc)
    assert len(balconies) == 0

    reqs = {"balconies": {"planting_required": True, "seating_required": True}}
    res = plan_elevated_features(master_no_balc, reqs)
    updates = res["fulfillment_updates"]
    assert updates["balcony_planting"]["status"] == "infeasible"
    assert "NO_BALCONY_SURFACE" in updates["balcony_planting"]["reason_codes"]


def test_invalid_non_finite_geometry_rejected():
    master = _make_phase5_master()
    # Inject NaN / Inf into balcony coordinates
    master["balconies"][0]["coordinates"] = [[[float("nan"), 10.0], [20.0, 10.0], [20.0, 8.2], [16.0, 8.2], [16.0, 10.0]]]
    balconies = _extract_balconies(master)
    # Malformed coordinate polygon is safely omitted or rejected
    assert len(balconies) == 0


# =========================================================================
# 2. ELIGIBILITY AND EVIDENCE (B06 / B09 & Scoped Structural Approval)
# =========================================================================

def test_bare_approval_flag_cannot_bypass_missing_load_evidence():
    # Structural certified flag is False and structural_evidence is empty
    master_uncertified = _make_phase5_master(certified=False)
    reqs = {
        "balconies": {"planting_required": True},
        "terrace": {"planting_required": True},
    }
    res = plan_elevated_features(master_uncertified, reqs)
    updates = res["fulfillment_updates"]
    
    # Must report review_required rather than silently accepting without evidence
    assert updates["balcony_planting"]["status"] == "review_required"
    assert "structural_evidence.balcony_allowance_kg_m2" in updates["balcony_planting"]["missing_evidence"]
    assert updates["rooftop_planting"]["status"] == "review_required"
    assert "structural_evidence.roof_allowance_kg_m2" in updates["rooftop_planting"]["missing_evidence"]


def test_door_access_route_clearance_preserved():
    master = _make_phase5_master(certified=True)
    # Balcony door is at [18.0, 10.0]
    reqs = {"balconies": {"planting_required": True, "seating_required": True}}
    res = plan_elevated_features(master, reqs)
    elements = res["elements"]

    door_pt = Point(18.0, 10.0)
    for el in elements:
        if el.get("supporting_surface_id") == "balcony_f2_south":
            el_poly = Polygon(el["polygon"])
            # Feature must not obstruct doorway corridor (0.5m clearance)
            assert el_poly.distance(door_pt) > 0.3


# =========================================================================
# 3. BALCONY PLANTING & SEATING
# =========================================================================

def test_balcony_potted_plants_and_seating_placed_on_valid_surface():
    master = _make_phase5_master(certified=True)
    reqs = {
        "balconies": {
            "planting_required": True,
            "potted_plants": True,
            "seating_required": True,
        }
    }
    res = plan_elevated_features(master, reqs)
    elements = res["elements"]
    types = {el["type"] for el in elements}
    assert "balcony_pot" in types
    assert "balcony_seating" in types

    for el in elements:
        if el["type"] in {"balcony_pot", "balcony_seating"}:
            assert el["supporting_surface_id"] == "balcony_f2_south"
            assert el["elevation_m"] >= 3.2


# =========================================================================
# 4. ROOFTOP PLANTS AND FURNITURE
# =========================================================================

def test_rooftop_planter_and_dining_set_placed_on_flat_terrace():
    master = _make_phase5_master(certified=True)
    reqs = {
        "terrace": {
            "planting_required": True,
            "planters_required": True,
            "tables_required": True,
            "seating_required": True,
        }
    }
    res = plan_elevated_features(master, reqs)
    elements = res["elements"]
    types = {el["type"] for el in elements}
    assert "rooftop_planter" in types
    assert "rooftop_table_set" in types

    for el in elements:
        if el["type"] in {"rooftop_planter", "rooftop_table_set"}:
            assert el["supporting_surface_id"] == "terrace_roof_flat"
            assert el["elevation_m"] >= 6.8


# =========================================================================
# 5. SOLAR PHOTOVOLTAIC PLANNING & ENERGY YIELD
# =========================================================================

def test_solar_pv_planning_on_valid_roof():
    master = _make_phase5_master()
    reqs = {
        "solar": {
            "panels_required": True,
            "preferred_roof_surface": "auto",
        }
    }
    plan = plan_solar_pv(master, reqs)
    assert plan is not None
    assert plan["status"] == "fulfilled"
    assert plan["module_count"] >= 4
    assert plan["system_capacity_kw"] >= 1.6
    assert plan["estimated_annual_yield_kwh"] > 1000.0
    assert plan["tilt_degrees"] > 0
    assert plan["azimuth_degrees"] == 180.0
    assert "outdoor_element" in plan
    assert plan["outdoor_element"]["type"] == "solar_panel_array"


def test_missing_or_invalid_location_raises_explicit_error():
    master = _make_phase5_master()
    master["site_location"] = {"latitude": "invalid_latitude", "longitude": 79.8}
    reqs = {"solar": {"panels_required": True}}
    
    with pytest.raises(ELIAError) as exc_info:
        plan_solar_pv(master, reqs)
    assert exc_info.value.code == "ELIA_INVALID_LOCATION"


def test_solar_without_roof_geometry_reports_evidence_missing():
    master = _make_phase5_master(with_terrace=False, with_pitched_roof=False)
    # Remove house polygon as well to test complete absence of roof
    master["house_exterior_polygon"] = [[0, 0], [1, 0], [1, 1], [0, 0]]
    reqs = {"solar": {"panels_required": True}}
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "evidence_missing"
    assert plan["feasibility_status"] == "evidence_missing"
    assert "MISSING_ROOF_GEOMETRY" in plan["reason"]
    assert "roof_surface_polygons" in plan.get("missing_evidence", [])


# =========================================================================
# 6. COORDINATED SURFACE PLANNING (Solar vs Terrace Space Competition)
# =========================================================================

def test_coordinated_solar_and_terrace_furniture_without_overlap():
    master = _make_phase5_master(certified=True)
    reqs = {
        "terrace": {
            "tables_required": True,
            "seating_required": True,
            "planting_required": True,
        },
        "solar": {
            "panels_required": True,
        }
    }
    # Plan solar first
    solar_plan = plan_solar_pv(master, reqs)
    assert solar_plan["status"] == "fulfilled"
    
    # Plan elevated features coordinating with solar array footprint
    elev_plan = plan_elevated_features(master, reqs, solar_plan=solar_plan)
    solar_poly = Polygon(solar_plan["outdoor_element"]["polygon"])
    
    for el in elev_plan["elements"]:
        if el.get("supporting_surface_id") == solar_plan["surface_id"]:
            el_poly = Polygon(el["polygon"])
            # Terrace furniture and planters must NOT overlap solar panels
            assert el_poly.intersection(solar_poly).area <= 1e-6


# =========================================================================
# 7. INTEGRATED WORKFLOW & PERSISTENCE SAFETY
# =========================================================================

def test_complete_phase5_workflow_end_to_end():
    master = _make_phase5_master(certified=True)
    original_master = deepcopy(master)
    reqs = {
        "access": {"parking_required": True, "garage_required": False, "driveway_required": True},
        "landscape": {"garden_required": True, "trees_required": True},
        "balconies": {"planting_required": True, "potted_plants": True},
        "terrace": {"tables_required": True, "seating_required": True},
        "solar": {"panels_required": True},
    }

    ext, outcome = generate_exterior(master, reqs, "run_p5_full", "baseline")
    assert outcome == "valid"

    # Upstream Master JSON must remain invariant
    assert master["house_exterior_polygon"] == original_master["house_exterior_polygon"]
    assert master["land_boundary_polygon"] == original_master["land_boundary_polygon"]

    # Verify Outdoor Elements contains elevated and solar items
    types = {el.get("type") for el in ext.get("outdoor_elements", [])}
    assert "solar_panel_array" in types
    assert "balcony_pot" in types
    assert "rooftop_table_set" in types

    # Verify structured fulfillment dictionary
    fulfillment = ext.get("preference_fulfillment", {}).get("items", {})
    assert fulfillment.get("solar_panels", {}).get("status") == "fulfilled"
    assert fulfillment.get("balcony_planting", {}).get("status") == "fulfilled"
    assert fulfillment.get("rooftop_seating", {}).get("status") == "fulfilled"

    # Verify environment solar installation record
    env = ext.get("environment", {})
    assert "solar_installation" in env
    assert env["solar_installation"]["module_count"] >= 4

    # Merged Master JSON preserves upstream and contains exterior_landscape
    merged = build_updated_master(master, ext, "run_p5_full", outcome)
    assert merged["house_exterior_polygon"] == original_master["house_exterior_polygon"]
    assert "exterior_landscape" in merged
