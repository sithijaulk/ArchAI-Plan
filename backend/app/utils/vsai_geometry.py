import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


class GeometryValidationError(ValueError):
    """Raised when input geometry cannot safely be processed."""


def validate_polygon(value: Any, label: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) < 3:
        raise GeometryValidationError(f"{label} must be a polygon with at least three [x, y] points")

    points: list[list[float]] = []
    for index, point in enumerate(value):
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 2
            or any(isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) for coordinate in point)
        ):
            raise GeometryValidationError(f"{label}[{index}] must contain exactly two numeric coordinates")
        coordinates = [float(coordinate) for coordinate in point]
        if not all(math.isfinite(coordinate) for coordinate in coordinates):
            raise GeometryValidationError(f"{label}[{index}] coordinates must be finite")
        points.append(coordinates)

    open_points = points[:-1] if points[0] == points[-1] else points
    if len(open_points) < 3 or len(set(map(tuple, open_points))) < 3:
        raise GeometryValidationError(f"{label} is degenerate")
    if _has_self_intersection(open_points):
        raise GeometryValidationError(f"{label} self-intersects")
    if _signed_area(open_points) == 0:
        raise GeometryValidationError(f"{label} has zero area")
    return points


def validate_floor_plan(floor_plan: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(floor_plan, Mapping):
        raise GeometryValidationError("floor_plan must be an object")
    rooms = floor_plan.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        raise GeometryValidationError("floor_plan.rooms must contain at least one room with a polygon")

    result: dict[str, list[dict[str, Any]]] = {"rooms": [], "structural_elements": []}
    for collection_name in ("rooms", "structural_elements"):
        elements = rooms if collection_name == "rooms" else floor_plan.get(collection_name, [])
        if not isinstance(elements, list):
            raise GeometryValidationError(f"floor_plan.{collection_name} must be an array")
        seen_ids: set[str] = set()
        for index, element in enumerate(elements):
            label = f"floor_plan.{collection_name}[{index}]"
            if not isinstance(element, Mapping):
                raise GeometryValidationError(f"{label} must be an object")
            element_id = element.get("id")
            if not isinstance(element_id, str) or not element_id.strip():
                raise GeometryValidationError(f"{label}.id must be a non-empty string")
            if element_id in seen_ids:
                raise GeometryValidationError(f"Duplicate id '{element_id}' in floor_plan.{collection_name}")
            seen_ids.add(element_id)
            polygon = validate_polygon(element.get("polygon"), f"{label}.polygon")
            result[collection_name].append({
                **deepcopy(dict(element)),
                "id": element_id,
                "polygon": polygon,
            })
    return result


def find_room_overlaps(rooms: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    overlaps: list[dict[str, str]] = []
    for index, first in enumerate(rooms):
        for second in rooms[index + 1:]:
            if _polygons_overlap(first["polygon"], second["polygon"]):
                overlaps.append({"first_room_id": first["id"], "second_room_id": second["id"]})
    return overlaps


def _signed_area(points: Sequence[Sequence[float]]) -> float:
    return sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    ) / 2


def _orientation(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Sequence[float], b: Sequence[float], point: Sequence[float]) -> bool:
    return (
        min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
        and _orientation(a, b, point) == 0
    )


def _segments_intersect(
    a: Sequence[float], b: Sequence[float], c: Sequence[float], d: Sequence[float]
) -> bool:
    first = _orientation(a, b, c)
    second = _orientation(a, b, d)
    third = _orientation(c, d, a)
    fourth = _orientation(c, d, b)
    if ((first > 0 > second) or (second > 0 > first)) and (
        (third > 0 > fourth) or (fourth > 0 > third)
    ):
        return True
    return (
        (first == 0 and _on_segment(a, b, c))
        or (second == 0 and _on_segment(a, b, d))
        or (third == 0 and _on_segment(c, d, a))
        or (fourth == 0 and _on_segment(c, d, b))
    )


def _has_self_intersection(points: Sequence[Sequence[float]]) -> bool:
    edge_count = len(points)
    for first in range(edge_count):
        a, b = points[first], points[(first + 1) % edge_count]
        for second in range(first + 1, edge_count):
            if second == first + 1 or (first == 0 and second == edge_count - 1):
                continue
            c, d = points[second], points[(second + 1) % edge_count]
            if _segments_intersect(a, b, c, d):
                return True
    return False


def _point_strictly_inside(point: Sequence[float], polygon: Sequence[Sequence[float]]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if _on_segment(previous, current, point):
            return False
        if (current[1] > point[1]) != (previous[1] > point[1]):
            crossing_x = (previous[0] - current[0]) * (point[1] - current[1]) / (
                previous[1] - current[1]
            ) + current[0]
            if point[0] < crossing_x:
                inside = not inside
        previous = current
    return inside


def _polygons_overlap(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]]) -> bool:
    first_points = first[:-1] if first[0] == first[-1] else first
    second_points = second[:-1] if second[0] == second[-1] else second
    for index in range(len(first_points)):
        a, b = first_points[index], first_points[(index + 1) % len(first_points)]
        for other in range(len(second_points)):
            c, d = second_points[other], second_points[(other + 1) % len(second_points)]
            first_side, second_side = _orientation(a, b, c), _orientation(a, b, d)
            third_side, fourth_side = _orientation(c, d, a), _orientation(c, d, b)
            if ((first_side > 0 > second_side) or (second_side > 0 > first_side)) and (
                (third_side > 0 > fourth_side) or (fourth_side > 0 > third_side)
            ):
                return True
    first_samples = list(first_points) + [
        [(first_points[index][0] + first_points[(index + 1) % len(first_points)][0]) / 2,
         (first_points[index][1] + first_points[(index + 1) % len(first_points)][1]) / 2]
        for index in range(len(first_points))
    ]
    second_samples = list(second_points) + [
        [(second_points[index][0] + second_points[(index + 1) % len(second_points)][0]) / 2,
         (second_points[index][1] + second_points[(index + 1) % len(second_points)][1]) / 2]
        for index in range(len(second_points))
    ]
    if any(_point_strictly_inside(point, second_points) for point in first_samples) or any(
        _point_strictly_inside(point, first_points) for point in second_samples
    ):
        return True
    return _point_strictly_inside(first_points[0], second_points) or _point_strictly_inside(
        second_points[0], first_points
    )
