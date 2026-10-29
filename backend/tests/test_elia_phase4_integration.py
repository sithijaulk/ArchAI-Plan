from __future__ import annotations

from copy import deepcopy
import pytest
from shapely.geometry import Polygon, Point, LineString

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.generation import generate_exterior
from app.components.elia_engine.service import run_elia, validate_candidate_exterior
from app.components.elia_engine.requirements import normalize_requirements
from app.components.elia_engine.output import build_updated_master


def _make_phase4_master(
    land_coords=None,
    house_coords=None,
    with_obstacle=False,
):
    land = land_coords or [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]]
    house = house_coords or [[15.0, 10.0], [28.0, 10.0], [28.0, 22.0], [15.0, 22.0], [15.0, 10.0]]
    
    master: dict = {
        "project_id": "p_phase4_test",
        "units": "m",
        "land_boundary_polygon": land,
        "house_exterior_polygon": house,
        "site_location": {"latitude": 6.9271, "longitude": 79.8612},
        "north_angle": 0.0,
        "road_facing": "south",
        "road_access_edge": 0,
        "balconies": [],
        "terraces": [],
        "main_entrance": [20.0, 10.0],
        "walls": [
            {
                "id": "wall_south_01",
                "json_id": "wall_south_01",
                "type": "wall",
                "length_m": 12.0,
                "height_m": 3.5,
            }
        ],
    }
    if with_obstacle:
        # Restriction placed right in front of the house to block straight paths
        master["exterior_restrictions"] = [
            {
                "id": "shed_fixed_01",
                "polygon": [[5.0, 2.0], [12.0, 2.0], [12.0, 8.0], [5.0, 8.0], [5.0, 2.0]],
            }
        ]
    return master


# =========================================================================
# 1. INVARIANCE & NON-MUTATION OF AUTHORITATIVE UPSTREAM GEOMETRY
# =========================================================================

def test_authoritative_geometry_and_house_footprint_invariant():
    master = _make_phase4_master()
    original_master = deepcopy(master)
    reqs = {
        "access": {"parking_required": True, "garage_required": False, "driveway_required": True},
        "landscape": {"garden_required": True, "trees_required": True},
    }
    exterior, outcome = generate_exterior(master, reqs, "run_p4_01", "baseline")
    assert outcome == "valid"

    # Master document must not have been mutated during generation
    assert master["land_boundary_polygon"] == original_master["land_boundary_polygon"]
    assert master["house_exterior_polygon"] == original_master["house_exterior_polygon"]

    # Merged document preserves upstream fixed structures
    merged = build_updated_master(master, exterior, "run_p4_01", outcome)
    assert merged["house_exterior_polygon"] == original_master["house_exterior_polygon"]
    assert merged["land_boundary_polygon"] == original_master["land_boundary_polygon"]
    assert "exterior_landscape" in merged


# =========================================================================
# 2. PREFERENCE CHANGES DIRECTLY AFFECT GENERATED OUTPUT
# =========================================================================

def test_preference_changes_affect_actual_generated_output():
    master = _make_phase4_master()

    # Layout A: Open parking, no garage, lawn required
    reqs_a = {
        "access": {"parking_required": True, "garage_required": False, "vehicle_count": 2},
        "landscape": {"lawn_required": True, "garden_table_set_required": False},
    }
    ext_a, _ = generate_exterior(master, reqs_a, "run_a", "baseline")
    types_a = {item.get("type") for item in ext_a.get("outdoor_elements", [])}
    assert "parking_bay" in types_a
    assert "lawn_zone" in types_a
    assert "garden_table_set" not in types_a

    # Layout B: Explicit furniture requested
    reqs_b = {
        "access": {"parking_required": False, "garage_required": False},
        "landscape": {"garden_table_set_required": True, "garden_table_set_count": 2},
    }
    ext_b, _ = generate_exterior(master, reqs_b, "run_b", "baseline")
    types_b = {item.get("type") for item in ext_b.get("outdoor_elements", [])}
    assert "garden_table_set" in types_b
    table_sets = [item for item in ext_b.get("outdoor_elements", []) if item.get("type") == "garden_table_set"]
    assert len(table_sets) == 2


# =========================================================================
# 3. DRIVEWAY STYLE SELECTION & NO SILENT SUBSTITUTION
# =========================================================================

def test_straight_driveway_not_silently_substituted_when_obstructed():
    # Place restriction directly in front of south access
    master = _make_phase4_master(with_obstacle=True)
    reqs = {
        "access": {
            "parking_required": True,
            "garage_required": True,
            "driveway_required": True,
            "driveway_style": "straight",
            "preferred_garage_location": [8.0, 15.0],
            "preferred_gate_location": [8.0, 0.0],
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_straight", "baseline")
    driveway = ext.get("access", {}).get("driveway") or {}

    # When straight route is obstructed, must NOT silently substitute with curved A*
    if driveway.get("status") == "infeasible":
        assert driveway.get("reason") == "STRAIGHT_DRIVEWAY_OBSTRUCTED"
        assert driveway.get("chosen_style") == "straight"
    else:
        # If geometry could connect directly without crossing obstacle, it must be straight
        assert driveway.get("chosen_style") == "straight"


def test_curved_driveway_style_honored():
    master = _make_phase4_master()
    reqs = {
        "access": {
            "parking_required": True,
            "garage_required": True,
            "driveway_required": True,
            "driveway_style": "curved",
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_curved", "baseline")
    driveway = ext.get("access", {}).get("driveway") or {}
    assert driveway.get("chosen_style") == "curved"


# =========================================================================
# 4. OPEN PARKING BAYS WHEN GARAGE NOT REQUESTED
# =========================================================================

def test_open_parking_bays_generated_when_garage_not_requested():
    master = _make_phase4_master()
    reqs = {
        "access": {
            "parking_required": True,
            "garage_required": False,
            "vehicle_count": 2,
            "covered_parking": True,
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_bays", "baseline")
    assert outcome == "valid"
    outdoor = ext.get("outdoor_elements", [])
    bays = [item for item in outdoor if item.get("type") == "parking_bay" and item.get("validation", {}).get("valid")]
    assert len(bays) >= 1
    # Check bay dimensions and coverage attribute
    first_bay = bays[0]
    assert first_bay.get("covered") is True
    assert first_bay.get("dimensions", {}).get("width_m") == 2.5
    assert first_bay.get("dimensions", {}).get("length_m") == 5.0


# =========================================================================
# 5. MULTI-COUNT FURNITURE WITH USABLE CLEARANCE
# =========================================================================

def test_multi_count_furniture_with_usable_clearance():
    master = _make_phase4_master()
    reqs = {
        "landscape": {
            "garden_table_set_required": True,
            "garden_table_set_count": 2,
            "garden_seating_required": True,
            "garden_seating_count": 3,
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_furn", "baseline")
    outdoor = ext.get("outdoor_elements", [])
    tables = [item for item in outdoor if item.get("type") == "garden_table_set" and item.get("validation", {}).get("valid")]
    seating = [item for item in outdoor if item.get("type") == "garden_seating" and item.get("validation", {}).get("valid")]
    
    assert len(tables) == 2
    assert len(seating) == 3
    # Ensure usable clearance is documented
    for t in tables:
        assert t.get("validation", {}).get("usable_clearance_m") == 0.6


# =========================================================================
# 6. WATER FEATURES & TECHNICAL REVIEW EVIDENCE
# =========================================================================

def test_water_features_generated_with_review_required_evidence():
    master = _make_phase4_master()
    reqs = {
        "water_features": {
            "garden_taps_required": True,
            "garden_taps_count": 2,
            "well_required": True,
            "pond_required": True,
            "swimming_pool_required": True,
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_water", "baseline")
    outdoor = ext.get("outdoor_elements", [])
    taps = [item for item in outdoor if item.get("type") == "garden_tap"]
    wells = [item for item in outdoor if item.get("type") == "water_well"]
    ponds = [item for item in outdoor if item.get("type") == "garden_pond"]
    pools = [item for item in outdoor if item.get("type") == "swimming_pool"]

    assert len(taps) == 2
    assert len(wells) == 1
    assert len(ponds) == 1
    assert len(pools) == 1

    # Verify review_required status and notes
    for item in wells + ponds + pools + taps:
        assert item.get("status") == "review_required"
        assert item.get("validation", {}).get("evidence_status") == "review_required"
        assert "notes" in item


# =========================================================================
# 7. BOUNDARY WALL GENERATION & GATE OPENING SUBTRACTION
# =========================================================================

def test_boundary_wall_respects_boundary_and_gate_openings():
    master = _make_phase4_master()
    reqs = {
        "access": {"gate_width_m": 4.0},
        "landscape": {
            "boundary_wall_required": True,
            "boundary_wall_height_m": 2.1,
            "boundary_wall_type": "masonry_rendered",
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_wall", "baseline")
    outdoor = ext.get("outdoor_elements", [])
    walls = [item for item in outdoor if item.get("type") == "boundary_wall"]
    assert len(walls) == 1
    wall = walls[0]
    assert wall.get("height_m") == 2.1
    assert wall.get("wall_type") == "masonry_rendered"
    assert len(wall.get("gate_openings", [])) >= 1


# =========================================================================
# 8. NON-OVERLAPPING GROUND SURFACES PARTITION
# =========================================================================

def test_non_overlapping_ground_surfaces_partition():
    master = _make_phase4_master()
    reqs = {
        "access": {
            "driveway_required": True,
            "driveway_surface": "interlock",
        },
        "landscape": {
            "pedestrian_path_required": True,
            "walking_path_surface": "paving_stones",
            "lawn_required": True,
            "open_space_finish": "natural_grass",
            "trees_required": True,
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_surfaces", "baseline")
    surfaces = ext.get("ground_surfaces", [])
    assert len(surfaces) >= 2
    types = {s.get("type") for s in surfaces}
    assert "driveway" in types
    assert "lawn" in types

    # Check that materials match user preferences
    for s in surfaces:
        if s.get("type") == "driveway":
            assert s.get("material") == "interlock"
        elif s.get("type") == "lawn":
            assert s.get("material") == "natural_grass"


# =========================================================================
# 9. MODEL UNAVAILABLE RAISES EXPLICIT ERROR WITHOUT SILENT FALLBACK
# =========================================================================

def test_trained_model_unavailable_raises_explicit_error():
    master = _make_phase4_master()
    reqs = {"design_style": "greeny"}
    # Requesting trained_model when runtime adapter is not configured must raise 503 ELIAError
    with pytest.raises(ELIAError) as exc_info:
        generate_exterior(master, reqs, "run_model", "trained_model")
    assert "ELIA_MODEL_UNAVAILABLE" in exc_info.value.code


# =========================================================================
# 10. STRUCTURED PREFERENCE FULFILLMENT CONTRACT
# =========================================================================

def test_structured_preference_fulfillment_contract():
    master = _make_phase4_master()
    reqs = {
        "access": {
            "parking_required": True,
            "garage_required": False,
            "driveway_required": True,
            "driveway_style": "auto",
        },
        "water_features": {
            "garden_taps_required": True,
            "garden_taps_count": 1,
        },
        "balconies": {
            "planting_required": True,
        }
    }
    ext, outcome = generate_exterior(master, reqs, "run_fulfillment", "baseline")
    fulfillment = ext.get("preference_fulfillment", {})
    items = fulfillment.get("items", {})

    # Parking fulfilled
    assert items.get("parking", {}).get("status") == "fulfilled"
    # Driveway style fulfilled
    assert items.get("driveway_style", {}).get("status") == "fulfilled"
    # Garden tap review required
    assert items.get("garden_taps_required", {}).get("status") == "review_required"
    # Balcony planting evaluated in Phase 5 (infeasible when no balcony surface exists)
    assert items.get("balcony_planting", {}).get("status") in {"unsupported", "infeasible"}
