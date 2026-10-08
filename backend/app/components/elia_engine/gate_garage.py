from __future__ import annotations

from math import cos, hypot, isfinite, pi, sin
from typing import Any, Mapping

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely import affinity

from .adapter import resolve_upstream_road
from .geometry import point_xy
from .parser import UNIT_TO_METERS
from .rule_repository import elia_rules



def _gate_opening(line: LineString, center: Point, width: float) -> LineString | None:
    if width <= 0 or not isfinite(width):
        return None
    distance = line.project(center)
    start = distance - width / 2
    end = distance + width / 2
    if start < -1e-9 or end > line.length + 1e-9:
        return None
    return LineString([line.interpolate(max(0.0, start)), line.interpolate(min(line.length, end))])


def garage_polygon(value: Mapping[str, Any]) -> Polygon:
    polygon = value.get("polygon")
    if not isinstance(polygon, (list, tuple)) or not polygon:
        return Polygon()
    if isinstance(polygon[0], (list, tuple)) and polygon[0] and isinstance(polygon[0][0], (list, tuple)):
        return Polygon(polygon[0], polygon[1:])
    return Polygon(polygon)



def _count_fitting_bays(polygon: Polygon, bay_w: float, bay_l: float, tolerance: float = 0.05) -> int:
    """Return how many non-overlapping axis-aligned bay boxes fit inside *polygon*.

    Strategy:
    - Try several alignment angles: world 0°, world 90°, and the polygon's own
      minimum-rotated-rectangle principal axis.  For each, rotate the polygon to
      axis-aligned orientation **around its centroid** so it stays near the origin.
    - For each alignment we slide the grid by up to half a bay in both x and y
      so translated/rotated valid rectangles are reliably counted.
    - Each candidate bay is tested against the *actual* rotated polygon (with a
      small tolerance), not just its bounding box, so concavities are respected.
    - Returns the maximum count found across all orientations and offsets.
    """
    if polygon.is_empty or bay_w <= 0 or bay_l <= 0:
        return 0
    if polygon.area < bay_w * bay_l - tolerance:
        return 0

    # Collect trial angles: world axes plus polygon's own principal axis.
    angles = [0.0, 90.0]
    try:
        import math as _math
        rect = polygon.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
        dx = coords[1][0] - coords[0][0]
        dy = coords[1][1] - coords[0][1]
        principal = _math.degrees(_math.atan2(dy, dx)) % 180.0
        angles.append(principal)
        angles.append((principal + 90.0) % 180.0)
    except Exception:
        pass

    best = 0
    centroid = polygon.centroid
    for angle_deg in angles:
        rotated = affinity.rotate(polygon, -angle_deg, origin=centroid, use_radians=False)
        min_x, min_y, max_x, max_y = rotated.bounds
        
        estimated_cells = ((max_x - min_x) / bay_w) * ((max_y - min_y) / bay_l)
        from .rule_repository import elia_rules
        if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
            from .exceptions import ELIAError
            raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search budget exhausted for garage bay fitting.")
            
        buffered = rotated.buffer(1e-5)
        # Try sub-bay grid offsets (0, 1/2) x (0, 1/2) in both dimensions
        for off_x in (0.0, bay_w / 2.0):
            for off_y in (0.0, bay_l / 2.0):
                count = 0
                occupied = Polygon()
                y = min_y + off_y
                while y + bay_l <= max_y + tolerance:
                    x = min_x + off_x
                    while x + bay_w <= max_x + tolerance:
                        candidate = box(x, y, x + bay_w, y + bay_l)
                        if (buffered.covers(candidate) and
                                candidate.intersection(occupied).area < 1e-9):
                            count += 1
                            occupied = occupied.union(candidate)
                        x += bay_w
                    y += bay_l
                best = max(best, count)
    return best


def _road_side(master: Mapping[str, Any], access: Mapping[str, Any]) -> tuple[str | None, int | None]:
    upstream_side, upstream_edge = resolve_upstream_road(master)
    side = access.get("road_side") or upstream_side
    edge_index = access.get("road_access_edge")
    if edge_index is None:
        edge_index = upstream_edge
    return (str(side).lower() if side else None, edge_index)


def plan_gate(land: Polygon, house: Polygon, master: Mapping[str, Any], access: Mapping[str, Any], unit_scale: float,
              obstacles: BaseGeometry | None = None) -> dict[str, Any] | None:
    rules = elia_rules()["access"]
    width = float(access.get("gate_width_m") or elia_rules()["access"]["default_gate_width_m"])
    if width <= 0 or not isfinite(width):
        from .exceptions import ELIAError
        raise ELIAError("ELIA_INVALID_GATE_GEOMETRY", "Gate width must be finite and positive.")
    gate_count = int(access.get("gate_count", 1))
    existing = master.get("existing_gate") or master.get("gate")
    if isinstance(existing, Mapping):
        position = point_xy(existing, unit_scale)
        if not position:
            return None
        point = Point(position)
        existing_width = existing.get("width_m")
        if existing_width is not None:
            gate_w = float(existing_width)
        elif existing.get("width") is not None:
            gate_w = float(existing["width"]) * unit_scale
        else:
            gate_w = width
        if gate_w <= 0 or not isfinite(gate_w):
            from .exceptions import ELIAError
            raise ELIAError("ELIA_INVALID_GATE_GEOMETRY", "Existing gate width must be finite and positive.")
        boundary_coords = list(land.exterior.coords)
        boundary_segment = min((LineString([first, second]) for first, second in
                                zip(boundary_coords, boundary_coords[1:])),
                               key=lambda segment: segment.distance(point))
        opening = _gate_opening(boundary_segment, point, gate_w)
        if (point.distance(land.boundary) <= rules["gate_boundary_tolerance_m"] and opening is not None and
                not (obstacles and opening.intersects(obstacles.buffer(rules["gate_obstacle_clearance_m"])))):
            interior = land.representative_point()
            dx, dy = interior.x - point.x, interior.y - point.y
            magnitude = hypot(dx, dy) or 1.0
            access_point = (point.x + dx / magnitude * rules["gate_access_inset_m"],
                            point.y + dy / magnitude * rules["gate_access_inset_m"])

            return {"json_id": "GATE_001", "position": list(position), "width": gate_w,
                    "access_point": list(access_point), "type": existing.get("type", access.get("gate_type", "existing")),
                    "source": "master_json", "valid": True, "additional_gates": [], "planned_gate_count": 1}
        return None

    side, edge_index = _road_side(master, access)
    if side is None and edge_index is None:
        return None
    coords = list(land.exterior.coords)
    edges = []
    preferred = access.get("preferred_gate_location")
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
        if preferred:
            target = Point(float(preferred[0]), float(preferred[1]))
            if line.distance(target) > 0.5:
                continue
            midpoint = line.interpolate(line.project(target))
        if obstacles and obstacles.buffer(rules["gate_obstacle_clearance_m"]).covers(midpoint):
            continue
        dist_to_preferred = line.distance(Point(float(preferred[0]), float(preferred[1]))) if preferred else 0.0
        edges.append((dist_to_preferred, house.distance(midpoint), -line.length, index, line, midpoint))
    if not edges:
        return None
    if preferred:
        edges.sort(key=lambda candidate: (candidate[0], -candidate[1], candidate[2], candidate[3]))
    else:
        edges.sort(key=lambda candidate: (candidate[1], candidate[2], -candidate[3]), reverse=True)
    _, _, _, selected_edge_index, line, midpoint = edges[0]
    interior = land.representative_point()
    separation = float(elia_rules()["access"]["gate_separation_m"])
    group_length = gate_count * width + max(0, gate_count - 1) * separation
    if preferred:
        projected = line.project(Point(float(preferred[0]), float(preferred[1])))
        start_distance = max(0.0, min(line.length - group_length, projected - width / 2))
        if start_distance < 0 or start_distance + group_length > line.length + 1e-6:
            return None
    else:
        start_distance = (line.length - group_length) / 2
    gates = []
    for index in range(gate_count):
        distance = start_distance + width / 2 + index * (width + separation)
        gate_point = line.interpolate(distance)
        dx, dy = interior.x - gate_point.x, interior.y - gate_point.y
        magnitude = hypot(dx, dy) or 1.0
        access_point = (gate_point.x + dx / magnitude * rules["gate_access_inset_m"],
                gate_point.y + dy / magnitude * rules["gate_access_inset_m"])
        opening = _gate_opening(line, gate_point, width)
        if opening is None or (obstacles and opening.intersects(obstacles.buffer(rules["gate_obstacle_clearance_m"]))):
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
        if value is not None:
            from .exceptions import ELIAError
            raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY", "Supplied garage geometry must be an object.")
        return None
    from shapely.geometry import shape

    # Strict alias selection: check explicit key presence, not truthiness.
    # This prevents an empty list/dict from falling through to a center-based fallback.
    raw = None
    explicit_key = None
    for key in ("polygon", "footprint", "geometry"):
        if key in value:
            raw = value[key]
            explicit_key = key
            break

    if explicit_key is not None:
        # An explicit geometry key was provided — validate strictly.
        if isinstance(raw, Mapping):
            # GeoJSON shape object
            try:
                parsed = shape(raw)
                if not isinstance(parsed, Polygon):
                    from .exceptions import ELIAError
                    raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                                    f"Garage '{explicit_key}' must be a Polygon GeoJSON, got {raw.get('type')}.")
                rings = [list(parsed.exterior.coords)] + [list(interior.coords) for interior in parsed.interiors]
            except ELIAError:
                raise
            except Exception as exc:
                from .exceptions import ELIAError
                raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY", "Supplied garage geometry is malformed.") from exc
        elif isinstance(raw, (list, tuple)):
            if len(raw) == 0:
                # Case A: explicitly supplied empty polygon list → reject
                from .exceptions import ELIAError
                raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                                 f"Garage '{explicit_key}' must not be an empty list.")
            # Distinguish ring-of-rings vs flat ring based on first element
            if isinstance(raw[0], (list, tuple)) and raw[0] and isinstance(raw[0][0], (list, tuple)):
                # Ring-of-rings: [[exterior], [hole], ...]
                rings = list(raw)
            else:
                # Flat ring: [[x,y], [x,y], ...]
                rings = [raw]
        else:
            from .exceptions import ELIAError
            raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                             f"Garage '{explicit_key}' must be a list of coordinates or a GeoJSON object.")

        # Validate every point in every ring strictly — do not silently skip bad points/rings
        scaled_rings: list[list[tuple[float, float]]] = []
        for ring_index, ring in enumerate(rings):
            if not isinstance(ring, (list, tuple)):
                from .exceptions import ELIAError
                raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                                 f"Ring {ring_index} in garage '{explicit_key}' must be a list of points.")
            scaled_ring: list[tuple[float, float]] = []
            for pt_index, point in enumerate(ring):
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    # Case B: invalid/empty point in ring → reject whole geometry
                    from .exceptions import ELIAError
                    raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                                     f"Point {pt_index} in ring {ring_index} of garage '{explicit_key}' "
                                     f"is not a valid coordinate pair.")
                try:
                    x, y = float(point[0]), float(point[1])
                except (TypeError, ValueError) as exc:
                    from .exceptions import ELIAError
                    raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                                     f"Point {pt_index} in ring {ring_index} of garage '{explicit_key}' "
                                     f"must contain numeric values.") from exc
                if not (isfinite(x) and isfinite(y)):
                    from .exceptions import ELIAError
                    raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                                     f"Point {pt_index} in ring {ring_index} of garage '{explicit_key}' "
                                     f"must contain finite coordinates.")
                scaled_ring.append((x * scale, y * scale))
            # Each ring must have at least 3 distinct points (4 with closing repeat)
            distinct = scaled_ring if (len(scaled_ring) < 2 or scaled_ring[0] != scaled_ring[-1]) else scaled_ring[:-1]
            if len(distinct) < 3:
                # Case C: hole with fewer than 3 points → reject, do not drop silently
                kind = "exterior" if ring_index == 0 else f"hole {ring_index}"
                from .exceptions import ELIAError
                raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY",
                                 f"The {kind} ring of garage '{explicit_key}' has fewer than 3 distinct points.")
            scaled_rings.append(scaled_ring)

        polygon = Polygon(scaled_rings[0], scaled_rings[1:])
        if not polygon.is_valid or polygon.area <= 0:
            from .exceptions import ELIAError
            raise ELIAError("ELIA_INVALID_GARAGE_GEOMETRY", "Supplied garage polygon is invalid or has zero area.")
        return polygon

    # No explicit polygon/footprint/geometry key: fall back to center-based construction.
    center = point_xy(value, scale)
    if center:
        config = elia_rules()["access"]
        width = config["default_garage_width_m"] * int(value.get("capacity", 1))
        length = config["default_garage_length_m"]
        return box(center[0] - width / 2, center[1] - length / 2, center[0] + width / 2, center[1] + length / 2)
    return None




def _bay_dimensions(access: Mapping[str, Any], unit_scale: float) -> tuple[float, float]:
    config = elia_rules()["access"]
    def_w = float(config["default_garage_width_m"])
    def_l = float(config["default_garage_length_m"])
    profiles = access.get("vehicle_profiles") or [{"width": 1.8, "length": 4.5}]
    
    clearance_w = def_w - 1.8
    clearance_l = def_l - 4.5
    
    max_w, max_l = def_w, def_l
    for p in profiles:
        w = float(p["width_m"]) if p.get("width_m") is not None else float(p.get("width", 1.8)) * unit_scale
        l = float(p["length_m"]) if p.get("length_m") is not None else float(p.get("length", 4.5)) * unit_scale
        max_w = max(max_w, w + clearance_w)
        max_l = max(max_l, l + clearance_l)
        
    return max_w, max_l


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
        if residual.is_empty:
            return None
        source = "candidate"
        bay_w, bay_l = _bay_dimensions(access, unit_scale)
        width = bay_w * int(access.get("garage_capacity", 1))
        length = bay_l
        preferred = access.get("preferred_garage_location_m") or access.get("preferred_garage_location")
        if preferred:
            preferred_center = Point(float(preferred[0]), float(preferred[1]))
            min_x, min_y, max_x, max_y = residual.bounds
            step = max(width / 2, 1.0)
            
            estimated_cells = ((max_x - min_x) / step) * ((max_y - min_y) / step)
            if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
                from .exceptions import ELIAError
                raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search budget exhausted for garage.")
                
            fallback_candidates = [Point(x, y) for y in _frange(min_y + length / 2, max_y - length / 2, step)
                                   for x in _frange(min_x + width / 2, max_x - width / 2, step)]
            fallback_candidates.sort(key=lambda point: (point.distance(gate_point), point.y, point.x))
            candidates = [preferred_center, *fallback_candidates]
        else:
            min_x, min_y, max_x, max_y = residual.bounds
            step = max(width / 2, 1.0)
            
            estimated_cells = ((max_x - min_x) / step) * ((max_y - min_y) / step)
            if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
                from .exceptions import ELIAError
                raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search budget exhausted for garage.")
                
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
    bay_w, bay_l = _bay_dimensions(access, unit_scale)
    actual_capacity = _count_fitting_bays(garage, bay_w, bay_l)
    requested_capacity = int(access.get("garage_capacity", 1))
    if actual_capacity < requested_capacity:
        return None
    entry, approach = access_points
    rings = [list(garage.exterior.coords), *[list(interior.coords) for interior in garage.interiors]]
    serialized_polygon = rings if garage.interiors else rings[0]
    return {"json_id": "GARAGE_001", "polygon": serialized_polygon, "entry_point": list(entry),
            "access_point": list(approach),
            "capacity": actual_capacity, "source": source, "valid": True}


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
