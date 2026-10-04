from __future__ import annotations

from math import hypot
from typing import Any, Mapping

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from .geometry import point_xy
from .parser import UNIT_TO_METERS
from .rule_repository import elia_rules


def _road_side(master: Mapping[str, Any], access: Mapping[str, Any]) -> tuple[str | None, int | None]:
    land_info = master.get("land_info", {})
    road = master.get("road_access") or (land_info.get("road_access") if isinstance(land_info, Mapping) else None)
    side = access.get("road_side") or (road.get("side") if isinstance(road, Mapping) else None)
    edge_index = access.get("road_access_edge")
    if edge_index is None and isinstance(road, Mapping):
        edge_index = road.get("edge_index")
    if edge_index is None and isinstance(land_info, Mapping):
        edge_index = land_info.get("road_access_edge")
    if side is None and isinstance(land_info, Mapping):
        side = land_info.get("road_facing")
    return (str(side).lower() if side else None, edge_index)


def plan_gate(land: Polygon, house: Polygon, master: Mapping[str, Any], access: Mapping[str, Any], unit_scale: float,
              obstacles: BaseGeometry | None = None) -> dict[str, Any] | None:
    rules = elia_rules()["access"]
    width = float(access.get("gate_width") or elia_rules()["access"]["default_gate_width_m"])
    gate_count = int(access.get("gate_count", 1))
    existing = master.get("existing_gate") or master.get("gate")
    if isinstance(existing, Mapping):
        position = point_xy(existing, unit_scale)
        if not position:
            return None
        point = Point(position)
        if point.distance(land.boundary) <= rules["gate_boundary_tolerance_m"] and not (
            obstacles and obstacles.buffer(rules["gate_obstacle_clearance_m"]).covers(point)):
            interior = land.representative_point()
            dx, dy = interior.x - point.x, interior.y - point.y
            magnitude = hypot(dx, dy) or 1.0
            access_point = (point.x + dx / magnitude * rules["gate_access_inset_m"],
                            point.y + dy / magnitude * rules["gate_access_inset_m"])
            return {"json_id": "GATE_001", "position": list(position), "width": float(existing.get("width", width * (1 / unit_scale))) * unit_scale,
                    "access_point": list(access_point), "type": existing.get("type", access.get("gate_type", "existing")),
                    "source": "master_json", "valid": True, "additional_gates": [], "planned_gate_count": 1}
        return None

    side, edge_index = _road_side(master, access)
    if side is None and edge_index is None:
        return None
    coords = list(land.exterior.coords)
    edges = []
    for index, (first, second) in enumerate(zip(coords, coords[1:])):
        line = LineString([first, second])
        if edge_index is not None and index != int(edge_index):
            continue
        midpoint = line.interpolate(0.5, normalized=True)
        if side in {"north", "south", "east", "west"}:
            distances = {"north": land.bounds[3] - midpoint.y, "south": midpoint.y - land.bounds[1],
                         "east": land.bounds[2] - midpoint.x, "west": midpoint.x - land.bounds[0]}
            if distances[side] > max(rules["road_edge_alignment_min_distance_m"],
                                     line.length * rules["road_edge_alignment_ratio"]):
                continue
        separation = float(elia_rules()["access"]["gate_separation_m"])
        required_length = gate_count * width + max(0, gate_count - 1) * separation
        if line.length + 1e-9 < required_length:
            continue
        preferred = access.get("preferred_gate_location")
        if preferred:
            target = Point(float(preferred[0]), float(preferred[1]))
            midpoint = line.interpolate(line.project(target))
            if line.distance(target) > 0.5:
                continue
        if obstacles and obstacles.buffer(rules["gate_obstacle_clearance_m"]).covers(midpoint):
            continue
        edges.append((house.distance(midpoint), -line.length, index, line, midpoint))
    if not edges:
        return None
    _, _, selected_edge_index, line, midpoint = max(edges, key=lambda candidate: (candidate[0], candidate[1], -candidate[2]))
    interior = land.representative_point()
    separation = float(elia_rules()["access"]["gate_separation_m"])
    group_length = gate_count * width + max(0, gate_count - 1) * separation
    start_distance = (line.length - group_length) / 2
    gates = []
    for index in range(gate_count):
        distance = start_distance + width / 2 + index * (width + separation)
        gate_point = line.interpolate(distance)
        dx, dy = interior.x - gate_point.x, interior.y - gate_point.y
        magnitude = hypot(dx, dy) or 1.0
        access_point = (gate_point.x + dx / magnitude * rules["gate_access_inset_m"],
                gate_point.y + dy / magnitude * rules["gate_access_inset_m"])
        if obstacles and obstacles.buffer(0.25).covers(gate_point):
            return None
        gates.append({"json_id": f"GATE_{index + 1:03d}", "position": [gate_point.x, gate_point.y],
                      "access_point": list(access_point), "width": width,
                      "type": access.get("gate_type", "unspecified"), "source": "candidate", "valid": True,
                      "boundary_edge_index": selected_edge_index})
    primary = gates[0]
    primary["additional_gates"] = gates[1:]
    primary["planned_gate_count"] = len(gates)
    return primary


def _existing_garage(value: Any, scale: float) -> Polygon | None:
    if not isinstance(value, Mapping):
        return None
    polygon_value = value.get("polygon") or value.get("footprint") or value.get("geometry")
    if isinstance(polygon_value, Mapping) and polygon_value.get("type") == "Polygon":
        polygon_value = polygon_value.get("coordinates", [[]])[0]
    if isinstance(polygon_value, (list, tuple)) and len(polygon_value) >= 3:
        points = [(float(point[0]) * scale, float(point[1]) * scale) for point in polygon_value]
        polygon = Polygon(points)
        return polygon if polygon.is_valid and polygon.area > 0 else None
    center = point_xy(value, scale)
    if center:
        config = elia_rules()["access"]
        width, length = config["default_garage_width_m"], config["default_garage_length_m"]
        return box(center[0] - width / 2, center[1] - length / 2, center[0] + width / 2, center[1] + length / 2)
    return None


def plan_garage(land: Polygon, residual: BaseGeometry, gate: Mapping[str, Any], master: Mapping[str, Any], access: Mapping[str, Any],
                unit_scale: float, obstacles: BaseGeometry | None = None,
                approach_distance: float | None = None) -> dict[str, Any] | None:
    existing = master.get("existing_garage") or master.get("garage")
    garage = _existing_garage(existing, unit_scale)
    source = "master_json"
    gate_point = Point(gate["access_point"])
    clearance = float(elia_rules()["access"]["garage_clearance_m"])
    approach_distance = approach_distance or float(elia_rules()["access"]["default_garage_approach_distance_m"])
    access_points = None
    if garage is None:
        if not access.get("garage_required", False):
            return None
        source = "candidate"
        config = elia_rules()["access"]
        width, length = config["default_garage_width_m"], config["default_garage_length_m"]
        preferred = access.get("preferred_garage_location")
        if preferred:
            preferred_center = Point(float(preferred[0]), float(preferred[1]))
            min_x, min_y, max_x, max_y = residual.bounds
            step = max(width / 2, 1.0)
            fallback_candidates = [Point(x, y) for y in _frange(min_y + length / 2, max_y - length / 2, step)
                                   for x in _frange(min_x + width / 2, max_x - width / 2, step)]
            fallback_candidates.sort(key=lambda point: (point.distance(gate_point), point.y, point.x))
            candidates = [preferred_center, *fallback_candidates]
        else:
            min_x, min_y, max_x, max_y = residual.bounds
            step = max(width / 2, 1.0)
            candidates = [Point(x, y) for y in _frange(min_y + length / 2, max_y - length / 2, step)
                          for x in _frange(min_x + width / 2, max_x - width / 2, step)]
            candidates.sort(key=lambda point: (point.distance(Point(gate["access_point"])), point.y, point.x))
        garage = None
        for center in candidates:
            candidate = box(center.x - width / 2, center.y - length / 2, center.x + width / 2, center.y + length / 2)
            if (residual.covers(candidate) and land.boundary.distance(candidate) >= clearance and
                    not (obstacles and candidate.intersects(obstacles.buffer(clearance)))):
                candidate_access = _garage_access(candidate, land, gate_point, approach_distance, obstacles)
                if (candidate_access is not None and
                    not candidate.buffer(approach_distance).covers(gate_point)):
                    garage, access_points = candidate, candidate_access
                    break
        if (garage is None or not land.covers(garage) or not residual.covers(garage) or
                (obstacles and garage.intersects(obstacles.buffer(clearance)))):
            return None
    if access_points is None:
        access_points = _garage_access(garage, land, gate_point, approach_distance, obstacles)
    if access_points is None:
        return None
    entry, approach = access_points
    return {"json_id": "GARAGE_001", "polygon": list(garage.exterior.coords), "entry_point": list(entry),
            "access_point": list(approach),
            "capacity": int(access.get("garage_capacity", 1)), "source": source, "valid": True}


def _garage_access(garage: Polygon, land: Polygon, gate_point: Point, distance: float,
                   obstacles: BaseGeometry | None) -> tuple[tuple[float, float], tuple[float, float]] | None:
    center = garage.centroid
    candidates = [garage.boundary.interpolate(garage.boundary.project(gate_point))]
    ring = list(garage.exterior.coords)
    candidates.extend(LineString([first, second]).interpolate(0.5, normalized=True)
                      for first, second in zip(ring, ring[1:]))
    approaches = []
    boundary_clearance = max(float(elia_rules()["access"]["boundary_clearance_m"]), distance - 0.1)
    obstacle_clearance = float(elia_rules()["access"]["driveway_clearance_m"])
    for entry in candidates:
        dx, dy = entry.x - center.x, entry.y - center.y
        magnitude = hypot(dx, dy) or 1.0
        approach = (entry.x + dx / magnitude * distance, entry.y + dy / magnitude * distance)
        approach_point = Point(approach)
        connector = LineString([(entry.x, entry.y), approach])
        if (not land.covers(approach_point) or land.boundary.distance(approach_point) < boundary_clearance or
                garage.buffer(1e-6).covers(approach_point) or garage.distance(approach_point) < distance - 0.05 or
                (obstacles and obstacles.buffer(obstacle_clearance).covers(approach_point)) or
                garage.contains(connector.interpolate(0.5, normalized=True))):
            continue
        approaches.append((approach_point.distance(gate_point), (entry.x, entry.y), approach))
    if not approaches:
        return None
    _, entry, approach = min(approaches, key=lambda candidate: (candidate[0], candidate[1][1], candidate[1][0]))
    return entry, approach


def _frange(start: float, stop: float, step: float):
    value = start
    while value <= stop:
        yield value
        value += step
