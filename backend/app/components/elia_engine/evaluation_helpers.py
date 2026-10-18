"""Reusable ELIA-owned evaluation and geometry validation helpers.

Provides robust, contract-aligned helpers for:
- Finite numeric validation
- Physical footprint extraction
- Supporting-surface resolution
- Geometry and guard protection validation
- Evidence scope and revision validation
- Canonical object indexing and protected-property comparison
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry


def to_finite_float(val: Any) -> float | None:
    """Convert value to float if finite, rejecting booleans, None, strings, and non-finite numbers."""
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def to_positive_finite_float(val: Any) -> float | None:
    """Convert value to positive float (> 0) if finite, rejecting booleans and non-positive values."""
    f = to_finite_float(val)
    if f is not None and f > 0.0:
        return f
    return None


def extract_physical_footprint(
    obj: Mapping[str, Any],
) -> tuple[BaseGeometry | None, str]:
    """Extract the physical 2D footprint geometry for a container or outdoor element.
    
    Returns:
        (geometry, status)
        where status is one of:
        - "valid"
        - "missing"
        - "missing_dimensions"
        - "malformed"
        - "non_finite"
    """
    if not isinstance(obj, Mapping):
        return None, "malformed"

    # 1. Explicit polygon or footprint provided
    poly_raw = obj.get("footprint") or obj.get("polygon")
    if poly_raw is not None:
        if not isinstance(poly_raw, (list, tuple)) or len(poly_raw) < 3:
            return None, "malformed"
        clean_pts = []
        for pt in poly_raw:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                return None, "malformed"
            x = to_finite_float(pt[0])
            y = to_finite_float(pt[1])
            if x is None or y is None:
                return None, "non_finite"
            clean_pts.append((x, y))
        try:
            poly = Polygon(clean_pts)
            if not poly.is_valid or poly.is_empty or poly.area <= 0:
                return None, "malformed"
            # Apply rotation if present
            rot = to_finite_float(obj.get("rotation_degrees"))
            if rot is not None and rot % 360.0 != 0:
                poly = affinity.rotate(poly, rot, origin="center")
            return poly, "valid"
        except Exception:
            return None, "malformed"

    # 2. Position + Dimensions
    pos = obj.get("position")
    if pos is None:
        return None, "missing"
    if not isinstance(pos, (list, tuple)) or len(pos) < 2:
        return None, "malformed"
    px = to_finite_float(pos[0])
    py = to_finite_float(pos[1])
    if px is None or py is None:
        return None, "non_finite"

    dims = obj.get("dimensions")
    w = None
    d = None
    if isinstance(dims, Mapping):
        w = to_positive_finite_float(dims.get("width_m") or dims.get("width"))
        d = to_positive_finite_float(dims.get("depth_m") or dims.get("depth") or dims.get("length_m") or dims.get("length"))
    if w is None:
        w = to_positive_finite_float(obj.get("width_m") or obj.get("width"))
    if d is None:
        d = to_positive_finite_float(obj.get("depth_m") or obj.get("depth") or obj.get("length_m") or obj.get("length"))

    # Explicit rule: Do not invent 0.4m defaults or substitute canopy radius!
    if w is None or d is None:
        return None, "missing_dimensions"

    try:
        b = box(px - w / 2.0, py - d / 2.0, px + w / 2.0, py + d / 2.0)
        rot = to_finite_float(obj.get("rotation_degrees"))
        if rot is not None and rot % 360.0 != 0:
            b = affinity.rotate(b, rot, origin="center")
        return b, "valid"
    except Exception:
        return None, "malformed"


def resolve_supporting_surface(
    planter: Mapping[str, Any],
    available_surfaces: list[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, str]:
    """Resolve an elevated planter to its authoritative supporting surface.
    
    Returns:
        (surface_dict, status)
        where status is one of:
        - "resolved"
        - "unresolved"
        - "contradictory_floor"
        - "contradictory_elevation"
        - "duplicate_id"
        - "missing_evidence"
    """
    if not available_surfaces:
        return None, "unresolved"

    # Detect duplicate IDs in available surfaces
    seen_ids = set()
    dup_ids = set()
    surface_by_id: dict[str, Mapping[str, Any]] = {}
    for s in available_surfaces:
        if isinstance(s, Mapping):
            sid = str(s.get("json_id") or s.get("id") or "").strip()
            if sid:
                if sid in seen_ids:
                    dup_ids.add(sid)
                seen_ids.add(sid)
                surface_by_id[sid] = s

    if dup_ids:
        return None, "duplicate_id"

    supp_id = str(planter.get("support_json_id") or planter.get("supporting_surface_id") or "").strip()
    pl_floor = planter.get("floor_id")
    pl_elev = to_finite_float(planter.get("elevation_m"))

    if supp_id:
        if supp_id not in surface_by_id:
            # Explicit invalid surface ID must not fall back to another surface
            return None, "unresolved"
        surf = surface_by_id[supp_id]
        surf_floor = surf.get("floor_id")
        if pl_floor and surf_floor and str(pl_floor).strip() != str(surf_floor).strip():
            return None, "contradictory_floor"
        surf_elev = to_finite_float(surf.get("elevation_m"))
        if pl_elev is not None and surf_elev is not None and abs(pl_elev - surf_elev) > 0.5:
            return None, "contradictory_elevation"
        return surf, "resolved"

    # When supp_id is not specified, require floor/elevation evidence to establish relationship
    if pl_floor:
        matching = [s for s in available_surfaces if isinstance(s, Mapping) and str(s.get("floor_id") or "").strip() == str(pl_floor).strip()]
        if len(matching) == 1:
            return matching[0], "resolved"
        elif len(matching) > 1:
            return None, "missing_evidence"
        else:
            return None, "unresolved"

    if pl_elev is not None:
        matching = [
            s for s in available_surfaces
            if isinstance(s, Mapping) and to_finite_float(s.get("elevation_m")) is not None
            and abs(to_finite_float(s.get("elevation_m")) - pl_elev) <= 0.5
        ]
        if len(matching) == 1:
            return matching[0], "resolved"

    # A single balcony in the project is not proof that every planter belongs to it
    return None, "missing_evidence"


def validate_surface_slab_polygon(
    surface: Mapping[str, Any],
) -> tuple[Polygon | None, str]:
    """Validate and return the usable structural slab polygon of a surface."""
    poly_raw = surface.get("polygon") or surface.get("footprint")
    if not poly_raw or not isinstance(poly_raw, (list, tuple)) or len(poly_raw) < 3:
        return None, "missing_or_malformed"

    clean_pts = []
    for pt in poly_raw:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return None, "malformed"
        x = to_finite_float(pt[0])
        y = to_finite_float(pt[1])
        if x is None or y is None:
            return None, "non_finite"
        clean_pts.append((x, y))

    try:
        poly = Polygon(clean_pts)
        if not poly.is_valid or poly.is_empty or poly.area <= 0:
            return None, "invalid"
        return poly, "valid"
    except Exception:
        return None, "invalid"


PROHIBITED_MOUNTING_VALUES = {
    "railing_top",
    "on_guard",
    "outside_barrier",
    "guardrail_top",
    "balcony_railing",
    "mounted_on_railing",
    "balcony_edge_top",
    "railing",
    "on_railing",
    "outside_guard",
}


def is_prohibited_balcony_mounting(mounting_type: Any) -> bool:
    """Check if mounting type explicitly specifies railing-top or outside-barrier mounting."""
    if not mounting_type or not isinstance(mounting_type, str):
        return False
    val = mounting_type.strip().lower()
    return val in PROHIBITED_MOUNTING_VALUES or val.startswith("railing_") or val.startswith("outside_")


def validate_guardrail_protection(
    surface: Mapping[str, Any],
    planter_geom: BaseGeometry,
) -> tuple[bool, str, str]:
    """Validate whether a planter footprint is inside the protected zone of a balcony guardrail.
    
    Returns:
        (is_protected, status, message)
        where status is one of:
        - "protected"
        - "outside_protected"
        - "malformed_guard"
        - "unresolved_protected_side"
        - "missing_guard"
    """
    prot_raw = surface.get("protected_region")
    if prot_raw is not None:
        if not isinstance(prot_raw, (list, tuple)) or len(prot_raw) < 3:
            return False, "malformed_guard", "protected_region is malformed or has fewer than 3 vertices"
        pts = []
        for pt in prot_raw:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                return False, "malformed_guard", "protected_region vertex coordinates malformed"
            x = to_finite_float(pt[0])
            y = to_finite_float(pt[1])
            if x is None or y is None:
                return False, "malformed_guard", "protected_region non-finite coordinates"
            pts.append((x, y))
        try:
            prot_poly = Polygon(pts)
            if not prot_poly.is_valid or prot_poly.is_empty:
                return False, "malformed_guard", "protected_region polygon is invalid or empty"
            if prot_poly.covers(planter_geom):
                return True, "protected", "Footprint contained within protected region envelope"
            return False, "outside_protected", "Footprint extends outside protected region envelope"
        except Exception:
            return False, "malformed_guard", "Error parsing protected_region polygon"

    guard_raw = surface.get("guardrail") or surface.get("guard")
    if guard_raw is None:
        return False, "missing_guard", "No guardrail or protected region defined on surface"

    if not isinstance(guard_raw, (list, tuple)):
        # Malformed string, number, or arbitrary dict
        return False, "malformed_guard", "guardrail geometry is not a valid coordinate sequence"

    if len(guard_raw) < 2:
        return False, "malformed_guard", "guardrail geometry has fewer than 2 points"

    pts = []
    for pt in guard_raw:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return False, "malformed_guard", "guardrail vertex is not a valid coordinate pair"
        x = to_finite_float(pt[0])
        y = to_finite_float(pt[1])
        if x is None or y is None:
            return False, "malformed_guard", "guardrail contains non-finite coordinates"
        pts.append((x, y))

    # Closed polygon guard envelope
    if len(pts) >= 3 and pts[0] == pts[-1]:
        try:
            g_poly = Polygon(pts)
            if not g_poly.is_valid or g_poly.is_empty:
                return False, "malformed_guard", "guardrail polygon is invalid"
            if g_poly.covers(planter_geom):
                return True, "protected", "Footprint contained inside guardrail envelope"
            return False, "outside_protected", "Footprint outside guardrail envelope"
        except Exception:
            return False, "malformed_guard", "guardrail polygon parsing failed"

    # Open LineString guard line
    try:
        g_line = LineString(pts)
        if not g_line.is_valid or g_line.is_empty:
            return False, "malformed_guard", "guardrail LineString is invalid"
        if g_line.intersects(planter_geom):
            return False, "outside_protected", "Planter footprint intersects the guardrail boundary line"
        # Open line alone does not prove which side is protected without explicit protected_region
        return False, "unresolved_protected_side", "Open guard line present but protected interior side is ambiguous without protected_region"
    except Exception:
        return False, "malformed_guard", "guardrail LineString parsing failed"


def collect_canonical_objects(
    root: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Index all supported ELIA candidate or reference objects symmetrically.
    
    Covers:
    - vegetation_nodes
    - outdoor_elements
    - outdoor_lighting.nodes
    - access (garage, driveway, walkway, gate, boundary_wall, etc.)
    - vertical_greenery.elements
    
    Returns:
        (objects_by_id, duplicate_ids)
    """
    objs_by_id: dict[str, dict[str, Any]] = {}
    dup_ids: list[str] = []

    def _add_item(item: Any, default_type: str = "element"):
        if not isinstance(item, Mapping):
            return
        iid = str(item.get("json_id") or item.get("id") or item.get("featureId") or "").strip()
        if not iid:
            return
        if iid in objs_by_id:
            dup_ids.append(iid)
        d_item = dict(item)
        if "type" not in d_item and default_type:
            d_item["type"] = default_type
        objs_by_id[iid] = d_item

    if not isinstance(root, Mapping):
        return objs_by_id, dup_ids

    # 1. Vegetation nodes
    for v in root.get("vegetation_nodes") or []:
        _add_item(v, "vegetation")

    # 2. Outdoor elements
    for o in root.get("outdoor_elements") or []:
        _add_item(o, "outdoor_element")

    # 3. Outdoor lighting nodes
    lighting_container = root.get("outdoor_lighting")
    if isinstance(lighting_container, Mapping):
        for lt in lighting_container.get("nodes") or []:
            _add_item(lt, "lighting_fixture")
    elif isinstance(lighting_container, list):
        for lt in lighting_container:
            _add_item(lt, "lighting_fixture")

    # 4. Access objects
    access_container = root.get("access")
    if isinstance(access_container, Mapping):
        for acc_k, acc_v in access_container.items():
            if isinstance(acc_v, Mapping):
                # Ensure type defaults to the access key if not set
                _add_item(acc_v, acc_k)
            elif isinstance(acc_v, list):
                for sub_item in acc_v:
                    _add_item(sub_item, acc_k)
    elif isinstance(access_container, list):
        for acc_item in access_container:
            _add_item(acc_item, "access_element")

    # 5. Vertical greenery elements
    vert_container = root.get("vertical_greenery")
    if isinstance(vert_container, Mapping):
        for vg in vert_container.get("elements") or []:
            _add_item(vg, "vertical_greenery")
    elif isinstance(vert_container, list):
        for vg in vert_container:
            _add_item(vg, "vertical_greenery")

    return objs_by_id, sorted(set(dup_ids))


def compare_locked_object_properties(
    ref_obj: Mapping[str, Any],
    cand_obj: Mapping[str, Any],
) -> list[str]:
    """Compare all protected properties of a locked object between reference and candidate.
    
    Returns a list of violation strings. An empty list indicates verified invariance.
    """
    violations: list[str] = []
    rid = str(ref_obj.get("json_id") or ref_obj.get("id") or "object").strip()

    # 1. Type
    r_type = ref_obj.get("type") or ref_obj.get("category")
    c_type = cand_obj.get("type") or cand_obj.get("category")
    if r_type and c_type != r_type:
        violations.append(f"locked_type_changed({rid}: {r_type} -> {c_type})")

    # 2. Species / plant identity
    r_sp = ref_obj.get("plant_id") or ref_obj.get("species_id") or ref_obj.get("vegetation_id")
    c_sp = cand_obj.get("plant_id") or cand_obj.get("species_id") or cand_obj.get("vegetation_id")
    if r_sp and c_sp != r_sp:
        violations.append(f"locked_species_changed({rid}: {r_sp} -> {c_sp})")

    # 3. Position (finite coordinates, 2D and 3D)
    r_pos = ref_obj.get("position")
    c_pos = cand_obj.get("position")
    if r_pos is not None:
        if c_pos is None or not isinstance(c_pos, (list, tuple)) or len(c_pos) < 2:
            violations.append(f"locked_position_removed({rid})")
        else:
            rx, ry = to_finite_float(r_pos[0]), to_finite_float(r_pos[1])
            cx, cy = to_finite_float(c_pos[0]), to_finite_float(c_pos[1])
            if rx is None or ry is None or cx is None or cy is None:
                violations.append(f"locked_position_invalid({rid})")
            elif abs(cx - rx) > 1e-3 or abs(cy - ry) > 1e-3:
                violations.append(f"locked_position_changed({rid}: {r_pos} -> {c_pos})")
            elif len(r_pos) >= 3:
                if len(c_pos) < 3:
                    violations.append(f"locked_z_coordinate_removed({rid})")
                else:
                    rz = to_finite_float(r_pos[2])
                    cz = to_finite_float(c_pos[2])
                    if rz is None or cz is None:
                        violations.append(f"locked_z_coordinate_invalid({rid})")
                    elif abs(cz - rz) > 1e-3:
                        violations.append(f"locked_z_coordinate_changed({rid}: {rz} -> {cz})")

    # 4. Elevation
    r_elev = ref_obj.get("elevation_m")
    c_elev = cand_obj.get("elevation_m")
    if r_elev is not None:
        if c_elev is None:
            violations.append(f"locked_elevation_removed({rid})")
        else:
            re = to_finite_float(r_elev)
            ce = to_finite_float(c_elev)
            if re is None or ce is None:
                violations.append(f"locked_elevation_invalid({rid})")
            elif abs(ce - re) > 1e-3:
                violations.append(f"locked_elevation_changed({rid}: {re} -> {ce})")

    # 5. Dimensions and individual dimension keys
    r_dims = ref_obj.get("dimensions")
    c_dims = cand_obj.get("dimensions")
    if isinstance(r_dims, Mapping):
        if not isinstance(c_dims, Mapping):
            violations.append(f"locked_dimensions_removed({rid})")
        else:
            for dim_k, dim_v in r_dims.items():
                if dim_k not in c_dims:
                    violations.append(f"locked_dimension_key_removed({rid}.{dim_k})")
                else:
                    rv = to_finite_float(dim_v)
                    cv = to_finite_float(c_dims[dim_k])
                    if rv is None or cv is None:
                        violations.append(f"locked_dimension_invalid({rid}.{dim_k})")
                    elif abs(cv - rv) > 1e-3:
                        violations.append(f"locked_dimension_changed({rid}.{dim_k}: {dim_v} -> {c_dims[dim_k]})")

    for dim_prop in ("width_m", "depth_m", "height_m", "canopy_radius_m"):
        if ref_obj.get(dim_prop) is not None:
            if cand_obj.get(dim_prop) is None:
                violations.append(f"locked_{dim_prop}_removed({rid})")
            else:
                rv = to_finite_float(ref_obj[dim_prop])
                cv = to_finite_float(cand_obj[dim_prop])
                if rv is None or cv is None:
                    violations.append(f"locked_{dim_prop}_invalid({rid})")
                elif abs(cv - rv) > 1e-3:
                    violations.append(f"locked_{dim_prop}_changed({rid}: {rv} -> {cv})")

    # 6. Rotation
    r_rot = ref_obj.get("rotation_degrees")
    c_rot = cand_obj.get("rotation_degrees")
    if r_rot is not None:
        if c_rot is None:
            violations.append(f"locked_rotation_removed({rid})")
        else:
            rr = to_finite_float(r_rot)
            cr = to_finite_float(c_rot)
            if rr is None or cr is None:
                violations.append(f"locked_rotation_invalid({rid})")
            else:
                drot = abs(cr - rr) % 360.0
                if drot > 180.0:
                    drot = 360.0 - drot
                if drot > 1e-3:
                    violations.append(f"locked_rotation_changed({rid}: {rr}° -> {cr}°)")

    # 7. Scale
    r_sc = ref_obj.get("scale") or ref_obj.get("scale_xyz")
    c_sc = cand_obj.get("scale") or cand_obj.get("scale_xyz")
    if r_sc is not None:
        if c_sc is None:
            violations.append(f"locked_scale_removed({rid})")
        elif r_sc != c_sc:
            violations.append(f"locked_scale_changed({rid}: {r_sc} -> {c_sc})")

    # 8. Footprint / Polygon
    r_poly = ref_obj.get("polygon") or ref_obj.get("footprint")
    c_poly = cand_obj.get("polygon") or cand_obj.get("footprint")
    if r_poly is not None:
        if c_poly is None:
            violations.append(f"locked_polygon_removed({rid})")
        else:
            try:
                g_r = Polygon(r_poly)
                g_c = Polygon(c_poly)
                if not g_r.equals_exact(g_c, tolerance=1e-3):
                    violations.append(f"locked_polygon_changed({rid})")
            except Exception:
                violations.append(f"locked_polygon_invalid({rid})")

    # 9. Support surface and floor
    r_supp = ref_obj.get("support_json_id") or ref_obj.get("supporting_surface_id")
    c_supp = cand_obj.get("support_json_id") or cand_obj.get("supporting_surface_id")
    if r_supp is not None and c_supp != r_supp:
        violations.append(f"locked_support_surface_changed({rid}: {r_supp} -> {c_supp})")

    r_fl = ref_obj.get("floor_id")
    c_fl = cand_obj.get("floor_id")
    if r_fl is not None and c_fl != r_fl:
        violations.append(f"locked_floor_changed({rid}: {r_fl} -> {c_fl})")

    return violations
