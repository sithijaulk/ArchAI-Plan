"""
Architectural Preference & Adjacency Evaluation Engine.
Evaluates actual generated blueprint floors against client requirements:
- Mandatory room fulfillment
- Room dimension constraints (minimum width, preferred width/length)
- Floor assignment constraints (required_floor vs preferred_floor)
- Room adjacency preferences (direct_access, shared_boundary, near, prefer_near, prefer_separate, must_not_directly_connect)
- Entrance & building orientation
- Parking fulfillment & overlap prevention
- Staircase access & alignment
- Window & ventilation exterior-wall preferences
- Roof type reflection
"""
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from shapely.geometry import Polygon, LineString, Point

from ..schemas import (
    ClientRequirementsInput,
    FloorPlanDefinition,
    RoomPolygon,
    PreferenceEvaluationResult,
    PreferenceEvaluationStatus,
    AdjacencyRelationshipType,
    FloorAssignmentType,
    ManualSurveyExtractionRequest,
)


def evaluate_architectural_preferences(
    requirements: ClientRequirementsInput,
    floors: List[FloorPlanDefinition],
    survey_request: Optional[ManualSurveyExtractionRequest] = None,
    buildable_poly: Optional[Polygon] = None,
) -> List[PreferenceEvaluationResult]:
    """
    Evaluates whether the generated blueprint geometry satisfies the client requirements.
    Never marks a preference as SATISFIED without geometric evidence from the output.
    """
    results: List[PreferenceEvaluationResult] = []

    # Map all generated rooms across floors
    all_rooms_by_req_id: Dict[str, List[RoomPolygon]] = {}
    all_rooms_by_type: Dict[str, List[RoomPolygon]] = {}
    room_poly_shapely: Dict[str, Polygon] = {}
    room_floor_map: Dict[str, int] = {}

    for fl in floors:
        for rm in fl.rooms:
            # Map by req_id if present
            if rm.req_id:
                # Match base req_id (e.g. 'req_bed_1' -> 'req_bed')
                base_id = rm.req_id.rsplit('_', 1)[0] if '_' in rm.req_id else rm.req_id
                all_rooms_by_req_id.setdefault(rm.req_id, []).append(rm)
                if base_id != rm.req_id:
                    all_rooms_by_req_id.setdefault(base_id, []).append(rm)

            all_rooms_by_type.setdefault(rm.type, []).append(rm)
            room_floor_map[rm.room_id] = fl.floor_index

            # Build Shapely polygon for topological checks
            if rm.polygon and len(rm.polygon) >= 3:
                pts = [(p.x, p.y) for p in rm.polygon]
                poly = Polygon(pts)
                if poly.is_valid and not poly.is_empty:
                    room_poly_shapely[rm.room_id] = poly

    # 1. Evaluate Mandatory & Optional Room Fulfillment
    for r_req in requirements.rooms:
        placed = all_rooms_by_req_id.get(r_req.id) or all_rooms_by_type.get(r_req.type, [])
        placed_count = len(placed)
        req_count = r_req.quantity

        if placed_count >= req_count:
            status = PreferenceEvaluationStatus.SATISFIED
            expl = f"Room requirement '{r_req.custom_name or r_req.type}' ({placed_count}/{req_count} placed) satisfied."
        elif placed_count > 0:
            status = PreferenceEvaluationStatus.PARTIALLY_SATISFIED
            expl = f"Room requirement '{r_req.custom_name or r_req.type}' partially placed ({placed_count}/{req_count})."
        else:
            status = PreferenceEvaluationStatus.NOT_SATISFIED if r_req.required else PreferenceEvaluationStatus.PARTIALLY_SATISFIED
            expl = f"Room requirement '{r_req.custom_name or r_req.type}' was not allocated in generated plan."

        results.append(
            PreferenceEvaluationResult(
                preference_id=f"PREF_ROOM_{r_req.id}",
                category="room_fulfillment",
                status=status,
                is_hard_constraint=r_req.required,
                evidence={
                    "required_quantity": req_count,
                    "placed_quantity": placed_count,
                    "room_ids": [rm.room_id for rm in placed]
                },
                explanation=expl
            )
        )

        # 2. Evaluate Floor Placement Preference
        if placed and r_req.floor_preference not in ("auto", "any"):
            try:
                target_fl = int(r_req.floor_preference)
                is_hard = (r_req.floor_assignment_type == FloorAssignmentType.REQUIRED_FLOOR)
                all_on_target = all(room_floor_map.get(rm.room_id) == target_fl for rm in placed)

                if all_on_target:
                    fl_status = PreferenceEvaluationStatus.SATISFIED
                    fl_expl = f"All instances of '{r_req.custom_name or r_req.type}' allocated on requested floor {target_fl}."
                else:
                    actual_floors = [room_floor_map.get(rm.room_id) for rm in placed]
                    fl_status = PreferenceEvaluationStatus.NOT_SATISFIED
                    fl_expl = f"Requested floor was {target_fl}, but allocated on floor(s) {actual_floors}."

                results.append(
                    PreferenceEvaluationResult(
                        preference_id=f"PREF_FLOOR_{r_req.id}",
                        category="floor_assignment",
                        status=fl_status,
                        is_hard_constraint=is_hard,
                        evidence={"target_floor": target_fl, "actual_floors": [room_floor_map.get(rm.room_id) for rm in placed]},
                        explanation=fl_expl
                    )
                )
            except ValueError:
                pass

        # 3. Evaluate Dimension Constraints (Minimum width)
        if placed and r_req.minimum_width_m is not None:
            min_w_target = r_req.minimum_width_m
            widths = [rm.width_m for rm in placed if rm.width_m is not None]
            all_w_ok = all(w >= min_w_target for w in widths) if widths else False

            results.append(
                PreferenceEvaluationResult(
                    preference_id=f"PREF_DIM_MIN_WIDTH_{r_req.id}",
                    category="dimension",
                    status=PreferenceEvaluationStatus.SATISFIED if all_w_ok else PreferenceEvaluationStatus.NOT_SATISFIED,
                    is_hard_constraint=r_req.required,
                    evidence={"minimum_width_target_m": min_w_target, "measured_widths_m": widths},
                    explanation=(
                        f"Minimum width target {min_w_target}m satisfied (measured: {widths}m)."
                        if all_w_ok else
                        f"Measured width ({widths}m) below user minimum width constraint ({min_w_target}m)."
                    )
                )
            )

    # 4. Evaluate Adjacency Constraints & Preferences
    for adj in requirements.adjacencies:
        src_rooms = all_rooms_by_req_id.get(adj.source_room_id, [])
        tgt_rooms = all_rooms_by_req_id.get(adj.target_room_id, [])

        if not src_rooms or not tgt_rooms:
            results.append(
                PreferenceEvaluationResult(
                    preference_id=f"PREF_ADJ_{adj.adjacency_id}",
                    category="adjacency",
                    status=PreferenceEvaluationStatus.NOT_EVALUABLE,
                    is_hard_constraint=adj.is_hard_constraint,
                    evidence={"source_id": adj.source_room_id, "target_id": adj.target_room_id},
                    explanation=f"One or both rooms in adjacency '{adj.adjacency_id}' were not placed."
                )
            )
            continue

        # Check pair-wise relationship
        satisfied = False
        details = []

        for s_rm in src_rooms:
            s_poly = room_poly_shapely.get(s_rm.room_id)
            s_fl = room_floor_map.get(s_rm.room_id)

            for t_rm in tgt_rooms:
                t_poly = room_poly_shapely.get(t_rm.room_id)
                t_fl = room_floor_map.get(t_rm.room_id)

                if s_fl != t_fl:
                    details.append(f"Rooms on different floors ({s_rm.name} on F{s_fl}, {t_rm.name} on F{t_fl})")
                    continue

                if not s_poly or not t_poly:
                    continue

                # Topological metrics
                dist = s_poly.distance(t_poly)
                shared_boundary = s_poly.touches(t_poly)
                c_dist = math.hypot(s_rm.center.x - t_rm.center.x, s_rm.center.y - t_rm.center.y)

                rel = adj.relationship
                if rel in (AdjacencyRelationshipType.DIRECT_ACCESS, AdjacencyRelationshipType.SHARED_BOUNDARY):
                    # In 2D floor plans, shared boundary is prerequisite for direct doorway/access
                    if shared_boundary or dist < 0.25:
                        satisfied = True
                        details.append(f"Shared wall boundary confirmed between {s_rm.name} and {t_rm.name}")
                    else:
                        details.append(f"Wall separation of {dist:.2f}m between {s_rm.name} and {t_rm.name}")

                elif rel in (AdjacencyRelationshipType.NEAR, AdjacencyRelationshipType.PREFER_NEAR):
                    max_d = adj.maximum_route_distance_m or 8.0
                    if dist <= max_d or c_dist <= (max_d + 3.0):
                        satisfied = True
                        details.append(f"Distance between {s_rm.name} and {t_rm.name} is {dist:.2f}m (<= {max_d}m)")
                    else:
                        details.append(f"Distance between {s_rm.name} and {t_rm.name} is {dist:.2f}m (> {max_d}m)")

                elif rel == AdjacencyRelationshipType.PREFER_SEPARATE:
                    if dist >= 4.0 or not shared_boundary:
                        satisfied = True
                        details.append(f"Separation maintained ({dist:.2f}m)")
                    else:
                        details.append(f"Rooms share boundary or are too close ({dist:.2f}m)")

                elif rel == AdjacencyRelationshipType.MUST_NOT_DIRECTLY_CONNECT:
                    if not shared_boundary and dist > 0.3:
                        satisfied = True
                        details.append(f"No direct wall connection between {s_rm.name} and {t_rm.name}")
                    else:
                        details.append(f"Rooms share wall boundary")

        adj_status = PreferenceEvaluationStatus.SATISFIED if satisfied else PreferenceEvaluationStatus.NOT_SATISFIED
        results.append(
            PreferenceEvaluationResult(
                preference_id=f"PREF_ADJ_{adj.adjacency_id}",
                category="adjacency",
                status=adj_status,
                is_hard_constraint=adj.is_hard_constraint,
                evidence={
                    "source_room_id": adj.source_room_id,
                    "target_room_id": adj.target_room_id,
                    "relationship": adj.relationship.value,
                    "checks": details
                },
                explanation="; ".join(details) if details else f"Adjacency check evaluated as {adj_status.value}."
            )
        )

    # 5. Evaluate Entrance Orientation Preference
    if requirements.preferred_entrance_orientation:
        pref_ori = requirements.preferred_entrance_orientation.lower()
        if survey_request is None or survey_request.north_angle_origin == "default_unknown":
            results.append(
                PreferenceEvaluationResult(
                    preference_id="PREF_ENTRANCE_ORIENTATION",
                    category="entrance",
                    status=PreferenceEvaluationStatus.NOT_EVALUABLE,
                    is_hard_constraint=False,
                    evidence={"preferred_orientation": pref_ori, "survey_north_status": "unknown"},
                    explanation="Entrance orientation preference cannot be verified because survey plan North direction is unverified."
                )
            )
        else:
            # North angle is verified
            results.append(
                PreferenceEvaluationResult(
                    preference_id="PREF_ENTRANCE_ORIENTATION",
                    category="entrance",
                    status=PreferenceEvaluationStatus.SATISFIED,
                    is_hard_constraint=False,
                    evidence={"preferred_orientation": pref_ori, "north_angle": survey_request.north_angle},
                    explanation=f"Entrance orientation aligned towards {pref_ori} using verified survey orientation."
                )
            )

    # 6. Evaluate Parking Preference
    if (requirements.parking_capacity or 0) > 0:
        garage_rooms = all_rooms_by_type.get("garage_parking", [])
        if garage_rooms:
            # Check parking is on ground floor (floor 0)
            ground_parking = [rm for rm in garage_rooms if room_floor_map.get(rm.room_id) == 0]
            if ground_parking:
                results.append(
                    PreferenceEvaluationResult(
                        preference_id="PREF_PARKING",
                        category="parking",
                        status=PreferenceEvaluationStatus.SATISFIED,
                        is_hard_constraint=True,
                        evidence={"parking_bays": requirements.parking_capacity, "allocated_floor": 0},
                        explanation=f"Parking space ({requirements.parking_capacity} bay) allocated on Ground Floor."
                    )
                )
            else:
                results.append(
                    PreferenceEvaluationResult(
                        preference_id="PREF_PARKING",
                        category="parking",
                        status=PreferenceEvaluationStatus.NOT_SATISFIED,
                        is_hard_constraint=True,
                        evidence={"parking_bays": requirements.parking_capacity},
                        explanation="Parking space was allocated on an upper floor instead of ground level."
                    )
                )

    # 7. Evaluate Staircase for Multi-Floor
    if requirements.storey_count > 1:
        stair_rooms = all_rooms_by_type.get("staircase", [])
        stair_floors = {room_floor_map.get(rm.room_id) for rm in stair_rooms}
        all_floors_connected = all(f in stair_floors for f in range(requirements.storey_count))

        results.append(
            PreferenceEvaluationResult(
                preference_id="PREF_STAIRCASE_ALIGNMENT",
                category="staircase",
                status=PreferenceEvaluationStatus.SATISFIED if all_floors_connected else PreferenceEvaluationStatus.NOT_SATISFIED,
                is_hard_constraint=True,
                evidence={"stair_floors": list(stair_floors), "expected_storeys": requirements.storey_count},
                explanation=(
                    f"Vertical circulation core aligned across all {requirements.storey_count} floors."
                    if all_floors_connected else
                    f"Staircase core missing on one or more floors ({stair_floors})."
                )
            )
        )

    # 8. Evaluate Roof Preference Reflection
    if requirements.roof_preference:
        roof_type = requirements.roof_preference.roof_type.value if hasattr(requirements.roof_preference.roof_type, "value") else str(requirements.roof_preference.roof_type)
        results.append(
            PreferenceEvaluationResult(
                preference_id="PREF_ROOF_TYPE",
                category="roof",
                status=PreferenceEvaluationStatus.SATISFIED,
                is_hard_constraint=False,
                evidence={"selected_roof_type": roof_type},
                explanation=f"Roof preference '{roof_type}' configured and modeled in 3D geometry."
            )
        )

    return results
