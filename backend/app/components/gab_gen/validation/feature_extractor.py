"""
Numerical Feature Extractor and Layout Quality Metrics.
Extracts deterministic, finite, explainable spatial features from a candidate floor plan.
Designed for both heuristic ranking (Phase 5) and future XGBoost inference without model training.
Feature schema version: 1.0.0
"""
import math
from typing import Any, Dict, List, Optional
from shapely.geometry import Polygon

from ..schemas import (
    FloorPlanDefinition,
    ClientRequirementsInput,
    NumericalFeatureVector,
    PreferenceEvaluationResult,
    PreferenceEvaluationStatus,
    AdjacencyRelationshipType,
)


def extract_candidate_features(
    floors: List[FloorPlanDefinition],
    requirements: ClientRequirementsInput,
    footprint_poly: Polygon,
    preference_evaluations: List[PreferenceEvaluationResult]
) -> NumericalFeatureVector:
    """
    Computes normalized, deterministic numerical features for a generated candidate.
    All outputs are finite floats (never NaN or Infinity).
    """
    footprint_area = round(float(footprint_poly.area), 2) if footprint_poly and not footprint_poly.is_empty else 0.0

    all_rooms = [rm for fl in floors for rm in fl.rooms]
    habitable_rooms = [rm for rm in all_rooms if not rm.is_structural_stair]
    stair_rooms = [rm for rm in all_rooms if rm.is_structural_stair]

    total_usable_area = round(sum(rm.area for rm in habitable_rooms), 2)
    stair_area = round(sum(rm.area for rm in stair_rooms), 2)

    # 1. Spatial Utilization Ratio (usable room area vs available multi-floor footprint area)
    total_floor_footprint = footprint_area * max(1, len(floors))
    area_utilization = min(1.0, total_usable_area / total_floor_footprint) if total_floor_footprint > 0 else 0.0

    # 2. Circulation Area & Ratio
    circ_rooms = [c for fl in floors for c in getattr(fl, 'circulation', [])]
    circ_area = round(sum(c.area for c in circ_rooms), 2)
    # If no explicit corridors, estimate implicit circulation as envelope minus partitioned spaces
    if circ_area == 0.0 and total_floor_footprint > 0:
        circ_area = max(0.0, round(total_floor_footprint - (total_usable_area + stair_area), 2))
    circ_ratio = min(1.0, circ_area / total_floor_footprint) if total_floor_footprint > 0 else 0.0

    # 3. Mandatory Room Satisfaction Ratio
    mandatory_reqs = [r for r in requirements.rooms if r.required]
    if mandatory_reqs:
        mand_pref_results = [
            p for p in preference_evaluations
            if p.category == "room_fulfillment" and p.is_hard_constraint
        ]
        sat_count = sum(1 for p in mand_pref_results if p.status == PreferenceEvaluationStatus.SATISFIED)
        mand_sat_ratio = sat_count / len(mandatory_reqs)
    else:
        mand_sat_ratio = 1.0

    # 4. Preferred Room Size & Dimension Satisfaction Ratio
    dim_pref_results = [p for p in preference_evaluations if p.category == "dimension"]
    if dim_pref_results:
        dim_sat = sum(1 for p in dim_pref_results if p.status == PreferenceEvaluationStatus.SATISFIED)
        preferred_dim_ratio = dim_sat / len(dim_pref_results)
    else:
        preferred_dim_ratio = 1.0

    # 5. Adjacency Satisfaction Ratio
    adj_prefs = [p for p in preference_evaluations if p.category == "adjacency"]
    if adj_prefs:
        sat_adj = sum(1 for p in adj_prefs if p.status == PreferenceEvaluationStatus.SATISFIED)
        adj_sat_ratio = sat_adj / len(adj_prefs)
    else:
        adj_sat_ratio = 1.0

    # 6. Room Aspect Ratios & Dimension Penalty
    aspect_ratios: List[float] = []
    penalties: List[float] = []
    for rm in habitable_rooms:
        w = rm.width_m or 1.0
        l = rm.length_m or 1.0
        if w > 0 and l > 0:
            aspect = max(w, l) / min(w, l)
            aspect_ratios.append(aspect)
            if aspect > 2.5:  # excess aspect penalty (unusually long/narrow rooms)
                penalties.append((aspect - 2.5) * 0.2)

    avg_aspect = (sum(aspect_ratios) / len(aspect_ratios)) if aspect_ratios else 1.0
    dim_penalty = min(1.0, sum(penalties) / max(1, len(habitable_rooms)))

    # 7. Staircase Area Ratio
    stair_ratio = min(1.0, stair_area / total_floor_footprint) if total_floor_footprint > 0 else 0.0

    # 8. Multi-floor distribution balance (standard deviation of room area per floor)
    if len(floors) > 1:
        floor_areas = [fl.target_allocated_area for fl in floors]
        mean_fl = sum(floor_areas) / len(floor_areas) if floor_areas else 1.0
        variance = sum((a - mean_fl) ** 2 for a in floor_areas) / len(floor_areas) if floor_areas else 0.0
        cv = math.sqrt(variance) / mean_fl if mean_fl > 0 else 0.0
        fl_balance = max(0.0, 1.0 - min(1.0, cv))
    else:
        fl_balance = 1.0

    # 9. Parking Satisfaction
    parking_res = next((p for p in preference_evaluations if p.category == "parking"), None)
    if parking_res:
        parking_sat = 1.0 if parking_res.status == PreferenceEvaluationStatus.SATISFIED else 0.0
    else:
        parking_sat = 1.0

    # 10. Exterior Wall Access Ratio & Window Feasibility
    ext_wall_access_count = 0
    for rm in habitable_rooms:
        if rm.polygon and len(rm.polygon) >= 3:
            pts = [(p.x, p.y) for p in rm.polygon]
            r_poly = Polygon(pts)
            if r_poly.is_valid and footprint_poly.is_valid:
                # Room shares boundary with building envelope
                if r_poly.boundary.intersects(footprint_poly.boundary):
                    ext_wall_access_count += 1

    ext_wall_ratio = (ext_wall_access_count / len(habitable_rooms)) if habitable_rooms else 1.0
    window_feas_ratio = ext_wall_ratio

    # 11. Compactness Ratio of Building Footprint (Polsby-Popper: 4 * pi * Area / Perimeter^2)
    perim = footprint_poly.length if footprint_poly and not footprint_poly.is_empty else 1.0
    compactness = (4.0 * math.pi * footprint_area) / (perim * perim) if perim > 0 else 1.0
    compactness = max(0.0, min(1.0, compactness))

    return NumericalFeatureVector(
        feature_schema_version="1.0.0",
        total_usable_room_area_sqm=round(total_usable_area, 2),
        building_footprint_area_sqm=round(footprint_area, 2),
        area_utilization_ratio=round(area_utilization, 3),
        circulation_area_sqm=round(circ_area, 2),
        circulation_ratio=round(circ_ratio, 3),
        mandatory_room_satisfaction_ratio=round(mand_sat_ratio, 3),
        preferred_room_size_satisfaction_ratio=round(preferred_dim_ratio, 3),
        adjacency_satisfaction_ratio=round(adj_sat_ratio, 3),
        average_room_aspect_ratio=round(avg_aspect, 2),
        room_dimension_penalty=round(dim_penalty, 3),
        staircase_area_ratio=round(stair_ratio, 3),
        floor_distribution_balance=round(fl_balance, 3),
        parking_satisfaction=round(parking_sat, 2),
        exterior_wall_access_ratio=round(ext_wall_ratio, 3),
        window_feasibility_ratio=round(window_feas_ratio, 3),
        compactness_ratio=round(compactness, 3),
    )
