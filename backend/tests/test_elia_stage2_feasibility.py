from __future__ import annotations

import pytest
from copy import deepcopy
from shapely.geometry import Polygon, Point

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.feasibility import (
    extract_canonical_geometry,
    assess_project_feasibility,
)
from app.components.elia_engine.schemas import ELIARequirements


def _sample_master(
    land_coords=None,
    house_coords=None,
    has_road=True,
    units="m",
    balconies=None,
    walls=None,
    roofs=None,
    utilities=None,
    structural_evidence=None,
) -> dict:
    land = land_coords or [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]]
    house = house_coords or [[10.0, 8.0], [25.0, 8.0], [25.0, 20.0], [10.0, 20.0], [10.0, 8.0]]
    master: dict = {
        "land_boundary_polygon": land,
        "house_exterior_polygon": house,
    }
    if units is not None:
        master["units"] = units
    if has_road:
        master["road_facing"] = "south"
        master["road_access_edge"] = 0
    if balconies is not None:
        master["balconies"] = balconies
    if walls is not None:
        master["walls"] = walls
    if roofs is not None:
        master["terraces"] = roofs
    if utilities is not None:
        master["utilities"] = utilities
    if structural_evidence is not None:
        master["structural_evidence"] = structural_evidence
    return master


# =========================================================================
# 1. GEOMETRY TESTS
# =========================================================================

def test_geometry_house_excluded_from_placement_regions():
    """House footprint must be strictly excluded from unoccupied exterior ground."""
    master = _sample_master()
    geom = extract_canonical_geometry(master)
    assert geom.land_area_m2 == pytest.approx(1200.0)
    assert geom.house_area_m2 == pytest.approx(180.0)
    assert geom.unoccupied_area_m2 == pytest.approx(1020.0)
    # Point inside house must not be in unoccupied ground
    inside_house = Point(15.0, 15.0)
    assert not geom.unoccupied_ground.contains(inside_house)
    # Point outside house but inside land must be in unoccupied ground
    outside_house = Point(5.0, 5.0)
    assert geom.unoccupied_ground.contains(outside_house)


def test_geometry_boundary_holes_preserved():
    """Land polygon with interior hole (e.g. natural rock / easement) preserves holes."""
    # Land with 10x10 hole at (2, 2)
    exterior_ring = [[0.0, 0.0], [50.0, 0.0], [50.0, 40.0], [0.0, 40.0], [0.0, 0.0]]
    interior_hole = [[2.0, 2.0], [6.0, 2.0], [6.0, 6.0], [2.0, 6.0], [2.0, 2.0]]
    land_with_hole = [exterior_ring, interior_hole]
    master = _sample_master(land_coords=land_with_hole)
    geom = extract_canonical_geometry(master)
    # 50*40 = 2000, hole = 16, net land area = 1984
    assert geom.land_area_m2 == pytest.approx(1984.0)
    assert len(geom.land.interiors) == 1
    # Point inside the hole must not be in land
    inside_hole = Point(4.0, 4.0)
    assert not geom.land.contains(inside_hole)


def test_geometry_disconnected_exterior_regions():
    """Courtyard or surrounding geometry creating multiple exterior polygons is preserved."""
    # House dividing parcel into two distinct exterior zones
    master = _sample_master(
        land_coords=[[0.0, 0.0], [30.0, 0.0], [30.0, 20.0], [0.0, 20.0], [0.0, 0.0]],
        house_coords=[[10.0, 0.0], [20.0, 0.0], [20.0, 20.0], [10.0, 20.0], [10.0, 0.0]],
    )
    geom = extract_canonical_geometry(master)
    # Unoccupied ground will be a MultiPolygon of 2 separate 10x20 rectangles
    assert geom.unoccupied_area_m2 == pytest.approx(400.0)
    assert geom.unoccupied_ground.geom_type in {"MultiPolygon", "GeometryCollection"}


def test_geometry_missing_unknown_units():
    """When Master JSON lacks units and no default is supplied, units_explicit is False."""
    master = _sample_master(units=None)
    geom = extract_canonical_geometry(master, default_units=None)
    assert geom.units_explicit is False
    assert geom.units == "unknown"

    # In feasibility assessment, unverified units flags review_required
    reqs = {"access": {"parking_required": True, "vehicle_count": 1}}
    res = assess_project_feasibility(master, reqs)
    parking = res.feature_assessments["parking"]
    assert parking.feasibility_status == "review_required"
    assert "UNVERIFIED_PROJECT_UNITS" in parking.reason_codes


def test_geometry_invalid_non_finite_rejected():
    """Non-finite coordinates (NaN or Inf) are rejected with ELIA_INVALID_POLYGON."""
    master = _sample_master(land_coords=[[0.0, 0.0], [float("nan"), 0.0], [40.0, 30.0], [0.0, 0.0]])
    with pytest.raises(ELIAError) as exc:
        extract_canonical_geometry(master)
    assert exc.value.code == "ELIA_INVALID_POLYGON"


def test_existing_locked_objects_preserved():
    """Existing gates, garages, wells, and septic tanks cannot be deleted or relocated."""
    master = _sample_master(
        utilities={
            "well": {"position_m": [5.0, 5.0]},
            "septic_tank": {"position_m": [35.0, 25.0]},
        }
    )
    master["existing_gate"] = {"position": [20.0, 0.0], "width_m": 4.0}
    master["existing_garage"] = {"polygon": [[28.0, 2.0], [34.0, 2.0], [34.0, 8.0], [28.0, 8.0]]}
    geom = extract_canonical_geometry(master)

    assert geom.existing_well is not None
    assert (geom.existing_well.x, geom.existing_well.y) == (5.0, 5.0)
    assert geom.existing_septic is not None
    assert (geom.existing_septic.x, geom.existing_septic.y) == (35.0, 25.0)
    assert geom.existing_gate is not None
    assert geom.existing_garage is not None

    reqs = {
        "access": {"parking_required": True, "garage_required": True},
        "water_features": {"well_required": True, "septic_tank_required": True},
    }
    res = assess_project_feasibility(master, reqs)
    assert res.feature_assessments["garage"].reason_codes == ["EXISTING_GARAGE_PRESERVED"]
    assert res.feature_assessments["gate"].reason_codes == ["EXISTING_GATE_PRESERVED"]
    assert res.feature_assessments["well"].reason_codes == ["EXISTING_WELL_PRESERVED"]
    assert res.feature_assessments["septic_tank"].reason_codes == ["EXISTING_SEPTIC_PRESERVED"]


# =========================================================================
# 2. AVAILABILITY & FEASIBILITY STATES
# =========================================================================

def test_feasibility_state_feasible_with_evidence():
    """Generous site with valid road access evaluates standard features as feasible."""
    master = _sample_master()
    reqs = {
        "access": {
            "parking_required": True,
            "vehicle_count": 2,
            "vehicle_type": "car",
            "driveway_required": True,
            "driveway_style": "curved",
            "gate_required": True,
            "gate_opening_mechanism": "sliding",
            "gate_width_m": 3.6,
        },
        "landscape": {
            "garden_required": True,
            "lawn_required": True,
            "garden_ground_finish": "grass",
        },
    }
    res = assess_project_feasibility(master, reqs)
    assert res.feature_assessments["parking"].feasibility_status == "feasible"
    assert res.feature_assessments["driveway"].feasibility_status == "feasible"
    assert res.feature_assessments["gate"].feasibility_status == "feasible"
    assert res.feature_assessments["garden_lawn"].feasibility_status == "feasible"


def test_feasibility_state_infeasible_demonstrated():
    """Demonstrably impossible demand (e.g. 10 vehicles on tiny site) returns infeasible."""
    # Tiny lot: 12x10 with 10x8 house -> only 40 m² exterior ground
    master = _sample_master(
        land_coords=[[0.0, 0.0], [12.0, 0.0], [12.0, 10.0], [0.0, 10.0], [0.0, 0.0]],
        house_coords=[[1.0, 1.0], [11.0, 1.0], [11.0, 9.0], [1.0, 9.0], [1.0, 1.0]],
    )
    reqs = {
        "access": {
            "parking_required": True,
            "vehicle_count": 6,
            "vehicle_type": "van",
        }
    }
    res = assess_project_feasibility(master, reqs)
    parking = res.feature_assessments["parking"]
    assert parking.feasibility_status == "infeasible"
    assert "INSUFFICIENT_PARKING_CLEARANCE" in parking.reason_codes
    assert len(parking.suggested_alternatives) > 0


def test_feasibility_missing_evidence_vs_known_absence():
    """
    Distinguishes:
    - Known absence: no balconies in Master JSON -> not_applicable
    - Missing evidence: balcony exists but structural load schedule missing -> review_required
    """
    # 1. Known absence
    master_no_balc = _sample_master(balconies=[])
    reqs = {"balconies": {"planting_required": True}}
    res_no_balc = assess_project_feasibility(master_no_balc, reqs)
    balc_no = res_no_balc.feature_assessments["balcony_features"]
    assert balc_no.feasibility_status == "not_applicable"
    assert "NO_BALCONY_SURFACE" in balc_no.reason_codes

    # 2. Missing evidence
    master_with_balc = _sample_master(
        balconies=[{"json_id": "b1", "elevation_m": 3.2, "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]]}],
        structural_evidence={},  # Missing balcony_allowance_kg_m2
    )
    res_with_balc = assess_project_feasibility(master_with_balc, reqs)
    balc_with = res_with_balc.feature_assessments["balcony_features"]
    assert balc_with.feasibility_status == "review_required"
    assert "MISSING_STRUCTURAL_ALLOWANCE" in balc_with.reason_codes
    assert "structural_evidence.balcony_allowance_kg_m2" in balc_with.missing_evidence

    # 3. Fully feasible with structural evidence
    master_approved = _sample_master(
        balconies=[{"json_id": "b1", "elevation_m": 3.2, "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]]}],
        structural_evidence={"balcony_allowance_kg_m2": 150.0},
    )
    res_approved = assess_project_feasibility(master_approved, reqs)
    balc_app = res_approved.feature_assessments["balcony_features"]
    assert balc_app.feasibility_status == "feasible"


def test_feasibility_unsupported_scope_reported():
    """Features with deferred technical simulation state their exact assessment scope."""
    master = _sample_master(
        roofs=[{"json_id": "r1", "type": "flat_roof", "polygon": [[10, 8], [25, 8], [25, 20], [10, 20]]}]
    )
    reqs = {
        "solar": {"panels_required": True},
        "water_features": {"swimming_pool_required": True},
    }
    res = assess_project_feasibility(master, reqs)

    solar = res.feature_assessments["solar_pv"]
    assert "Stage 6" in solar.assessment_scope
    assert solar.feasibility_status == "feasible"

    pool = res.feature_assessments["swimming_pool"]
    assert "geotechnical" in pool.assessment_scope or "unsupported" in pool.assessment_scope
    assert pool.feasibility_status == "review_required"
    assert len(pool.missing_evidence) > 0


# =========================================================================
# 3. PREFERENCE & ACCESS FEASIBILITY
# =========================================================================

def test_straight_driveway_obstructed_by_house():
    """Direct straight driveway blocked by house footprint is evaluated as infeasible."""
    # Road at south (y=0). House spans from x=5 to x=35 across entire lot width
    master = _sample_master(
        land_coords=[[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]],
        house_coords=[[5.0, 5.0], [35.0, 5.0], [35.0, 15.0], [5.0, 15.0], [5.0, 5.0]],
    )
    reqs = {
        "access": {
            "driveway_required": True,
            "driveway_style": "straight",
        }
    }
    res = assess_project_feasibility(master, reqs)
    driveway = res.feature_assessments["driveway"]
    assert driveway.feasibility_status == "infeasible"
    assert "STRAIGHT_DRIVEWAY_OBSTRUCTED" in driveway.reason_codes
    assert any("curved" in alt.lower() for alt in driveway.suggested_alternatives)


def test_greeny_alternatives_when_shade_tree_cannot_fit():
    """When shade tree canopy cannot fit in narrow setbacks, alternatives are suggested."""
    # Narrow lot: house leaves only 2m setback on all sides
    master = _sample_master(
        land_coords=[[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0], [0.0, 0.0]],
        house_coords=[[2.0, 2.0], [18.0, 2.0], [18.0, 18.0], [2.0, 18.0], [2.0, 2.0]],
        walls=[{"json_id": "wall_1", "height_m": 3.0}],
    )
    reqs = {
        "landscape": {
            "trees_required": True,
            "shade_tree_preference": True,
        }
    }
    res = assess_project_feasibility(master, reqs)
    tree_feat = res.feature_assessments["shade_trees"]
    assert tree_feat.feasibility_status == "infeasible"
    assert "INSUFFICIENT_SHADE_TREE_SETBACK" in tree_feat.reason_codes
    # Greeny alternatives must include compact trees and vertical greenery
    assert any("compact" in alt.lower() for alt in tree_feat.suggested_alternatives)
    assert any("vertical" in alt.lower() or "wall" in alt.lower() for alt in tree_feat.suggested_alternatives)


# =========================================================================
# 4. UTILITIES & ELEVATED SURFACES
# =========================================================================

def test_well_septic_50ft_separation_rule_w01():
    """When lot cannot satisfy 15.24m (50 ft) separation from septic tank, well is infeasible."""
    # Small 15x15 lot with septic tank near center (7.5, 7.5)
    # 50 ft = 15.24m radius covers the entire lot!
    master = _sample_master(
        land_coords=[[0.0, 0.0], [15.0, 0.0], [15.0, 15.0], [0.0, 15.0], [0.0, 0.0]],
        house_coords=[[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [2.0, 8.0], [2.0, 2.0]],
        utilities={"septic_tank": {"position_m": [7.5, 7.5]}},
    )
    reqs = {
        "water_features": {"well_required": True}
    }
    res = assess_project_feasibility(master, reqs)
    well = res.feature_assessments["well"]
    assert well.feasibility_status == "infeasible"
    assert "WELL_SEPTIC_SEPARATION_VIOLATION" in well.reason_codes
    assert "W01" in well.applicable_rule_ids


def test_mixed_pitched_roof_and_terrace_project():
    """Project with both pitched roofs and flat terraces distinguishes their eligibility."""
    master = _sample_master(
        roofs=[
            {"json_id": "terrace_1", "type": "flat_roof", "slope_degrees": 0.0, "polygon": [[10, 8], [18, 8], [18, 14], [10, 14]]},
            {"json_id": "roof_pitch_1", "type": "pitched_roof", "slope_degrees": 25.0, "polygon": [[18, 8], [25, 8], [25, 20], [18, 20]]},
        ],
        structural_evidence={"roof_allowance_kg_m2": 200.0},
    )
    reqs = {
        "terrace": {"planting_required": True},
        "solar": {"panels_required": True},
    }
    res = assess_project_feasibility(master, reqs)
    terrace_feat = res.feature_assessments["rooftop_terrace"]
    assert terrace_feat.feasibility_status == "feasible"
    assert "terrace_1" in terrace_feat.affected_object_ids

    solar_feat = res.feature_assessments["solar_pv"]
    assert solar_feat.feasibility_status == "feasible"


def test_only_pitched_roof_makes_terrace_seating_infeasible():
    """Project with only pitched roofs makes terrace seating/planting infeasible."""
    master = _sample_master(
        roofs=[
            {"json_id": "roof_pitch_1", "type": "pitched_roof", "slope_degrees": 30.0, "polygon": [[10, 8], [25, 8], [25, 20], [10, 20]]},
        ]
    )
    reqs = {"terrace": {"seating_required": True}}
    res = assess_project_feasibility(master, reqs)
    terrace_feat = res.feature_assessments["rooftop_terrace"]
    assert terrace_feat.feasibility_status == "infeasible"
    assert "PITCHED_ROOF_INELIGIBLE" in terrace_feat.reason_codes


# =========================================================================
# 5. COMBINED PREFERENCE CONFLICTS
# =========================================================================

def test_combined_conflict_space_exhaustion():
    """When total ground footprints exceed available unbuilt ground, conflict is reported."""
    # Unoccupied ground is ~100 m²
    master = _sample_master(
        land_coords=[[0.0, 0.0], [20.0, 0.0], [20.0, 15.0], [0.0, 15.0], [0.0, 0.0]],
        house_coords=[[2.0, 2.0], [16.0, 2.0], [16.0, 12.0], [2.0, 12.0], [2.0, 2.0]],
    )
    # Demand: 3 cars (45m²) + garage (66m²) + pool (65m²) + dining (10m²) = 186m² > 100m²
    reqs = {
        "access": {
            "parking_required": True,
            "vehicle_count": 3,
            "garage_required": True,
            "driveway_required": True,
        },
        "water_features": {
            "swimming_pool_required": True,
        },
        "landscape": {
            "garden_table_set_required": True,
        },
    }
    res = assess_project_feasibility(master, reqs)
    assert res.overall_status == "conflicts_detected"
    assert len(res.combined_conflicts) > 0
    spatial_conflict = next(c for c in res.combined_conflicts if c.conflict_type == "SPATIAL_COMPETITION")
    assert "swimming_pool" in spatial_conflict.conflicting_features
    assert "parking" in spatial_conflict.conflicting_features
    assert len(spatial_conflict.suggested_alternatives) > 0


def test_combined_conflict_solar_and_terrace_competition():
    """Small flat roof with both solar panels and active terrace living reports competition."""
    # Flat terrace of only 20 m²
    master = _sample_master(
        roofs=[
            {"json_id": "terrace_tiny", "type": "flat_roof", "slope_degrees": 0.0, "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]]}
        ],
        structural_evidence={"roof_allowance_kg_m2": 250.0},
    )
    reqs = {
        "solar": {"panels_required": True},
        "terrace": {"planting_required": True, "seating_required": True},
    }
    res = assess_project_feasibility(master, reqs)
    assert any(c.conflict_type == "ROOFTOP_SURFACE_COMPETITION" for c in res.combined_conflicts)
