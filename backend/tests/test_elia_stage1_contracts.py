"""
Focused Stage 1 contract verification tests for ELIA Engine (Component 4).

Covers demonstrated defect areas:
- Invalid supplied constraints producing explicit errors (no silent dropping)
- Missing elevations remaining unavailable (not converted to zero)
- Surveyed source entrance vs computed planning access target distinction
- Hole preservation in model adapter constraints
- Single unit normalization to meters
- Source document immutability (no source-data mutation)
"""
from copy import deepcopy
import pytest
from shapely.geometry import shape

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.model_adapter import prepare_model_input


def _minimal_valid_master() -> dict:
    """Uses real schema field structure without synthetic dummy plot data."""
    return {
        "units": "m",
        "location": {"latitude": 6.9271, "longitude": 79.8612},
        "land_info": {
            "boundary_polygon": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]],
            "road_facing": "south",
            "calculated_north_bearing": 0.0,
        },
        "house_exterior_polygon": [[10.0, 8.0], [25.0, 8.0], [25.0, 20.0], [10.0, 20.0], [10.0, 8.0]],
    }


def test_invalid_restriction_geometry_raises_explicit_error():
    """Malformed supplied restrictions must produce an actionable error, not be silently dropped."""
    master = _minimal_valid_master()
    master["exterior_restrictions"] = [
        {"polygon": [[0, 0], [1, 1]]}  # Invalid: only 2 points, cannot form polygon
    ]

    with pytest.raises(ELIAError) as exc_info:
        prepare_model_input(master, {})
    assert exc_info.value.code in ("ELIA_INVALID_RESTRICTION", "ELIA_INVALID_POLYGON")


def test_invalid_vertical_surface_geometry_raises_explicit_error():
    """Malformed vertical surface geometry must raise an actionable error, not be silently dropped."""
    master = _minimal_valid_master()
    master["balconies"] = [
        {"json_id": "balc_1", "polygon": "not_a_polygon"}
    ]

    with pytest.raises(ELIAError) as exc_info:
        prepare_model_input(master, {})
    assert exc_info.value.code in ("ELIA_INVALID_VERTICAL_SURFACE", "ELIA_INVALID_POLYGON")


def test_missing_elevation_remains_unavailable_not_zero():
    """Missing elevation on vertical greenery surfaces must remain None, never coerced to 0.0."""
    master = _minimal_valid_master()
    master["balconies"] = [
        {
            "json_id": "balc_1",
            "floor_id": "fl_2",
            "polygon": [[10.0, 8.0], [15.0, 8.0], [15.0, 10.0], [10.0, 10.0], [10.0, 8.0]],
            # elevation_m and z are intentionally absent
        }
    ]

    model_input = prepare_model_input(master, {})
    surfaces = model_input["vertical_surfaces"]
    assert len(surfaces) == 1
    assert surfaces[0]["json_id"] == "balc_1"
    assert surfaces[0]["elevation_m"] is None, "Absent elevation must remain None, not converted to 0.0"


def test_supplied_elevation_preserved_and_converted_to_meters():
    """Supplied elevation must be preserved and scaled by source unit scale."""
    master = _minimal_valid_master()
    master["units"] = "ft"
    # Convert boundary and house to ft so context parser succeeds
    scale_ft = 1.0 / 0.3048
    master["land_info"]["boundary_polygon"] = [
        [x * scale_ft, y * scale_ft] for x, y in master["land_info"]["boundary_polygon"]
    ]
    master["house_exterior_polygon"] = [
        [x * scale_ft, y * scale_ft] for x, y in master["house_exterior_polygon"]
    ]
    master["balconies"] = [
        {
            "json_id": "balc_elev",
            "polygon": [
                [x * scale_ft, y * scale_ft]
                for x, y in [[10.0, 8.0], [15.0, 8.0], [15.0, 10.0], [10.0, 10.0], [10.0, 8.0]]
            ],
            "z": 10.0,  # 10 ft
        }
    ]

    model_input = prepare_model_input(master, {})
    surfaces = model_input["vertical_surfaces"]
    assert len(surfaces) == 1
    # 10 ft * 0.3048 = 3.048 m
    assert pytest.approx(surfaces[0]["elevation_m"], 0.001) == 3.048


def test_distinction_between_surveyed_entrance_and_computed_access_target():
    """Surveyed main_entrance must be kept distinct from computed planning target."""
    master = _minimal_valid_master()
    master["main_entrance"] = [12.0, 8.0]

    model_input = prepare_model_input(master, {})
    # Surveyed entrance fact
    assert model_input["main_entrance"] == [12.0, 8.0]
    # Computed planning target is projected outside the house wall
    assert model_input["computed_access_target"] is not None
    assert model_input["computed_access_target"] != model_input["main_entrance"]


def test_absent_main_entrance_remains_none():
    """When main_entrance is not supplied, surveyed main_entrance must be None."""
    master = _minimal_valid_master()
    assert "main_entrance" not in master

    model_input = prepare_model_input(master, {})
    assert model_input["main_entrance"] is None


def test_hole_preservation_in_model_adapter_restrictions():
    """Holes in restriction polygons must be preserved in the GeoJSON mapping."""
    master = _minimal_valid_master()
    # Exterior ring and interior hole
    master["exterior_restrictions"] = [
        {
            "coordinates": [
                [[0.0, 0.0], [8.0, 0.0], [8.0, 8.0], [0.0, 8.0], [0.0, 0.0]],
                [[2.0, 2.0], [6.0, 2.0], [6.0, 6.0], [2.0, 6.0], [2.0, 2.0]],
            ]
        }
    ]

    model_input = prepare_model_input(master, {})
    restrictions = model_input["exterior_restrictions"]
    assert len(restrictions) == 1
    geom = shape(restrictions[0])
    assert len(geom.interiors) == 1, "Interior hole must be preserved in model adapter restriction"


def test_source_master_json_is_not_mutated():
    """Model adapter execution must not mutate the caller's Master JSON document."""
    master = _minimal_valid_master()
    master["balconies"] = [
        {"json_id": "b1", "polygon": [[10.0, 8.0], [15.0, 8.0], [15.0, 10.0], [10.0, 10.0], [10.0, 8.0]]}
    ]
    snapshot = deepcopy(master)

    _ = prepare_model_input(master, {"access": {"road_side": "south"}})
    assert master == snapshot, "Source Master JSON was mutated during model preparation"
