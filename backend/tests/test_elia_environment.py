from math import cos, radians, sin

import pytest
from shapely.geometry import LineString, box

from app.components.elia_engine.lighting import place_lighting
from app.components.elia_engine.shadow import analyze_shadows
from app.components.elia_engine.solar import calculate_solar_samples
from app.components.elia_engine.vertical_greenery import plan_vertical_greenery
from app.components.elia_engine.vegetation import place_vegetation


def test_solar_samples_are_finite_for_valid_location():
    samples = calculate_solar_samples({
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "solar_analysis_date": "2026-03-20",
    })
    assert len(samples) == 3
    assert all(-360 <= item["solar_azimuth_degrees"] <= 360 for item in samples)
    assert all(-90 <= item["solar_elevation_degrees"] <= 90 for item in samples)


def test_low_sun_and_missing_height_are_reported_not_fabricated():
    footprint = box(2, 2, 8, 8)
    low = analyze_shadows(footprint, 8, [{"timestamp": "2026-03-20T06:00:00+00:00", "solar_azimuth_degrees": 90,
                                        "solar_elevation_degrees": 1}])[0]
    no_height = analyze_shadows(footprint, None, [{"timestamp": "2026-03-20T12:00:00+00:00", "solar_azimuth_degrees": 180,
                                                  "solar_elevation_degrees": 45}])[0]
    assert low["status"] == "sun_too_low"
    assert no_height["status"] == "building_height_unavailable"


@pytest.mark.parametrize(("north_angle", "expected_shadow"), [
    (0, (0.0, -5.0)),
    (90, (-5.0, 0.0)),
    (180, (0.0, 5.0)),
    (270, (5.0, 0.0)),
    (37, (-5.0 * sin(radians(37)), -5.0 * cos(radians(37)))),
])
def test_shadow_projection_uses_documented_north_angle(north_angle, expected_shadow):
    footprint = box(2, 2, 8, 8)
    sample = [{"timestamp": "2026-03-20T12:00:00+00:00", "solar_azimuth_degrees": 0,
               "solar_elevation_degrees": 45}]
    result = analyze_shadows(footprint, 5, sample, north_angle_degrees=north_angle)[0]
    assert result["shadow_vector_m"] == pytest.approx(expected_shadow)


def test_vertical_trigger_and_no_support_are_explicit():
    master = {"balconies": []}
    automatic = plan_vertical_greenery(0.19, {"vertical_greenery": {"mode": "automatic"}}, master)
    above_threshold = plan_vertical_greenery(0.20, {"vertical_greenery": {"mode": "automatic"}}, master)
    disabled = plan_vertical_greenery(0.01, {"vertical_greenery": {"mode": "disabled"}}, master)
    assert automatic["triggered"] and automatic["status"] == "no_eligible_support_geometry"
    assert not above_threshold["triggered"]
    assert disabled["status"] == "disabled"


def test_vertical_planter_uses_only_explicit_support_geometry():
    master = {"balconies": [{"json_id": "BAL_01", "polygon": [[2, 2], [8, 2], [8, 3], [2, 3]], "z": 3.2, "floor_id": "F1"}]}
    result = plan_vertical_greenery(0.1, {"vertical_greenery": {"mode": "automatic"}}, master)
    assert result["status"] == "placed"
    assert result["elements"][0]["support_json_id"] == "BAL_01"
    assert result["elements"][0]["position"]["z"] == 3.2


def test_vegetation_canopies_stay_in_residual_and_out_of_driveway():
    land = box(0, 0, 20, 20)
    driveway = box(8, 0, 12, 20)
    residual = land.difference(box(3, 3, 9, 9))
    nodes = place_vegetation(residual, land, driveway, {"landscape": {"garden_required": True,
                           "greenery_density": "low", "preferred_vegetation_categories": ["shade_tree"]}}, [])
    assert nodes
    assert all(land.covers(__import__("shapely").geometry.Point(node["position"]).buffer(node["canopy_radius_m"])) for node in nodes)
    assert all(not __import__("shapely").geometry.Point(node["position"]).buffer(node["canopy_radius_m"]).intersects(driveway) for node in nodes)
    assert all(not node["verified_species_data"] for node in nodes)


def test_lighting_nodes_are_outside_driveway_surface():
    land = box(0, 0, 20, 20)
    driveway = LineString([(2, 10), (18, 10)])
    nodes = place_lighting(land, land, driveway, None, None,
                           {"lighting": {"required": True, "style": "pathway", "zones": ["driveway"]},
                            "access": {"preferred_driveway_width": 3.0}})
    assert nodes
    assert all(__import__("shapely").geometry.Point(node["position"]).distance(driveway) >= 1.5 for node in nodes)


def test_lighting_is_opt_in_and_honors_supported_style_zone_and_spacing():
    land = box(0, 0, 100, 100)
    disabled = place_lighting(land, land, None, None, None,
                              {"lighting": {"required": False, "zones": ["boundary"]}})
    closer = place_lighting(land, land, None, None, None,
                            {"lighting": {"required": True, "style": "architectural",
                                          "zones": ["boundary"], "preferred_spacing_m": 8}})
    wider = place_lighting(land, land, None, None, None,
                           {"lighting": {"required": True, "style": "architectural",
                                         "zones": ["boundary"], "preferred_spacing_m": 16}})

    assert disabled == []
    assert closer and wider
    assert all(node["zone"] == "boundary" and node["type"] == "wall_light" for node in closer + wider)
    assert len(closer) > len(wider)
