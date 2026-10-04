import pytest

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.adapter import normalize_master_json
from app.components.elia_engine.parser import parse_exterior_context


BASE_MASTER = {
    "project_id": "p1",
    "units": "m",
    "land_info": {"boundary_points": [[0, 0], [30, 0], [30, 20], [0, 20]]},
    "house_exterior_polygon": [[10, 5], [20, 5], [20, 15], [10, 15]],
    "interior_layout": {"rooms": [{"id": "R1", "furniture": ["desk"]}]},
}


def test_parses_and_closes_valid_master_polygons():
    context = parse_exterior_context(BASE_MASTER)

    assert context.land.area == 600
    assert context.house.area == 100
    assert context.normalized_rings == ("land_boundary_polygon", "house_exterior_polygon")


def test_converts_feet_to_meters():
    context = parse_exterior_context({**BASE_MASTER, "units": "ft"})

    assert context.land.area == pytest.approx(600 * 0.3048**2)
    assert context.source_units == "ft"


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"house_exterior_polygon": BASE_MASTER["house_exterior_polygon"]}, "ELIA_MISSING_LAND_BOUNDARY"),
        ({"land_info": BASE_MASTER["land_info"]}, "ELIA_MISSING_HOUSE_EXTERIOR"),
        ({**BASE_MASTER, "house_exterior_polygon": [[0, 0], [4, 4], [0, 4], [4, 0]]}, "ELIA_INVALID_POLYGON"),
    ],
)
def test_rejects_missing_or_invalid_geometry(document, code):
    with pytest.raises(ELIAError) as error:
        parse_exterior_context(document)

    assert error.value.code == code


def test_rejects_unknown_units_and_house_outside_land():
    with pytest.raises(ELIAError, match="Unsupported"):
        parse_exterior_context({**BASE_MASTER, "units": "pixels"})
    with pytest.raises(ELIAError) as error:
        parse_exterior_context({**BASE_MASTER, "house_exterior_polygon": [[40, 40], [42, 40], [42, 42], [40, 42]]})
    assert error.value.code == "ELIA_HOUSE_OUTSIDE_LAND"


def test_research_master_fields_preserve_polygon_holes_and_inherit_north():
    document = {
        "units": "m",
        "land_info": {
            "mathematical_polygon": {
                "type": "Polygon",
                "coordinates": [
                    [[0, 0], [30, 0], [30, 20], [0, 20], [0, 0]],
                    [[2, 2], [2, 5], [5, 5], [5, 2], [2, 2]],
                ],
            },
            "calculated_north_bearing": 27,
        },
        "house": {"exterior_polygon": [[10, 8], [20, 8], [20, 15], [10, 15]]},
        "floor_plan": {"ground_floor": {"utilities": {
            "water_well": {"center": {"x": 1, "y": 1}},
            "septic_tank": {"x": 25, "y": 15},
        }}},
    }

    context = parse_exterior_context(document)
    normalized = normalize_master_json(document)

    assert context.land.area == 591
    assert len(context.land.interiors) == 1
    assert normalized["north_angle"] == 27
    assert normalized["utilities"]["well"]["position"] == [1, 1]
    assert normalized["utilities"]["septic_tank"]["position"] == [25, 15]
    assert "house_exterior_polygon" not in document


def test_raw_geojson_coordinate_rings_preserve_land_holes():
    document = {
        "units": "m",
        "land_info": {"mathematical_polygon": [
            [[0, 0], [30, 0], [30, 20], [0, 20], [0, 0]],
            [[2, 2], [2, 5], [5, 5], [5, 2], [2, 2]],
        ], "calculated_north_bearing": 0},
        "house_exterior_polygon": [[10, 8], [20, 8], [20, 15], [10, 15]],
    }

    context = parse_exterior_context(document)

    assert context.land.area == 591
    assert len(context.land.interiors) == 1


def test_non_finite_hole_coordinates_are_rejected():
    document = {
        "units": "m",
        "land_info": {"mathematical_polygon": [
            [[0, 0], [30, 0], [30, 20], [0, 20]],
            [[2, 2], [2, float("nan")], [5, 5]],
        ], "calculated_north_bearing": 0},
        "house_exterior_polygon": [[10, 8], [20, 8], [20, 15], [10, 15]],
    }

    with pytest.raises(ELIAError) as error:
        parse_exterior_context(document)

    assert error.value.code == "ELIA_INVALID_POLYGON"


def test_polygon_coordinates_must_be_two_dimensional_pairs():
    document = {
        "units": "m",
        "land_info": {"mathematical_polygon": [[0, 0, 0], [30, 0, 0], [30, 20, 0], [0, 20, 0]],
                      "calculated_north_bearing": 0},
        "house_exterior_polygon": [[10, 8], [20, 8], [20, 15], [10, 15]],
    }

    with pytest.raises(ELIAError) as error:
        parse_exterior_context(document)

    assert error.value.code == "ELIA_INVALID_POLYGON"


def test_buildable_zone_is_not_accepted_as_house_exterior():
    document = {
        "land_info": {"mathematical_polygon": [[0, 0], [30, 0], [30, 20], [0, 20]]},
        "buildable_footprint": {"polygon": [[5, 5], [25, 5], [25, 15], [5, 15]]},
    }
    with pytest.raises(ELIAError) as error:
        parse_exterior_context(document)

    assert error.value.code == "ELIA_MISSING_HOUSE_EXTERIOR"


def test_explicit_legacy_house_polygon_inside_buildable_footprint_remains_supported():
    document = {
        "land_info": {"mathematical_polygon": [[0, 0], [30, 0], [30, 20], [0, 20]],
                      "calculated_north_bearing": 0},
        "buildable_footprint": {"house_exterior_polygon": [[10, 5], [20, 5], [20, 15], [10, 15]]},
    }

    context = parse_exterior_context(document)

    assert context.house.area == 100


def test_conflicting_north_aliases_are_rejected():
    with pytest.raises(ELIAError) as error:
        normalize_master_json({"north_angle": 0, "land_info": {"calculated_north_bearing": 45}})

    assert error.value.code == "ELIA_CONFLICTING_NORTH_ORIENTATION"


def test_malformed_or_non_finite_upstream_utility_coordinates_are_rejected():
    with pytest.raises(ELIAError) as error:
        normalize_master_json({"utilities": {"well": {"position": {"x": float("inf"), "y": 2}}}})

    assert error.value.code == "ELIA_INVALID_UTILITY_LOCATION"


@pytest.mark.parametrize("house_path", [
    {"floor_plan": {"ground_floor": {"exterior_polygon": [[10, 5], [20, 5], [20, 15], [10, 15]]}}},
    {"structural_rectification": {"house_exterior_polygon": [[10, 5], [20, 5], [20, 15], [10, 15]]}},
])
def test_component_floor_and_structural_house_footprints_need_no_interior_data(house_path):
    document = {
        "units": "m",
        "land_info": {"mathematical_polygon": [[0, 0], [30, 0], [30, 20], [0, 20]],
                      "calculated_north_bearing": 12},
        **house_path,
    }

    context = parse_exterior_context(document)

    assert context.house.area == 100
    assert not document.get("interior_layout")
