from __future__ import annotations

import math
from typing import Any, Mapping
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

from .exceptions import ELIAError


def _extract_balconies(master_json: Mapping[str, Any], unit_scale: float = 1.0) -> list[dict[str, Any]]:
    """Extract and validate balcony surfaces from Master JSON."""
    raw_balconies = master_json.get("balconies")
    if raw_balconies is None and isinstance(master_json.get("building_exterior"), Mapping):
        raw_balconies = master_json["building_exterior"].get("balconies")
    if not isinstance(raw_balconies, list):
        return []

    balconies = []
    for i, b in enumerate(raw_balconies):
        if not isinstance(b, Mapping):
            continue
        b_id = str(b.get("json_id") or b.get("id") or f"BALC_{i+1:03d}")
        floor_id = b.get("floor_id") or b.get("floor") or "floor_2"
        elev = b.get("elevation_m", b.get("z_m", b.get("elevation")))
        elevation_m = None
        has_measured_elevation = False
        if elev is not None:
            try:
                val = float(elev)
                if math.isfinite(val) and 0.0 < val <= 150.0:
                    elevation_m = val
                    has_measured_elevation = True
            except (TypeError, ValueError):
                pass
        display_elevation_m = elevation_m if elevation_m is not None else 3.2

        coords = b.get("polygon") or b.get("coordinates")
        if isinstance(coords, Mapping):
            coords = coords.get("coordinates", [])

        exterior_pts = []
        interior_rings = []
        if isinstance(coords, (list, tuple)) and coords:
            if isinstance(coords[0], (list, tuple)) and coords[0] and isinstance(coords[0][0], (list, tuple)):
                # Ring-of-rings: [ exterior_ring, hole_1, ... ]
                ext = coords[0]
                try:
                    if not all(math.isfinite(float(p[0])) and math.isfinite(float(p[1])) for p in ext):
                        continue
                    exterior_pts = [(float(p[0]) * unit_scale, float(p[1]) * unit_scale) for p in ext]
                except (TypeError, ValueError, IndexError):
                    continue
                for h in coords[1:]:
                    if isinstance(h, (list, tuple)) and len(h) >= 3:
                        try:
                            if all(math.isfinite(float(p[0])) and math.isfinite(float(p[1])) for p in h):
                                interior_rings.append([(float(p[0]) * unit_scale, float(p[1]) * unit_scale) for p in h])
                        except (TypeError, ValueError, IndexError):
                            pass
            else:
                try:
                    if not all(math.isfinite(float(p[0])) and math.isfinite(float(p[1])) for p in coords):
                        continue
                    exterior_pts = [(float(p[0]) * unit_scale, float(p[1]) * unit_scale) for p in coords]
                except (TypeError, ValueError, IndexError):
                    continue

        if len(exterior_pts) < 3:
            continue
        
        try:
            poly = Polygon(exterior_pts, interior_rings)
        except (TypeError, ValueError, IndexError):
            continue
        if not poly.is_valid or poly.area <= 0:
            continue

        door = b.get("access_door") or b.get("door_position")
        certified = bool(b.get("structural_certified", False) or b.get("live_load_certified", False))

        balconies.append({
            "json_id": b_id,
            "floor_id": floor_id,
            "elevation_m": elevation_m,
            "polygon": poly,
            "area_m2": poly.area,
            "access_door": door,
            "structural_certified": certified,
        })
    return balconies


def _extract_terraces(master_json: Mapping[str, Any], unit_scale: float = 1.0) -> list[dict[str, Any]]:
    """Extract and validate usable flat terrace surfaces from Master JSON."""
    raw = master_json.get("terraces") or master_json.get("flat_roofs")
    if raw is None and isinstance(master_json.get("building_exterior"), Mapping):
        raw = master_json["building_exterior"].get("terraces") or master_json["building_exterior"].get("flat_roofs")
    if not isinstance(raw, list):
        return []

    terraces = []
    for i, t in enumerate(raw):
        if not isinstance(t, Mapping):
            continue
        r_type = str(t.get("roof_type") or t.get("type") or "terrace").lower()
        if "pitched" in r_type or "gable" in r_type:
            continue # Pitched roofs cannot be used as terraces

        t_id = str(t.get("json_id") or t.get("id") or f"TERR_{i+1:03d}")
        floor_id = t.get("floor_id") or t.get("floor") or "roof"
        elev = t.get("elevation_m", t.get("z_m", t.get("elevation")))
        elevation_m = None
        has_measured_elevation = False
        if elev is not None:
            try:
                val = float(elev)
                if math.isfinite(val) and 0.0 < val <= 150.0:
                    elevation_m = val
                    has_measured_elevation = True
            except (TypeError, ValueError):
                pass
        display_elevation_m = elevation_m if elevation_m is not None else float(master_json.get("house_height_m") or 6.4)

        coords = t.get("polygon") or t.get("coordinates")
        if isinstance(coords, Mapping):
            coords = coords.get("coordinates", [])

        exterior_pts = []
        interior_rings = []
        if isinstance(coords, (list, tuple)) and coords:
            if isinstance(coords[0], (list, tuple)) and coords[0] and isinstance(coords[0][0], (list, tuple)):
                ext = coords[0]
                try:
                    if not all(math.isfinite(float(p[0])) and math.isfinite(float(p[1])) for p in ext):
                        continue
                    exterior_pts = [(float(p[0]) * unit_scale, float(p[1]) * unit_scale) for p in ext]
                except (TypeError, ValueError, IndexError):
                    continue
                for h in coords[1:]:
                    if isinstance(h, (list, tuple)) and len(h) >= 3:
                        try:
                            if all(math.isfinite(float(p[0])) and math.isfinite(float(p[1])) for p in h):
                                interior_rings.append([(float(p[0]) * unit_scale, float(p[1]) * unit_scale) for p in h])
                        except (TypeError, ValueError, IndexError):
                            pass
            else:
                try:
                    if not all(math.isfinite(float(p[0])) and math.isfinite(float(p[1])) for p in coords):
                        continue
                    exterior_pts = [(float(p[0]) * unit_scale, float(p[1]) * unit_scale) for p in coords]
                except (TypeError, ValueError, IndexError):
                    continue

        if len(exterior_pts) < 3:
            continue
        try:
            poly = Polygon(exterior_pts, interior_rings)
        except (TypeError, ValueError, IndexError):
            continue
        if not poly.is_valid or poly.area <= 0:
            continue

        door = t.get("access_door") or t.get("door_position")
        certified = bool(t.get("live_load_certified", False) or t.get("structural_certified", False))

        terraces.append({
            "json_id": t_id,
            "floor_id": floor_id,
            "elevation_m": elevation_m,
            "polygon": poly,
            "area_m2": poly.area,
            "access_door": door,
            "live_load_certified": certified,
        })
    return terraces


def _extract_walls(master_json: Mapping[str, Any], unit_scale: float = 1.0) -> list[dict[str, Any]]:
    """Extract exterior wall surfaces for vertical greenery."""
    raw = master_json.get("walls") or master_json.get("facades")
    if raw is None and isinstance(master_json.get("building_exterior"), Mapping):
        raw = master_json["building_exterior"].get("walls")
    if not isinstance(raw, list):
        return []

    walls = []
    for i, w in enumerate(raw):
        if not isinstance(w, Mapping):
            continue
        w_id = str(w.get("json_id") or w.get("id") or f"WALL_{i+1:03d}")
        orient = str(w.get("orientation") or "south").lower()
        length = float(w.get("length_m") or 6.0) * unit_scale
        height = float(w.get("height_m") or 3.0) * unit_scale
        start_pt = w.get("start_point")
        end_pt = w.get("end_point")
        walls.append({
            "json_id": w_id,
            "orientation": orient,
            "length_m": length,
            "height_m": height,
            "start_point": start_pt,
            "end_point": end_pt,
        })
    return walls


def plan_elevated_features(
    master_json: Mapping[str, Any],
    requirements: Mapping[str, Any],
    unit_scale: float = 1.0,
    solar_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Coordinated planner for balcony features, rooftop terrace features, and wall greenery."""
    balconies_req = requirements.get("balconies") or {}
    terrace_req = requirements.get("terrace") or {}
    vg_req = requirements.get("vertical_greenery") or {}

    structural_evidence = master_json.get("structural_evidence") or {}
    if not isinstance(structural_evidence, Mapping):
        structural_evidence = {}

    balconies = _extract_balconies(master_json, unit_scale)
    terraces = _extract_terraces(master_json, unit_scale)
    walls = _extract_walls(master_json, unit_scale)

    elements: list[dict[str, Any]] = []
    fulfillment_updates: dict[str, dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # 1. BALCONY FEATURES (Planting, Pots, Seating)
    # -------------------------------------------------------------------------
    balc_planting = bool(balconies_req.get("planting_required", False) or balconies_req.get("potted_plants", False) or balconies_req.get("hanging_plants", False))
    balc_seating = bool(balconies_req.get("seating_required", False))

    if balc_planting or balc_seating:
        if not balconies:
            if balc_planting:
                fulfillment_updates["balcony_planting"] = {
                    "status": "infeasible",
                    "original_request": True,
                    "actual_quantity": 0,
                    "reason_codes": ["NO_BALCONY_SURFACE"],
                    "supported_alternatives": ["Ground container planting or vertical wall greenery."],
                }
            if balc_seating:
                fulfillment_updates["balcony_seating"] = {
                    "status": "infeasible",
                    "original_request": True,
                    "actual_quantity": 0,
                    "reason_codes": ["NO_BALCONY_SURFACE"],
                    "supported_alternatives": ["Ground garden seating or patio furniture."],
                }
        else:
            # Check structural allowance for balconies
            balc_allowance = structural_evidence.get("balcony_allowance_kg_m2")
            has_balc_load_cert = balc_allowance is not None and any(b["structural_certified"] for b in balconies)

            balc_pots_placed = 0
            balc_seats_placed = 0

            for b in balconies:
                poly = b["polygon"]
                # 0.15m perimeter clearance interior to railing
                usable = poly.buffer(-0.15)
                
                # Door clearance: 0.6m clear corridor from access door
                door = b.get("access_door")
                if door and isinstance(door, (list, tuple)) and len(door) >= 2:
                    usable = usable.difference(Point(door[0], door[1]).buffer(0.6))

                if usable.is_empty or usable.area < 0.3:
                    continue

                min_x, min_y, max_x, max_y = usable.bounds
                center = usable.representative_point()

                # Place Seating if requested
                if balc_seating and usable.area >= 1.0:
                    seat_w, seat_d = 0.8, 0.6
                    seat_box = box(center.x - seat_w / 2, center.y - seat_d / 2, center.x + seat_w / 2, center.y + seat_d / 2)
                    if usable.covers(seat_box):
                        balc_seats_placed += 1
                        usable = usable.difference(seat_box.buffer(0.15)) # 0.15m clearance
                        elements.append({
                            "json_id": f"BALC_SEAT_{balc_seats_placed:03d}",
                            "type": "balcony_seating",
                            "supporting_surface_id": b["json_id"],
                            "floor_id": b["floor_id"],
                            "elevation_m": round(b["elevation_m"] + 0.4, 2),
                            "position": [round(center.x, 3), round(center.y, 3)],
                            "dimensions": {"width_m": seat_w, "depth_m": seat_d, "height_m": 0.8},
                            "polygon": list(seat_box.exterior.coords),
                            "validation": {
                                "valid": True,
                                "supporting_surface": b["json_id"],
                                "structural_load_verified": has_balc_load_cert,
                                "circulation_clearance_m": 0.15,
                            },
                            "render": {"asset_id": "balcony_bistro_set", "visible": True},
                        })

                # Place Pots if planting is requested
                if balc_planting and not usable.is_empty:
                    pot_size = 0.35
                    # Try corners
                    for corner_x, corner_y in [(min_x + 0.2, min_y + 0.2), (max_x - 0.2, min_y + 0.2), (min_x + 0.2, max_y - 0.2)]:
                        pot_box = box(corner_x - pot_size / 2, corner_y - pot_size / 2, corner_x + pot_size / 2, corner_y + pot_size / 2)
                        if usable.covers(pot_box):
                            balc_pots_placed += 1
                            usable = usable.difference(pot_box.buffer(0.1))
                            elements.append({
                                "json_id": f"BALC_POT_{balc_pots_placed:03d}",
                                "type": "balcony_pot",
                                "supporting_surface_id": b["json_id"],
                                "floor_id": b["floor_id"],
                                "elevation_m": round(b["elevation_m"] + 0.1, 2),
                                "position": [round(corner_x, 3), round(corner_y, 3)],
                                "dimensions": {"width_m": pot_size, "depth_m": pot_size, "height_m": 0.45},
                                "polygon": list(pot_box.exterior.coords),
                                "validation": {
                                    "valid": True,
                                    "supporting_surface": b["json_id"],
                                    "structural_load_verified": has_balc_load_cert,
                                },
                                "render": {"asset_id": "terracotta_pot_generic", "visible": True},
                            })
                            if balc_pots_placed >= 2:
                                break

            # Update fulfillment status
            if balc_planting:
                if not has_balc_load_cert:
                    fulfillment_updates["balcony_planting"] = {
                        "status": "review_required",
                        "original_request": True,
                        "actual_quantity": balc_pots_placed,
                        "reason_codes": ["MISSING_STRUCTURAL_ALLOWANCE"],
                        "missing_evidence": ["structural_evidence.balcony_allowance_kg_m2"],
                    }
                elif balc_pots_placed > 0:
                    fulfillment_updates["balcony_planting"] = {
                        "status": "fulfilled",
                        "original_request": True,
                        "actual_quantity": balc_pots_placed,
                        "reason_codes": [],
                    }
                else:
                    fulfillment_updates["balcony_planting"] = {
                        "status": "infeasible",
                        "original_request": True,
                        "actual_quantity": 0,
                        "reason_codes": ["INSUFFICIENT_BALCONY_CLEARANCE"],
                    }

            if balc_seating:
                if not has_balc_load_cert:
                    fulfillment_updates["balcony_seating"] = {
                        "status": "review_required",
                        "original_request": True,
                        "actual_quantity": balc_seats_placed,
                        "reason_codes": ["MISSING_STRUCTURAL_ALLOWANCE"],
                        "missing_evidence": ["structural_evidence.balcony_allowance_kg_m2"],
                    }
                elif balc_seats_placed > 0:
                    fulfillment_updates["balcony_seating"] = {
                        "status": "fulfilled",
                        "original_request": True,
                        "actual_quantity": balc_seats_placed,
                        "reason_codes": [],
                    }
                else:
                    fulfillment_updates["balcony_seating"] = {
                        "status": "infeasible",
                        "original_request": True,
                        "actual_quantity": 0,
                        "reason_codes": ["INSUFFICIENT_BALCONY_DIMENSIONS"],
                        "supported_alternatives": ["Ground garden seating."],
                    }

    # -------------------------------------------------------------------------
    # 2. ROOFTOP TERRACE FEATURES (Planters, Tables, Seating)
    # -------------------------------------------------------------------------
    roof_planting = bool(terrace_req.get("planting_required", False) or terrace_req.get("planters_required", False))
    roof_seating = bool(terrace_req.get("seating_required", False) or terrace_req.get("tables_required", False))

    if roof_planting or roof_seating:
        if not terraces:
            if roof_planting:
                fulfillment_updates["rooftop_planting"] = {
                    "status": "infeasible",
                    "original_request": True,
                    "actual_quantity": 0,
                    "reason_codes": ["NO_ROOFTOP_SURFACE"],
                    "supported_alternatives": ["Ground garden planting."],
                }
            if roof_seating:
                fulfillment_updates["rooftop_seating"] = {
                    "status": "infeasible",
                    "original_request": True,
                    "actual_quantity": 0,
                    "reason_codes": ["NO_ROOFTOP_SURFACE"],
                    "supported_alternatives": ["Ground patio seating."],
                }
        else:
            roof_allowance = structural_evidence.get("roof_allowance_kg_m2") or structural_evidence.get("terrace_allowance_kg_m2")
            has_roof_cert = roof_allowance is not None and any(t["live_load_certified"] for t in terraces)

            roof_planters_placed = 0
            roof_furniture_placed = 0

            for t in terraces:
                poly = t["polygon"]
                # 0.4m guardrail & safety setback
                usable = poly.buffer(-0.4)

                # Door / roof hatch clearance: 1.0m
                door = t.get("access_door")
                if door and isinstance(door, (list, tuple)) and len(door) >= 2:
                    usable = usable.difference(Point(door[0], door[1]).buffer(1.0))

                # If solar panels are placed on this surface, subtract solar area
                if solar_plan and solar_plan.get("status") == "fulfilled" and solar_plan.get("surface_id") == t["json_id"]:
                    solar_poly = solar_plan.get("outdoor_element", {}).get("polygon")
                    if solar_poly:
                        usable = usable.difference(Polygon(solar_poly).buffer(0.3))

                if usable.is_empty or usable.area < 2.0:
                    continue

                center = usable.representative_point()

                # Place Table Set and Seating in open area
                if roof_seating and usable.area >= 3.5:
                    tbl_w, tbl_d = 1.4, 0.9
                    tbl_box = box(center.x - tbl_w / 2, center.y - tbl_d / 2, center.x + tbl_w / 2, center.y + tbl_d / 2)
                    if usable.covers(tbl_box):
                        roof_furniture_placed += 1
                        usable = usable.difference(tbl_box.buffer(0.4))
                        elements.append({
                            "json_id": f"ROOF_TABLE_{roof_furniture_placed:03d}",
                            "type": "rooftop_table_set",
                            "supporting_surface_id": t["json_id"],
                            "floor_id": t["floor_id"],
                            "elevation_m": round(t["elevation_m"] + 0.05, 2),
                            "position": [round(center.x, 3), round(center.y, 3)],
                            "dimensions": {"width_m": tbl_w, "depth_m": tbl_d, "height_m": 0.75},
                            "polygon": list(tbl_box.exterior.coords),
                            "validation": {
                                "valid": True,
                                "supporting_surface": t["json_id"],
                                "live_load_certified": has_roof_cert,
                                "usable_clearance_m": 0.4,
                            },
                            "render": {"asset_id": "rooftop_dining_set", "visible": True},
                        })

                # Place Planters along perimeter
                if roof_planting and not usable.is_empty:
                    p_w, p_d = 1.2, 0.5
                    # Search around perimeter bounds of remaining usable space
                    u_min_x, u_min_y, u_max_x, u_max_y = usable.bounds
                    for cx, cy in [(u_min_x + p_w / 2 + 0.1, u_max_y - p_d / 2 - 0.1),
                                   (u_max_x - p_w / 2 - 0.1, u_max_y - p_d / 2 - 0.1),
                                   (u_min_x + p_w / 2 + 0.1, u_min_y + p_d / 2 + 0.1)]:
                        cand_box = box(cx - p_w / 2, cy - p_d / 2, cx + p_w / 2, cy + p_d / 2)
                        if usable.covers(cand_box):
                            roof_planters_placed += 1
                            usable = usable.difference(cand_box.buffer(0.2))
                            elements.append({
                                "json_id": f"ROOF_PLANTER_{roof_planters_placed:03d}",
                                "type": "rooftop_planter",
                                "supporting_surface_id": t["json_id"],
                                "floor_id": t["floor_id"],
                                "elevation_m": round(t["elevation_m"] + 0.05, 2),
                                "position": [round(cand_box.centroid.x, 3), round(cand_box.centroid.y, 3)],
                                "dimensions": {"width_m": p_w, "depth_m": p_d, "height_m": 0.6},
                                "polygon": list(cand_box.exterior.coords),
                                "validation": {
                                    "valid": True,
                                    "supporting_surface": t["json_id"],
                                    "live_load_certified": has_roof_cert,
                                },
                                "render": {"asset_id": "raised_bed_rooftop", "visible": True},
                            })
                            if roof_planters_placed >= 2:
                                break

            if roof_planting:
                if not has_roof_cert:
                    fulfillment_updates["rooftop_planting"] = {
                        "status": "review_required",
                        "original_request": True,
                        "actual_quantity": roof_planters_placed,
                        "reason_codes": ["MISSING_ROOF_STRUCTURAL_ALLOWANCE"],
                        "missing_evidence": ["structural_evidence.roof_allowance_kg_m2"],
                    }
                elif roof_planters_placed > 0:
                    fulfillment_updates["rooftop_planting"] = {
                        "status": "fulfilled",
                        "original_request": True,
                        "actual_quantity": roof_planters_placed,
                        "reason_codes": [],
                    }
                else:
                    fulfillment_updates["rooftop_planting"] = {
                        "status": "infeasible",
                        "original_request": True,
                        "actual_quantity": 0,
                        "reason_codes": ["INSUFFICIENT_TERRACE_SPACE"],
                    }

            if roof_seating:
                if not has_roof_cert:
                    fulfillment_updates["rooftop_seating"] = {
                        "status": "review_required",
                        "original_request": True,
                        "actual_quantity": roof_furniture_placed,
                        "reason_codes": ["MISSING_ROOF_STRUCTURAL_ALLOWANCE"],
                        "missing_evidence": ["structural_evidence.roof_allowance_kg_m2"],
                    }
                elif roof_furniture_placed > 0:
                    fulfillment_updates["rooftop_seating"] = {
                        "status": "fulfilled",
                        "original_request": True,
                        "actual_quantity": roof_furniture_placed,
                        "reason_codes": [],
                    }
                else:
                    fulfillment_updates["rooftop_seating"] = {
                        "status": "infeasible",
                        "original_request": True,
                        "actual_quantity": 0,
                        "reason_codes": ["INSUFFICIENT_TERRACE_SPACE"],
                    }

    # -------------------------------------------------------------------------
    # 3. WALL GREENERY & CLIMBERS
    # -------------------------------------------------------------------------
    vg_mode = str(vg_req.get("mode") or "automatic").lower()
    if vg_mode in {"preferred", "automatic"} and walls:
        for w_idx, w in enumerate(walls[:2]): # Support primary walls
            trellis_id = f"WALL_TRELLIS_{w_idx+1:03d}"
            elements.append({
                "json_id": trellis_id,
                "type": "wall_trellis",
                "supporting_surface_id": w["json_id"],
                "orientation": w["orientation"],
                "elevation_m": round(w["height_m"] / 2, 2),
                "dimensions": {"width_m": min(3.0, w["length_m"]), "height_m": min(2.5, w["height_m"]), "depth_m": 0.1},
                "validation": {
                    "valid": True,
                    "supporting_surface": w["json_id"],
                    "orientation": w["orientation"],
                },
                "render": {"asset_id": "wall_trellis_greenery", "visible": True},
            })

    return {
        "elements": elements,
        "fulfillment_updates": fulfillment_updates,
    }
