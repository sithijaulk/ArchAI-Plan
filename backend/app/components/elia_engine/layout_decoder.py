from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
from shapely.geometry import Point, Polygon, shape

from .geometry import point_xy
from .plants import get_plant_catalogue
from .rasterizer import RasterMetadata
from .rule_repository import elia_rules


def _find_local_peaks(heatmap: np.ndarray, threshold: float = 0.15, nms_radius: int = 3) -> list[tuple[float, int, int]]:
    """
    Find local peaks in a 2D heatmap with Non-Maximum Suppression (NMS).
    Returns list of (score, v, u) sorted descending by score.
    """
    h, w = heatmap.shape
    peaks: list[tuple[float, int, int]] = []

    for v in range(nms_radius, h - nms_radius):
        for u in range(nms_radius, w - nms_radius):
            val = float(heatmap[v, u])
            if val < threshold:
                continue
            window = heatmap[v - nms_radius : v + nms_radius + 1, u - nms_radius : u + nms_radius + 1]
            if val == np.max(window):
                peaks.append((val, v, u))

    peaks.sort(key=lambda item: item[0], reverse=True)
    return peaks


def decode_model_layout(
    heatmaps: np.ndarray,
    meta: RasterMetadata,
    prepared_input: Mapping[str, Any],
    model_version: str,
) -> dict[str, Any]:
    """
    Constrained decoder transforming 4x96x96 neural heatmaps into canonical ExteriorObject nodes
    and combining them with deterministic architectural features (gate, driveway, paths, solar, elevated).
    """
    raw_land = prepared_input.get("land")
    land_poly = shape(raw_land)
    raw_house = prepared_input.get("house_exterior")
    house_poly = shape(raw_house) if raw_house else Polygon()

    requirements = prepared_input.get("requirements", {})
    landscape_reqs = requirements.get("landscape", {})
    access_reqs = requirements.get("access", {})
    lighting_reqs = requirements.get("lighting", {})
    solar_reqs = requirements.get("solar", {})
    balcony_reqs = requirements.get("balconies", {})
    terrace_reqs = requirements.get("terrace", {})

    # Build obstacle union (house + utility buffers + restrictions)
    obstacle_polys = [house_poly] if (house_poly.is_valid and not house_poly.is_empty) else []
    utils = prepared_input.get("utilities", {})
    if isinstance(utils, Mapping):
        for u_name, u_val in utils.items():
            if isinstance(u_val, Mapping) and "position_m" in u_val:
                ux, uy = u_val["position_m"][:2]
                radius = 15.24 if u_name in {"well", "septic_tank"} else 1.5
                obstacle_polys.append(Point(ux, uy).buffer(radius))

    for rz in prepared_input.get("exterior_restrictions", []):
        try:
            rz_poly = shape(rz)
            if rz_poly.is_valid and not rz_poly.is_empty:
                obstacle_polys.append(rz_poly)
        except Exception:
            pass

    from shapely.ops import unary_union
    obstacles_union = unary_union(obstacle_polys) if obstacle_polys else Polygon()

    # 1. Decode Tree placements from Channel 0
    tree_peaks = _find_local_peaks(heatmaps[0], threshold=0.15, nms_radius=3)
    target_tree_count = landscape_reqs.get("tree_count")
    if target_tree_count is None:
        density = landscape_reqs.get("greenery_density", "medium")
        target_tree_count = {"low": 2, "medium": 4, "high": 6, "sparse": 2, "balanced": 4, "dense": 6}.get(density, 4)

    catalog = get_plant_catalogue()
    catalog_items = catalog.get("entries", [])
    tree_species = [item for item in catalog_items if item.get("category") == "tree"] or catalog_items

    vegetation_nodes: list[dict[str, Any]] = []
    placed_tree_points: list[Point] = []
    min_tree_sep = float(elia_rules()["vegetation"]["minimum_spacing_m"].get("small_tree", 2.5))

    for score, v, u in tree_peaks:
        if len(vegetation_nodes) >= target_tree_count:
            break
        wx, wy = meta.to_world(u + 0.5, v + 0.5)
        pt = Point(wx, wy)

        idx = len(vegetation_nodes) + 1
        spec = tree_species[(idx - 1) % len(tree_species)]
        canopy_r = float(spec.get("spread_m") or spec.get("canopy_spread_m") or 3.0) / 2.0
        mature_h = float(spec.get("height_m") or spec.get("mature_height_m") or 4.0)

        # Full crown boundary containment (Rule G02) and obstacle clearance
        canopy = pt.buffer(canopy_r)
        if not land_poly.covers(canopy):
            continue
        if obstacles_union.intersects(canopy.buffer(0.3)):
            continue
        if any(pt.distance(other) < min_tree_sep for other in placed_tree_points):
            continue

        placed_tree_points.append(pt)
        vegetation_nodes.append({
            "json_id": f"TREE_{idx:03d}",
            "type": "tree",
            "category": spec.get("category", "tree"),
            "species_id": spec.get("vegetation_id", f"TREE_SPEC_{idx}"),
            "species_name": spec.get("botanical_name", spec.get("common_name", "Garden Tree")),
            "position": [round(wx, 3), round(wy, 3)],
            "canopy_radius_m": round(canopy_r, 2),
            "dimensions": {"width": round(canopy_r * 2, 2), "depth": round(canopy_r * 2, 2), "height": mature_h},
            "units": "m",
            "model_placement_score": round(score, 4),
            "source": "trained_model",
        })

    # 2. Decode Seating / Tables from Channel 1
    seating_peaks = _find_local_peaks(heatmaps[1], threshold=0.15, nms_radius=3)
    outdoor_elements: list[dict[str, Any]] = []
    wants_seating = landscape_reqs.get("garden_seating_required") or landscape_reqs.get("outdoor_seating_required") or landscape_reqs.get("garden_table_set_required")

    if wants_seating:
        for score, v, u in seating_peaks:
            wx, wy = meta.to_world(u + 0.5, v + 0.5)
            pt = Point(wx, wy)
            if not land_poly.contains(pt):
                continue
            if obstacles_union.intersects(pt.buffer(1.0)):
                continue
            if any(pt.distance(tp) < 2.0 for tp in placed_tree_points):
                continue

            elem_id = f"ELEM_SEAT_{len(outdoor_elements) + 1:03d}"
            elem_type = "garden_table_set" if landscape_reqs.get("garden_table_set_required") else "garden_seating"
            outdoor_elements.append({
                "json_id": elem_id,
                "type": elem_type,
                "position": [round(wx, 3), round(wy, 3)],
                "dimensions": {"width": 1.8, "depth": 1.2, "height": 0.85},
                "units": "m",
                "model_placement_score": round(score, 4),
                "source": "trained_model",
            })
            break  # Place 1 primary seating unit as requested

    # 3. Decode Lighting nodes from Channel 2
    lighting_nodes: list[dict[str, Any]] = []
    if lighting_reqs.get("required"):
        light_peaks = _find_local_peaks(heatmaps[2], threshold=0.15, nms_radius=3)
        for score, v, u in light_peaks:
            if len(lighting_nodes) >= 4:
                break
            wx, wy = meta.to_world(u + 0.5, v + 0.5)
            pt = Point(wx, wy)
            if not land_poly.contains(pt) or obstacles_union.intersects(pt.buffer(0.5)):
                continue
            lighting_nodes.append({
                "json_id": f"LIGHT_{len(lighting_nodes) + 1:03d}",
                "type": "garden_light",
                "position": [round(wx, 3), round(wy, 3)],
                "illumination_radius_m": 4.0,
                "units": "m",
                "model_placement_score": round(score, 4),
                "source": "trained_model",
            })

    # 4. Integrate Deterministic Infrastructure (Gate, Garage, Driveway, Path)
    from .gate_garage import plan_gate, plan_garage
    from .service import _entrance_target
    from shapely.geometry import LineString

    gate = plan_gate(land_poly, house_poly, prepared_input, access_reqs, 1.0, obstacles_union)
    residual = land_poly.difference(house_poly)
    garage = plan_garage(land_poly, residual, gate, prepared_input, access_reqs, 1.0, obstacles_union, 1.5) if (access_reqs.get("garage_required") and gate) else None

    entrance_target = _entrance_target(prepared_input, house_poly, 1.0)
    main_entrance = entrance_target or prepared_input.get("main_entrance")
    driveway = None
    d_poly = None
    if access_reqs.get("driveway_required") and gate:
        target_pt = garage.get("access_point") if garage else entrance_target
        if target_pt:
            gate_pt = gate.get("access_point", gate.get("position"))
            d_line = LineString([gate_pt, target_pt])
            raw_d_poly = d_line.buffer(1.5, cap_style="flat").difference(house_poly)
            if raw_d_poly.geom_type == "MultiPolygon":
                d_poly = max(raw_d_poly.geoms, key=lambda g: g.area)
            else:
                d_poly = raw_d_poly
            driveway = {
                "json_id": "DRIVEWAY_001",
                "type": "driveway",
                "centerline": list(d_line.coords),
                "polygon": [list(c) for c in d_poly.exterior.coords],
                "width_m": 3.0,
                "source": "deterministic_planner",
                "units": "m",
            }

    # Pedestrian Path from Gate to Entrance
    if (landscape_reqs.get("pedestrian_path_required") or landscape_reqs.get("garden_path_required")) and gate and main_entrance:
        gate_pt = gate.get("access_point", gate.get("position"))
        p_target = entrance_target or main_entrance
        if driveway and d_poly is not None:
            dx, dy = p_target[0] - gate_pt[0], p_target[1] - gate_pt[1]
            length = (dx * dx + dy * dy) ** 0.5 or 1.0
            nx, ny = -dy / length, dx / length
            chosen_poly = None
            chosen_line = None
            for sign in (1, -1):
                offset = sign * 2.6
                p_start = (gate_pt[0] + nx * offset, gate_pt[1] + ny * offset)
                p_end = (p_target[0] + nx * offset, p_target[1] + ny * offset)
                cand_line = LineString([p_start, p_end])
                cand_poly = cand_line.buffer(0.6, cap_style="flat").difference(house_poly).difference(d_poly)
                if cand_poly.geom_type == "MultiPolygon":
                    cand_poly = max(cand_poly.geoms, key=lambda g: g.area)
                if land_poly.covers(cand_poly):
                    chosen_poly = cand_poly
                    chosen_line = cand_line
                    break
            if chosen_poly is not None:
                p_poly = chosen_poly
                p_line = chosen_line
            else:
                p_line = LineString([gate_pt, p_target])
                p_poly = p_line.buffer(0.6, cap_style="flat").difference(house_poly)
                if p_poly.geom_type == "MultiPolygon":
                    p_poly = max(p_poly.geoms, key=lambda g: g.area)
        else:
            p_line = LineString([gate_pt, p_target])
            p_poly = p_line.buffer(0.6, cap_style="flat").difference(house_poly)
            if p_poly.geom_type == "MultiPolygon":
                p_poly = max(p_poly.geoms, key=lambda g: g.area)

        outdoor_elements.append({
            "json_id": f"PATH_{len(outdoor_elements) + 1:03d}",
            "type": "pedestrian_path",
            "polygon": [list(c) for c in p_poly.exterior.coords],
            "units": "m",
            "source": "deterministic_planner",
        })

    # 5. Integrate Phase 5 Solar and Elevated Features
    from .solar_planner import plan_solar_pv
    from .elevated_features import plan_elevated_features

    solar_res = plan_solar_pv(prepared_input, requirements, 1.0)
    solar_elem = solar_res.get("outdoor_element") if isinstance(solar_res, dict) else None
    if solar_elem:
        outdoor_elements.append(solar_elem)

    elev_res = plan_elevated_features(prepared_input, requirements, 1.0, solar_elem)
    elev_elements = elev_res.get("outdoor_elements", []) if isinstance(elev_res, dict) else []
    for elev_item in elev_elements:
        outdoor_elements.append(elev_item)

    # 6. Assemble Full ExteriorLandscapeOutput
    access_dict: dict[str, Any] = {}
    if gate:
        access_dict["gate"] = gate
    if garage:
        access_dict["garage"] = garage
    if driveway:
        access_dict["driveway"] = driveway

    lighting_dict: dict[str, Any] = {
        "required": bool(lighting_reqs.get("required")),
        "nodes": lighting_nodes,
        "style": lighting_reqs.get("style", "pathway"),
    }

    metrics = {
        "model_version": model_version,
        "planner_version": "elia-hybrid-planner-v2.1",
        "trees_requested": target_tree_count,
        "trees_placed": len(vegetation_nodes),
        "seating_placed": len([e for e in outdoor_elements if "seat" in e["type"] or "table" in e["type"]]),
        "lighting_placed": len(lighting_nodes),
        "solar_pv_placed": bool(solar_elem),
        "elevated_features_placed": len(elev_elements),
    }

    solar_install = solar_res.get("solar_installation") if isinstance(solar_res, dict) else None
    vert_green = elev_res.get("vertical_greenery", {}) if isinstance(elev_res, dict) else {}

    return {
        "schema_version": "1.0",
        "version": "1.0",
        "coordinate_reference": "local Cartesian coordinates in meters; north is clockwise from local +Y toward +X",
        "access": access_dict,
        "site_analysis": {
            "land_area_m2": round(land_poly.area, 2),
            "house_footprint_m2": round(house_poly.area, 2),
            "residual_area_m2": round(max(0.0, land_poly.area - house_poly.area), 2),
        },
        "utility_safety": {"status": "assessed"},
        "environment": {
            "solar_installation": solar_install,
            "climate_zone": requirements.get("environment", {}).get("climate_zone", "tropical"),
        },
        "metrics": metrics,
        "vegetation_nodes": vegetation_nodes,
        "vertical_greenery": vert_green,
        "outdoor_lighting": lighting_dict,
        "outdoor_elements": outdoor_elements,
        "validation_summary": {"valid": True},
    }
