from shapely.geometry import box

from app.components.elia_engine.gate_garage import plan_gate, plan_garage
from app.components.elia_engine.utility_safety import validate_utilities
from app.components.elia_engine.vertical_greenery import plan_vertical_greenery


def test_gate_uses_road_frontage_boundary_only():
    land = box(0, 0, 30, 20)
    house = box(10, 5, 20, 15)
    gate = plan_gate(land, house, {"land_info": {"road_facing": "south"}},
                     {"gate_width": 4, "gate_type": "sliding"}, 1.0)
    assert gate is not None
    assert gate["position"][1] == 0
    assert gate["boundary_edge_index"] == 3


def test_gate_is_not_guessed_without_road_information():
    assert plan_gate(box(0, 0, 20, 20), box(8, 8, 12, 12), {}, {}, 1.0) is None


def test_multiple_gates_are_spaced_on_road_boundary():
    land = box(0, 0, 60, 30)
    house = box(15, 8, 40, 24)
    gate = plan_gate(land, house, {"land_info": {"road_facing": "south"}},
                     {"gate_count": 2, "gate_width": 4}, 1.0)
    assert gate["planned_gate_count"] == 2
    assert len(gate["additional_gates"]) == 1
    assert gate["additional_gates"][0]["position"][1] == 0
    assert gate["additional_gates"][0]["position"][0] - gate["position"][0] >= 5


def test_garage_candidate_respects_residual_and_utility_obstacle():
    land = box(0, 0, 30, 20)
    house = box(10, 5, 20, 15)
    residual = land.difference(house)
    gate = {"access_point": [15, 0.75]}
    garage = plan_garage(land, residual, gate, {}, {"garage_required": True, "garage_capacity": 1}, 1.0)
    assert garage is not None
    polygon = box(*[coordinate for coordinate in (min(p[0] for p in garage["polygon"]), min(p[1] for p in garage["polygon"]),
                                                   max(p[0] for p in garage["polygon"]), max(p[1] for p in garage["polygon"]))])
    assert land.covers(polygon)
    assert not polygon.intersects(house)


def test_requested_gate_position_is_preserved():
    land = box(0, 0, 60, 30)
    house = box(20, 8, 40, 24)

    gate = plan_gate(land, house, {"land_info": {"road_facing": "south"}},
                     {"road_side": "south", "preferred_gate_location": [10, 0], "gate_width": 4}, 1.0)

    assert gate is not None
    assert gate["position"][0] == 10
    assert gate["position"][1] == 0


def test_garage_capacity_changes_parking_geometry():
    land = box(0, 0, 60, 40)
    house = box(20, 12, 40, 32)
    residual = land.difference(house)
    gate = {"access_point": [30, 0.75]}

    garage = plan_garage(land, residual, gate, {}, {"garage_required": True, "garage_capacity": 2}, 1.0)

    assert garage is not None
    assert garage["capacity"] == 2
    assert box(*[coordinate for coordinate in (min(point[0] for point in garage["polygon"]),
                                               min(point[1] for point in garage["polygon"]),
                                               max(point[0] for point in garage["polygon"]),
                                               max(point[1] for point in garage["polygon"]))]).area > 21


def test_vertical_planter_needs_contained_footprint_and_positive_elevation():
    requirements = {"vertical_greenery": {"mode": "preferred", "enabled": True},
                    "vertical_greenery_enabled": True}
    master = {"balconies": [{"id": "BAL_1", "floor_id": "F1", "z_m": 0.0,
                             "polygon": [[0, 0], [0.6, 0], [0.6, 0.3], [0, 0.3]]}]}

    result = plan_vertical_greenery(0.1, requirements, master)

    assert result["elements"]
    assert not result["elements"][0]["validation"]["support_valid"]
    assert not result["elements"][0]["validation"]["footprint_valid"]
    assert not result["elements"][0]["validation"]["elevation_valid"]
    assert not result["elements"][0]["render"]["visible"]
    assert result["status"] == "no_eligible_support_geometry"


def test_utility_status_distinguishes_absent_unknown_and_violation():
    absent = validate_utilities({}, {}, "m")
    unknown = validate_utilities({"utilities": {"well": {"known": False}}}, {}, "m")
    violation = validate_utilities({"utilities": {
        "well": {"position": [0, 0]}, "septic_tank": {"position": [2, 0]},
    }}, {}, "m")

    assert absent.status == "not_applicable"
    assert unknown.status == "unknown"
    assert violation.status == "failed"
