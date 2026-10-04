from shapely.geometry import box

from app.components.elia_engine.gate_garage import plan_gate, plan_garage


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
