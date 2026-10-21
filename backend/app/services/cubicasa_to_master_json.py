"""
CubiCasa Segmentation to Master JSON Converter.

Translates CubiCasa5K SegmentationResult (polygons in pixels, detected icons)
into the standardized ArchAI Master JSON format (in feet, orthogonally rectified,
tagged room types, doors, windows, and bounding boxes).
"""

import math
import uuid
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.affinity import scale, translate

from ..ml.cubicasa.postprocessor import SegmentationResult

# Mapping from CubiCasa class names to ArchAI Master JSON room types and display labels
ROOM_CLASS_TO_TYPE: Dict[str, Tuple[str, str]] = {
    "Living Room": ("living", "LIVING ROOM"),
    "Kitchen": ("kitchen", "KITCHEN"),
    "Bedroom": ("bedroom", "BEDROOM"),
    "Bath": ("toilet", "BATHROOM"),
    "Hallway": ("hallway", "HALLWAY"),
    "Storage": ("store_room", "STORE ROOM"),
    "Garage": ("garage", "GARAGE"),
    "Undefined": ("room", "ROOM"),
}

# Classes to ignore during room extraction
IGNORED_ROOM_CLASSES = {"Background", "Outdoor", "Wall", "Railing"}


def snap_polygon_to_orthogonal(poly: Polygon, angle_threshold_deg: float = 15.0) -> Polygon:
    """
    Snaps nearly horizontal or vertical polygon edges to exact right angles (orthogonal grid).
    This ensures architectural plans render cleanly with crisp CAD-style walls.
    """
    coords = list(poly.exterior.coords)
    if len(coords) < 4:
        return poly

    # Remove duplicate closing point for processing
    pts = [[float(p[0]), float(p[1])] for p in coords[:-1]]
    n = len(pts)

    snapped_pts = []
    for i in range(n):
        curr_p = pts[i]
        next_p = pts[(i + 1) % n]
        dx = next_p[0] - curr_p[0]
        dy = next_p[1] - curr_p[1]
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            snapped_pts.append(curr_p)
            continue

        angle_deg = math.degrees(math.atan2(abs(dy), abs(dx)))
        # Near horizontal: angle close to 0 or 180
        if angle_deg <= angle_threshold_deg:
            next_p[1] = curr_p[1]
        # Near vertical: angle close to 90
        elif abs(angle_deg - 90.0) <= angle_threshold_deg:
            next_p[0] = curr_p[0]

        snapped_pts.append(curr_p)

    snapped_pts.append(snapped_pts[0])
    try:
        new_poly = Polygon(snapped_pts)
        if new_poly.is_valid and not new_poly.is_empty and new_poly.area > 0:
            return new_poly
    except Exception:
        pass
    return poly


def format_dimension_text(width_ft: float, height_ft: float) -> str:
    """Formats width and height into standard architectural feet-and-inches dimension text."""
    w_ft = int(width_ft)
    w_in = int(round((width_ft - w_ft) * 12))
    if w_in == 12:
        w_ft += 1
        w_in = 0

    h_ft = int(height_ft)
    h_in = int(round((height_ft - h_ft) * 12))
    if h_in == 12:
        h_ft += 1
        h_in = 0

    return f"{w_ft}'{w_in}\" \u00d7 {h_ft}'{h_in}\""


def convert_cubicasa_to_master_json(
    result: SegmentationResult,
    image_width_px: int,
    image_height_px: int,
    target_width_ft: Optional[float] = None,
    project_id: str = "project-segmented",
    project_name: str = "AI Segmented Floor Plan",
    orientation: str = "North",
) -> Dict[str, Any]:
    """
    Transforms CubiCasa5K inference results into an ArchAI Master JSON specification.
    """
    # 1. Determine scaling factor from pixels to feet
    # Default to 42.0 ft width if not specified
    overall_width_ft = float(target_width_ft) if target_width_ft and target_width_ft > 0 else 42.0
    scale_factor = overall_width_ft / float(max(image_width_px, 1))

    # Calculate overall height in feet
    overall_height_ft = round(image_height_px * scale_factor, 1)
    overall_width_ft = round(overall_width_ft, 1)

    # 2. Extract and process room polygons
    rooms_output: List[Dict[str, Any]] = []
    type_counts: Dict[str, int] = {}
    total_room_confidence: float = 0.0
    processed_room_count: int = 0

    # Sort room classes consistently
    for room_class, polygons in result.room_polygons.items():
        if room_class in IGNORED_ROOM_CLASSES:
            continue

        raw_type, base_name = ROOM_CLASS_TO_TYPE.get(room_class, ("room", "ROOM"))

        for poly in polygons:
            if poly.is_empty or not poly.is_valid or poly.area < 200:
                continue

            # Simplify and snap polygon to orthogonal grid
            simplified = poly.simplify(2.0, preserve_topology=True)
            if not isinstance(simplified, Polygon):
                continue
            snapped = snap_polygon_to_orthogonal(simplified)

            # Convert coordinates from pixels to feet (round to 1 decimal place)
            # In image coordinates (0,0) is top-left, matching the 2D CAD viewer canvas
            raw_coords = list(snapped.exterior.coords)[:-1]
            scaled_coords = [
                [round(x * scale_factor, 1), round(y * scale_factor, 1)]
                for x, y in raw_coords
            ]

            if len(scaled_coords) < 3:
                continue

            # Bounding box dimensions
            xs = [p[0] for p in scaled_coords]
            ys = [p[1] for p in scaled_coords]
            rw = round(max(xs) - min(xs), 1)
            rh = round(max(ys) - min(ys), 1)
            if rw < 1.0 or rh < 1.0:
                continue

            # Calculate average room confidence from confidence map if available
            room_conf = 0.85
            if hasattr(result, "room_confidence") and result.room_confidence is not None:
                min_px_x = max(0, int(min(xs) / scale_factor))
                max_px_x = min(image_width_px, int(max(xs) / scale_factor))
                min_px_y = max(0, int(min(ys) / scale_factor))
                max_px_y = min(image_height_px, int(max(ys) / scale_factor))
                if max_px_x > min_px_x and max_px_y > min_px_y:
                    sub_conf = result.room_confidence[min_px_y:max_px_y, min_px_x:max_px_x]
                    if sub_conf.size > 0:
                        room_conf = float(np.mean(sub_conf))

            total_room_confidence += room_conf
            processed_room_count += 1

            type_counts[raw_type] = type_counts.get(raw_type, 0) + 1
            idx = type_counts[raw_type]
            room_id = f"room-{raw_type}-{idx}"
            display_name = f"{base_name} {idx}" if idx > 1 or raw_type in ("bedroom", "toilet") else base_name

            rooms_output.append({
                "id": room_id,
                "name": display_name,
                "type": raw_type,
                "dimensionText": format_dimension_text(rw, rh),
                "polygon": scaled_coords,
                "confidence": round(room_conf, 2),
                "is_detected": True,
            })

    # Sort rooms logically (e.g. Living Room first, then Bed, Kitchen, Bath)
    order_map = {"living": 0, "kitchen": 1, "bedroom": 2, "master_bedroom": 2, "toilet": 3, "hallway": 4}
    rooms_output.sort(key=lambda r: order_map.get(r["type"], 99))

    # Mark first bedroom as master_bedroom if present
    bedrooms = [r for r in rooms_output if r["type"] == "bedroom"]
    if len(bedrooms) >= 2:
        bedrooms[0]["type"] = "master_bedroom"
        bedrooms[0]["name"] = "MASTER BEDROOM"

    # 3. Extract Doors and Windows from icon detections
    doors_output: List[Dict[str, Any]] = []
    windows_output: List[Dict[str, Any]] = []

    door_count = 0
    window_count = 0

    for icon_class, cy, cx, area in result.icon_detections:
        scaled_x = round(cx * scale_factor, 1)
        scaled_y = round(cy * scale_factor, 1)

        if icon_class == "Door":
            door_count += 1
            doors_output.append({
                "id": f"door-{door_count}",
                "name": f"DOOR {door_count}",
                "type": "single_swing",
                "center": [scaled_x, scaled_y],
                "position": [scaled_x, scaled_y],
                "width": 3.0,
                "confidence": 0.88,
            })
        elif icon_class == "Window":
            window_count += 1
            windows_output.append({
                "id": f"window-{window_count}",
                "name": f"WINDOW {window_count}",
                "center": [scaled_x, scaled_y],
                "position": [scaled_x, scaled_y],
                "width": 4.0,
                "confidence": 0.88,
            })

    # Mark the door nearest to the boundary as candidate main entrance
    if doors_output:
        def dist_to_boundary(d: Dict[str, Any]) -> float:
            x, y = d["center"]
            return min(x, abs(overall_width_ft - x), y, abs(overall_height_ft - y))

        doors_output.sort(key=dist_to_boundary)
        doors_output[0]["is_main_entrance"] = True
        doors_output[0]["name"] = "MAIN ENTRANCE"

    avg_confidence = round(total_room_confidence / max(processed_room_count, 1), 2) if processed_room_count else 0.85

    # 4. Synthesize outer boundary and buildable footprint
    boundary_points = [
        [0.0, 0.0],
        [overall_width_ft, 0.0],
        [overall_width_ft, overall_height_ft],
        [0.0, overall_height_ft],
    ]
    footprint_margin = 2.0
    footprint_polygon = [
        [footprint_margin, footprint_margin],
        [max(overall_width_ft - footprint_margin, footprint_margin + 1), footprint_margin],
        [max(overall_width_ft - footprint_margin, footprint_margin + 1), max(overall_height_ft - footprint_margin, footprint_margin + 1)],
        [footprint_margin, max(overall_height_ft - footprint_margin, footprint_margin + 1)],
    ]

    master_json: Dict[str, Any] = {
        "project_id": project_id,
        "project_name": project_name,
        "schema_version": "1.0",
        "units": "ft",
        "land_info": {
            "boundary_points": boundary_points,
            "area_sqft": round(overall_width_ft * overall_height_ft, 1),
            "orientation": orientation,
            "road_facing": orientation,
        },
        "buildable_footprint": {
            "polygon": footprint_polygon,
        },
        "floor_plan": {
            "dimensions": {
                "width": overall_width_ft,
                "height": overall_height_ft,
            },
            "rooms": rooms_output,
            "doors": doors_output,
            "windows": windows_output,
            "structural_elements": [],
        },
        "structural_rectification": {},
        "interior_layout": {},
        "exterior_landscape": {},
        "processing": {
            "gab_gen": {"status": "completed"},
            "vsai_rectifier": {"status": "pending"},
            "esai_engine": {"status": "pending"},
            "elia_engine": {"status": "pending"},
        },
        "segmentation_meta": {
            "source": "CubiCasa5K",
            "rooms_detected": len(rooms_output),
            "doors_detected": len(doors_output),
            "windows_detected": len(windows_output),
            "average_confidence": avg_confidence,
            "original_image_size": [image_width_px, image_height_px],
            "scale_factor_ft_per_px": scale_factor,
        },
    }

    return master_json
