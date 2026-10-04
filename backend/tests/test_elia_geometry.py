import pytest
from shapely.geometry import Polygon, box

from app.components.elia_engine.geometry import feet_to_meters, meters_to_feet
from app.components.elia_engine.residual_space import calculate_residual_space
from app.components.elia_engine.utility_safety import validate_utilities
from app.components.elia_engine.requirements import normalize_requirements


def test_residual_subtracts_house_and_restrictions():
    land, house = box(0, 0, 20, 20), box(5, 5, 10, 10)
    residual = calculate_residual_space(land, house, [box(12, 12, 14, 14)])
    assert residual.land_area == 400
    assert residual.house_area == 25
    assert residual.restricted_area == 4
    assert residual.available_area == 371


def test_distance_unit_helpers_round_trip():
    assert feet_to_meters(50) == pytest.approx(15.24)
    assert meters_to_feet(15.24) == pytest.approx(50)


@pytest.mark.parametrize(("distance_m", "expected"), [(15.2401, "passed"), (15.24, "passed"), (15.239, "failed")])
def test_well_septic_uses_configured_50_foot_boundary(distance_m, expected):
    master = {"units": "m"}
    requirements = {"utilities": {
        "well": {"known": True, "position": [0, 0]},
        "septic_tank": {"known": True, "position": [distance_m, 0]},
    }}
    result = validate_utilities(master, requirements, "m")
    assert result.checks[0]["status"] == expected
    assert result.checks[0]["required_distance_ft"] == 50


def test_requirement_normalization_rejects_missing_location_and_converts_footage():
    with pytest.raises(Exception, match="requires latitude and longitude"):
        normalize_requirements({}, {}, "m")
    normalized = normalize_requirements({"latitude": 6.9, "longitude": 79.8, "units": "ft",
                                         "access": {"gate_width": 12}}, {}, "m")
    assert normalized["access"]["gate_width"] == pytest.approx(3.6576)
    assert normalized["solar_analysis_date"] == "2026-03-20"


def test_custom_vehicle_dimensions_and_configured_turning_default_are_supported():
    normalized = normalize_requirements({"latitude": 6.9, "longitude": 79.8, "access": {
        "vehicle_profiles": [{"vehicle_type": "custom", "length": 5.0, "width": 2.0}]}}, {}, "m")
    profile = normalized["access"]["vehicle_profiles"][0]
    assert profile["length"] == 5.0
    assert profile["width"] == 2.0
    assert profile["minimum_turning_radius"] == 5.5
    assert profile["turning_radius_source"] == "configured_project_default"
