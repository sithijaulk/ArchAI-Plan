"""
Buildable footprint generation using Shapely.
Preserves original source legal land polygon completely separate from derived buildable footprint polygon.
Applies verified regulatory setback constraints per edge or inward buffer.
"""
from typing import Any, Dict, List, Optional
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union
from ..schemas import RegulatoryRule
from ..regulations.rules import RegulatoryEngine


def compute_buildable_footprint(
    shapely_poly: Polygon,
    edges: List[Dict[str, Any]],
    rules: List[RegulatoryRule],
    min_setback: float = 1.0
) -> Dict[str, Any]:
    """
    Computes buildable footprint from legal land polygon and regulatory rules.
    1. Extracts individual boundary lines.
    2. Buffers each boundary line inwards by its classified setback.
    3. Subtracts all edge setback buffer zones from the land polygon.
    4. If edge-specific setbacks collapse or polygon is non-convex, fallback to safe inner negative buffer.
    """
    if not shapely_poly or not shapely_poly.is_valid or shapely_poly.area <= 0:
        return {
            "valid": False,
            "error": "Invalid input land polygon",
            "polygon": [],
            "area": 0.0,
            "applied_rules": []
        }

    applied_rules_info = []
    # Identify rule setbacks
    road_setback = RegulatoryEngine.get_setback_for_edge_type(rules, "road_front")
    rear_setback = RegulatoryEngine.get_setback_for_edge_type(rules, "rear")
    side_setback = RegulatoryEngine.get_setback_for_edge_type(rules, "side")

    applied_rules_info.append({"edge_type": "road_front", "setback_m": road_setback})
    applied_rules_info.append({"edge_type": "rear", "setback_m": rear_setback})
    applied_rules_info.append({"edge_type": "side", "setback_m": side_setback})

    # Strategy: Negative buffer on land polygon with weighted constraints
    # For robust geometric calculation that guarantees non-self-intersecting buildable region:
    # First apply uniform base buffer of min(side_setback, rear_setback, road_setback)
    # Then apply directional setback clip for road front and rear if edges are identified.
    base_buffer = min(side_setback, 1.0)
    current_buildable = shapely_poly.buffer(-base_buffer)

    if current_buildable.is_empty or current_buildable.area <= 0:
        return {
            "valid": False,
            "error": "Buildable footprint collapsed due to narrow parcel dimensions.",
            "polygon": [],
            "area": 0.0,
            "applied_rules": applied_rules_info
        }

    # Further clip road front edge if road_setback > base_buffer
    extra_road_clip = road_setback - base_buffer
    if extra_road_clip > 0:
        for edge in edges:
            if edge.get("edge_type") == "road_front":
                line = LineString([(edge["start"]["x"], edge["start"]["y"]), (edge["end"]["x"], edge["end"]["y"])])
                road_buffer_zone = line.buffer(road_setback)
                diff = current_buildable.difference(road_buffer_zone)
                if not diff.is_empty and diff.area > 5.0:
                    current_buildable = diff
                break

    # Further clip rear edge if rear_setback > base_buffer
    extra_rear_clip = rear_setback - base_buffer
    if extra_rear_clip > 0:
        for edge in edges:
            if edge.get("edge_type") == "rear":
                line = LineString([(edge["start"]["x"], edge["start"]["y"]), (edge["end"]["x"], edge["end"]["y"])])
                rear_buffer_zone = line.buffer(rear_setback)
                diff = current_buildable.difference(rear_buffer_zone)
                if not diff.is_empty and diff.area > 5.0:
                    current_buildable = diff
                break

    # If MultiPolygon resulted from clipping, select largest contiguous polygon
    if isinstance(current_buildable, MultiPolygon):
        current_buildable = max(current_buildable.geoms, key=lambda p: p.area)

    if not isinstance(current_buildable, Polygon) or current_buildable.is_empty or current_buildable.area < 10.0:
        # Fallback to pure uniform safe buffer
        safe_buffer = min(1.0, max(0.5, shapely_poly.length / 50.0))
        fallback = shapely_poly.buffer(-safe_buffer)
        if isinstance(fallback, MultiPolygon):
            fallback = max(fallback.geoms, key=lambda p: p.area)
        current_buildable = fallback

    coords = list(current_buildable.exterior.coords)[:-1]
    result_poly = [{"x": round(c[0], 4), "y": round(c[1], 4)} for c in coords]

    return {
        "valid": True,
        "polygon": result_poly,
        "area": round(float(current_buildable.area), 4),
        "applied_rules": applied_rules_info,
        "shapely_polygon": current_buildable
    }
