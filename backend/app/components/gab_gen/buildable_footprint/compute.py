"""
Deterministic edge-aware buildable footprint generation using Shapely.
Preserves original source legal land polygon in canonical P0 coordinates.
Applies verified regulatory setback constraints per edge or inward buffer without arbitrary safe fallbacks.
Records exact rule IDs applied, affected edge IDs, setback values, and returns infeasible if site collapses.
"""
from typing import Any, Dict, List, Optional
from shapely.geometry import Polygon, MultiPolygon, LineString
from ..schemas import RegulatoryRule
from ..regulations.rules import RegulatoryEngine


def compute_buildable_footprint(
    shapely_poly: Polygon,
    edges: List[Dict[str, Any]],
    rules: List[RegulatoryRule]
) -> Dict[str, Any]:
    """
    Computes buildable footprint from legal land polygon and regulatory rules.
    Traceability:
      - records exact rule_id applied
      - records affected_edge_id
      - records setback value
    Geometry:
      - strictly respects canonical coordinate system
      - no arbitrary fallback buffer (e.g. 0.5m/1m arbitrary fallback)
      - if setbacks collapse site or yield empty/infeasible polygon, returns valid=False & status=infeasible
    """
    if not shapely_poly or not shapely_poly.is_valid or shapely_poly.area <= 0:
        return {
            "valid": False,
            "status": "failed",
            "error": "Invalid or non-existent input land polygon",
            "polygon": [],
            "area": 0.0,
            "applied_rules": []
        }

    if not rules:
        return {
            "valid": False,
            "status": "regulatory_configuration_required",
            "error": "No verified regulatory setback rules supplied.",
            "polygon": [],
            "area": 0.0,
            "applied_rules": []
        }

    # Map each edge to its applied rule
    applied_rules_info: List[Dict[str, Any]] = []
    current_buildable = shapely_poly

    for edge in edges:
        edge_id = edge.get("edge_id")
        edge_type = edge.get("edge_type", "side")
        rule = RegulatoryEngine.get_rule_for_edge_type(rules, edge_type)

        if rule is not None:
            setback_m = rule.value
            applied_rules_info.append({
                "rule_id": rule.rule_id,
                "authority": rule.authority,
                "edge_id": edge_id,
                "edge_type": edge_type,
                "setback_m": setback_m,
                "verification_status": rule.verification_status
            })

            # Create boundary line segment
            p1 = (edge["start"]["x"], edge["start"]["y"])
            p2 = (edge["end"]["x"], edge["end"]["y"])
            edge_line = LineString([p1, p2])

            # Buffer outward from line by setback_m to define restricted setback zone
            setback_zone = edge_line.buffer(setback_m)
            current_buildable = current_buildable.difference(setback_zone)
        else:
            # If no rule covers this edge type, record missing configuration
            applied_rules_info.append({
                "rule_id": None,
                "edge_id": edge_id,
                "edge_type": edge_type,
                "setback_m": 0.0,
                "note": "no_specific_rule_applied"
            })

    # Validate resulting geometry
    if current_buildable.is_empty or current_buildable.area <= 0:
        return {
            "valid": False,
            "status": "infeasible",
            "error": "Regulatory setbacks collapse the site completely. Buildable footprint area is 0 m².",
            "polygon": [],
            "area": 0.0,
            "applied_rules": applied_rules_info,
            "shapely_polygon": None
        }

    # Handle MultiPolygon explicitly
    if isinstance(current_buildable, MultiPolygon):
        # Deterministically select largest contiguous feasible parcel polygon
        polys = [p for p in current_buildable.geoms if p.area > 0]
        if not polys:
            return {
                "valid": False,
                "status": "infeasible",
                "error": "Regulatory setbacks fragmented site into unusable non-contiguous fragments.",
                "polygon": [],
                "area": 0.0,
                "applied_rules": applied_rules_info,
                "shapely_polygon": None
            }
        current_buildable = max(polys, key=lambda p: p.area)

    # Minimum feasible footprint area threshold (e.g., at least 15 sqm for any residential room)
    if current_buildable.area < 15.0:
        return {
            "valid": False,
            "status": "infeasible",
            "error": f"Derived buildable footprint area ({current_buildable.area:.2f} m²) is architecturally inadequate to support residential dwelling.",
            "polygon": [],
            "area": round(float(current_buildable.area), 4),
            "applied_rules": applied_rules_info,
            "shapely_polygon": current_buildable
        }

    coords = list(current_buildable.exterior.coords)[:-1]
    result_poly = [{"x": round(c[0], 4), "y": round(c[1], 4)} for c in coords]

    return {
        "valid": True,
        "status": "completed",
        "polygon": result_poly,
        "area": round(float(current_buildable.area), 4),
        "applied_rules": applied_rules_info,
        "shapely_polygon": current_buildable
    }
