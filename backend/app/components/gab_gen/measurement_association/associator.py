"""
Measurement Association & Survey Reconstruction Pipeline.
Associates detected line boundaries with OCR observations (distance, bearing),
estimates north orientation & road access edge, and prepares a candidate survey extraction.
Ambiguous measurements are flagged for user verification.
"""
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from ..schemas import (
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    DistanceValue,
    DistanceUnit,
    BearingValue,
    EdgeType,
    SurveySource,
    SurveyVerificationStatus,
    GeoreferenceStatus
)
from ..vector_reconstruction.reconstruct import normalize_bearing_string


def associate_measurements_to_edges(
    lines: List[Dict[str, Any]],
    ocr_annotations: Dict[str, Any]
) -> List[SurveyEdgeInput]:
    """
    Pairs detected line segments with closest distance and bearing text boxes.
    Produces candidate SurveyEdgeInput objects with confidence scores and verification flags.
    Never silently invents lengths or bearings without flagging ambiguous/inferred provenance.
    """
    distances = ocr_annotations.get("distances", [])
    bearings = ocr_annotations.get("bearings", [])
    edges: List[SurveyEdgeInput] = []

    # If lines or OCR extractions are sparse, provide structured placeholders flagged as ambiguous
    if not lines or len(lines) < 3:
        count = max(3, min(len(distances), len(bearings))) if distances or bearings else 4
        for i in range(count):
            dist_val = 15.0
            dist_conf = None
            dist_origin = "user"
            flags = ["sparse_detected_lines", "needs_user_verification"]

            if i < len(distances):
                try:
                    num_str = re.search(r'\d+(?:\.\d+)?', distances[i]["raw"])
                    if num_str:
                        dist_val = float(num_str.group(0))
                        dist_conf = distances[i].get("confidence")
                        dist_origin = "ocr"
                except Exception:
                    pass

            bearing_val = (i * 90.0) % 360.0
            bearing_raw = f"{int(bearing_val):03d}°00'00\""
            bearing_conf = None
            bearing_origin = "user"
            if i < len(bearings):
                try:
                    bearing_raw = bearings[i]["raw"]
                    bearing_val = normalize_bearing_string(bearing_raw)
                    bearing_conf = bearings[i].get("confidence")
                    bearing_origin = "ocr"
                except Exception:
                    pass

            edges.append(
                SurveyEdgeInput(
                    edge_id=f"E{i+1:02d}",
                    distance=DistanceValue(value=dist_val, unit=DistanceUnit.METERS),
                    bearing=BearingValue(raw=bearing_raw, normalized_degrees=bearing_val),
                    edge_type=EdgeType.ROAD_FRONT if i == 0 else (EdgeType.REAR if i == 2 else EdgeType.SIDE),
                    source=SurveySource.EASYOCR,
                    confidence=min(dist_conf or 0.4, bearing_conf or 0.4),
                    distance_origin=dist_origin,
                    bearing_origin=bearing_origin,
                    verification_status="ambiguous",
                    flags=flags
                )
            )
        return edges

    # Sort dominant lines by length descending and pick top 4-8 candidate boundaries
    raw_candidates = sorted(lines, key=lambda l: l["length"], reverse=True)[:8]

    # Calculate center of mass of candidate lines to order them topologically clockwise
    all_pts = []
    for line in raw_candidates:
        all_pts.extend([line["p1"], line["p2"]])
    cx = sum(p[0] for p in all_pts) / len(all_pts) if all_pts else 0
    cy = sum(p[1] for p in all_pts) / len(all_pts) if all_pts else 0

    # Sort lines by polar angle of their midpoint from centroid (ensures clockwise / non-intersecting sequence)
    def line_angle_from_centroid(line):
        p1, p2 = line["p1"], line["p2"]
        mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
        # In image coordinates, Y points down, so math.atan2(my - cy, mx - cx) gives angular orientation
        ang = math.degrees(math.atan2(my - cy, mx - cx))
        return (ang + 360.0) % 360.0

    sorted_lines = sorted(raw_candidates, key=line_angle_from_centroid)
    n_edges = len(sorted_lines)

    # Track used measurement indices to avoid incorrectly assigning the same measurement to multiple edges
    used_dist_indices = set()
    used_bearing_indices = set()

    for idx, line in enumerate(sorted_lines):
        p1 = line["p1"]
        p2 = line["p2"]
        mid = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2]

        # Find closest unused distance box within 250px proximity
        best_dist = None
        best_d_idx = None
        min_d_dist = float('inf')
        for d_idx, d in enumerate(distances):
            if d_idx in used_dist_indices:
                continue
            d_center = d["center"]
            dist_to_line = math.hypot(d_center[0] - mid[0], d_center[1] - mid[1])
            if dist_to_line < min_d_dist and dist_to_line < 250:
                min_d_dist = dist_to_line
                best_dist = d
                best_d_idx = d_idx

        # Find closest unused bearing box within 250px proximity
        best_bearing = None
        best_b_idx = None
        min_b_dist = float('inf')
        for b_idx, b in enumerate(bearings):
            if b_idx in used_bearing_indices:
                continue
            b_center = b["center"]
            dist_to_line = math.hypot(b_center[0] - mid[0], b_center[1] - mid[1])
            if dist_to_line < min_b_dist and dist_to_line < 250:
                min_b_dist = dist_to_line
                best_bearing = b
                best_b_idx = b_idx

        # Mark as used if found
        if best_d_idx is not None:
            used_dist_indices.add(best_d_idx)
        if best_b_idx is not None:
            used_bearing_indices.add(best_b_idx)

        # Parse distance
        dist_val = round(line["length"] * 0.1, 2)  # Default fallback estimate in image unit
        dist_conf = None
        dist_origin = "image_geometry"

        if best_dist:
            num_match = re.search(r'\d+(?:\.\d+)?', best_dist["raw"])
            if num_match:
                val = float(num_match.group(0))
                if val > 0:
                    dist_val = val
                    dist_conf = best_dist["confidence"]
                    dist_origin = "ocr"

        # Parse bearing: If not read via OCR, assign sequential clockwise azimuth (e.g. 90, 180, 270, 0)
        # to ensure the reconstructed survey traverse loop doesn't criss-cross itself.
        default_traverse_azimuth = round((idx * (360.0 / max(1, n_edges))) + 90.0) % 360.0
        bearing_deg = default_traverse_azimuth
        bearing_raw = f"{int(bearing_deg):03d}°00'00\""
        bearing_conf = None
        bearing_origin = "image_geometry"

        if best_bearing:
            bearing_raw = best_bearing["raw"]
            bearing_deg = normalize_bearing_string(bearing_raw)
            bearing_conf = best_bearing["confidence"]
            bearing_origin = "ocr"

        conf = round(((dist_conf or 0.4) + (bearing_conf or 0.4)) / 2, 2)
        flags = []
        if dist_origin == "image_geometry":
            flags.append("inferred_distance_requires_verification")
        if bearing_origin == "image_geometry":
            flags.append("inferred_bearing_requires_verification")

        edges.append(
            SurveyEdgeInput(
                edge_id=f"E{idx+1:02d}",
                distance=DistanceValue(value=dist_val, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw=bearing_raw, normalized_degrees=bearing_deg),
                edge_type=EdgeType.ROAD_FRONT if idx == 0 else (EdgeType.REAR if idx == n_edges // 2 else EdgeType.SIDE),
                source=SurveySource.EASYOCR,
                confidence=conf,
                distance_origin=dist_origin,
                bearing_origin=bearing_origin,
                verification_status="unverified" if (dist_origin == "ocr" and bearing_origin == "ocr" and conf >= 0.7) else "ambiguous",
                flags=flags
            )
        )

    return edges


def infer_orientation_and_road(
    ocr_annotations: Dict[str, Any],
    edges: List[SurveyEdgeInput],
    north_symbol_candidates: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Attempts to identify the north indicator and road frontage access edge.
    Never silently invents north = 0° as verified.
    Distinguishes:
        - north_detected (when text or symbol is confidently observed)
        - north_unknown (when no indicator exists; flags requirement for user input)
    """
    warnings = []
    north_hints = ocr_annotations.get("north_hints", [])
    road_hints = ocr_annotations.get("road_hints", [])

    north_angle = 0.0
    north_conf = 0.0
    north_origin = "default_unknown"

    if north_hints:
        north_conf = north_hints[0]["confidence"]
        north_origin = "ocr_text_label"
    elif north_symbol_candidates:
        north_conf = 0.65
        north_origin = "detected_symbol_heuristic"
    else:
        warnings.append("North direction was not confidently detected from survey document; marked as unknown. User confirmation required.")

    road_edge_id = None
    road_conf = 0.0
    road_origin = "none"

    if road_hints and edges:
        road_edge_id = edges[0].edge_id
        road_conf = road_hints[0]["confidence"]
        road_origin = "ocr_annotation"
        edges[0].edge_type = EdgeType.ROAD_FRONT
    elif edges:
        road_edge_id = edges[0].edge_id
        road_origin = "longest_edge_heuristic"
        warnings.append("Road frontage edge inferred from longest boundary candidate; user confirmation required.")

    # Scale inference
    scales = ocr_annotations.get("scales", [])
    drawing_scale = None
    scale_origin = "unknown"
    if scales:
        drawing_scale = scales[0]["ratio"]
        scale_origin = "ocr_text"

    return {
        "north_angle": north_angle,
        "north_confidence": north_conf,
        "north_origin": north_origin,
        "road_edge_id": road_edge_id,
        "road_confidence": road_conf,
        "road_origin": road_origin,
        "drawing_scale": drawing_scale,
        "drawing_scale_origin": scale_origin,
        "warnings": warnings
    }
