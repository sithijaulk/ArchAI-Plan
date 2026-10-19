"""
Measurement Association & Survey Reconstruction Pipeline.
Associates detected line boundaries with OCR observations (distance, bearing),
estimates north orientation & road access edge, and prepares a candidate survey extraction.
Ambiguous measurements are flagged for user verification.
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from ..schemas import (
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    DistanceValue,
    DistanceUnit,
    BearingValue,
    EdgeType,
    SurveySource
)
from ..vector_reconstruction.reconstruct import normalize_bearing_string


def associate_measurements_to_edges(
    lines: List[Dict[str, Any]],
    ocr_annotations: Dict[str, Any]
) -> List[SurveyEdgeInput]:
    """
    Pairs detected line segments with closest distance and bearing text boxes.
    Produces candidate SurveyEdgeInput objects with confidence scores and verification flags.
    """
    distances = ocr_annotations.get("distances", [])
    bearings = ocr_annotations.get("bearings", [])
    edges: List[SurveyEdgeInput] = []

    # If lines or OCR extractions are sparse, provide structured placeholders flagged as ambiguous
    if not lines or len(lines) < 3:
        # Construct fallback candidate list from raw distances/bearings if available
        count = max(3, min(len(distances), len(bearings))) if distances or bearings else 4
        for i in range(count):
            dist_val = 15.0
            dist_conf = None
            if i < len(distances):
                try:
                    num = float(''.join(c for c in distances[i]["raw"] if c.isdigit() or c == '.'))
                    dist_val = num if num > 0 else 15.0
                    dist_conf = distances[i].get("confidence")
                except ValueError:
                    pass

            bearing_val = (i * 90.0) % 360.0
            bearing_raw = f"{int(bearing_val):03d}°00'00\""
            bearing_conf = None
            if i < len(bearings):
                bearing_raw = bearings[i]["raw"]
                bearing_val = normalize_bearing_string(bearing_raw)
                bearing_conf = bearings[i].get("confidence")

            edges.append(
                SurveyEdgeInput(
                    edge_id=f"E{i+1:02d}",
                    distance=DistanceValue(value=dist_val, unit=DistanceUnit.METERS),
                    bearing=BearingValue(raw=bearing_raw, normalized_degrees=bearing_val),
                    edge_type=EdgeType.ROAD_FRONT if i == 0 else (EdgeType.REAR if i == 2 else EdgeType.SIDE),
                    source=SurveySource.EASYOCR,
                    confidence=min(dist_conf or 0.5, bearing_conf or 0.5),
                    distance_origin="ocr" if dist_conf else "user",
                    bearing_origin="ocr" if bearing_conf else "user",
                    verification_status="ambiguous",
                    flags=["needs_user_verification", "sparse_detected_lines"]
                )
            )
        return edges

    # Sort dominant lines by length descending and pick top 4-6 candidate boundaries
    sorted_lines = sorted(lines, key=lambda l: l["length"], reverse=True)[:6]

    for idx, line in enumerate(sorted_lines):
        p1 = line["p1"]
        p2 = line["p2"]
        mid = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2]

        # Find closest distance box
        best_dist = None
        min_d_dist = float('inf')
        for d in distances:
            d_center = d["center"]
            dist_to_line = math.hypot(d_center[0] - mid[0], d_center[1] - mid[1])
            if dist_to_line < min_d_dist:
                min_d_dist = dist_to_line
                best_dist = d

        # Find closest bearing box
        best_bearing = None
        min_b_dist = float('inf')
        for b in bearings:
            b_center = b["center"]
            dist_to_line = math.hypot(b_center[0] - mid[0], b_center[1] - mid[1])
            if dist_to_line < min_b_dist:
                min_b_dist = dist_to_line
                best_bearing = b

        # Parse distance
        dist_val = round(line["length"] * 0.1, 2)  # Initial unscaled image unit
        dist_conf = None
        if best_dist and min_d_dist < 200:  # Within 200px proximity
            try:
                num = float(''.join(c for c in best_dist["raw"] if c.isdigit() or c == '.'))
                if num > 0:
                    dist_val = num
                    dist_conf = best_dist["confidence"]
            except ValueError:
                pass

        # Parse bearing
        bearing_deg = line["angle"]
        bearing_raw = f"{int(bearing_deg):03d}°00'00\""
        bearing_conf = None
        if best_bearing and min_b_dist < 200:
            bearing_raw = best_bearing["raw"]
            bearing_deg = normalize_bearing_string(bearing_raw)
            bearing_conf = best_bearing["confidence"]

        conf = round(((dist_conf or 0.4) + (bearing_conf or 0.4)) / 2, 2)
        flags = []
        if not dist_conf:
            flags.append("inferred_distance")
        if not bearing_conf:
            flags.append("inferred_bearing")

        edges.append(
            SurveyEdgeInput(
                edge_id=f"E{idx+1:02d}",
                distance=DistanceValue(value=dist_val, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw=bearing_raw, normalized_degrees=bearing_deg),
                edge_type=EdgeType.ROAD_FRONT if idx == 0 else (EdgeType.REAR if idx == 2 else EdgeType.SIDE),
                source=SurveySource.EASYOCR,
                confidence=conf,
                distance_origin="ocr" if dist_conf else "image_geometry",
                bearing_origin="ocr" if bearing_conf else "image_geometry",
                verification_status="unverified" if conf >= 0.7 else "ambiguous",
                flags=flags
            )
        )

    return edges


def infer_orientation_and_road(
    ocr_annotations: Dict[str, Any],
    edges: List[SurveyEdgeInput]
) -> Dict[str, Any]:
    """
    Attempts to identify the north indicator and road frontage access edge.
    Returns:
        {
            "north_angle": float,
            "north_confidence": float,
            "road_edge_id": Optional[str],
            "road_confidence": float,
            "warnings": List[str]
        }
    """
    warnings = []
    north_hints = ocr_annotations.get("north_hints", [])
    road_hints = ocr_annotations.get("road_hints", [])

    north_angle = 0.0
    north_conf = 0.0
    if north_hints:
        north_conf = north_hints[0]["confidence"]
    else:
        warnings.append("North direction not explicitly recognized; assumed 0.0° (Up) for verification.")

    road_edge_id = None
    road_conf = 0.0
    if road_hints and edges:
        road_edge_id = edges[0].edge_id
        road_conf = road_hints[0]["confidence"]
        edges[0].edge_type = EdgeType.ROAD_FRONT
    elif edges:
        road_edge_id = edges[0].edge_id
        warnings.append("Road frontage edge inferred from longest boundary; please verify.")

    return {
        "north_angle": north_angle,
        "north_confidence": north_conf,
        "road_edge_id": road_edge_id,
        "road_confidence": road_conf,
        "warnings": warnings
    }
