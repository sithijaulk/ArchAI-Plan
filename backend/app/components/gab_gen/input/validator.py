"""
Validation and reconciliation of Client Requirements for GAB-Gen.
Ensures logical consistency:
- Attached bathrooms cannot exceed total bathrooms.
- Master bedrooms cannot exceed total bedrooms.
- Storey count (1-4) compatibility with room counts.
- Reconciles explicit count summaries with individual room programme list.
"""
from typing import Any, Dict, List, Optional
from ..schemas import ClientRequirementsInput, RoomRequirement, RoomPriority


def reconcile_and_validate_requirements(req: ClientRequirementsInput) -> Dict[str, Any]:
    """
    Validates logical consistency of client requirements and builds a normalized room programme.
    Returns:
        {
            "valid": bool,
            "errors": List[str],
            "warnings": List[str],
            "normalized_rooms": List[RoomRequirement]
        }
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Total bedroom / master bedroom consistency
    bed_count = req.bedroom_count
    master_bed_count = req.master_bedroom_count

    # Check against individual rooms array if provided
    prog_beds = sum(r.quantity for r in req.rooms if r.type == "bedroom")
    prog_master = sum(r.quantity for r in req.rooms if r.type == "master_bedroom")
    
    total_beds_in_prog = prog_beds + prog_master

    if bed_count is not None and master_bed_count is not None:
        if master_bed_count > bed_count:
            errors.append(
                f"Master bedroom count ({master_bed_count}) cannot exceed total bedroom count ({bed_count})."
            )

    # 2. Bathroom consistency
    bath_count = req.bathroom_count
    att_bath_count = req.attached_bathroom_count

    prog_common_baths = sum(r.quantity for r in req.rooms if r.type in ("bathroom", "common_bathroom"))
    prog_att_baths = sum(r.quantity for r in req.rooms if r.type == "attached_bathroom")
    total_baths_in_prog = prog_common_baths + prog_att_baths

    if bath_count is not None and att_bath_count is not None:
        if att_bath_count > bath_count:
            errors.append(
                f"Attached bathroom count ({att_bath_count}) cannot exceed total bathroom count ({bath_count})."
            )

    # 3. Storey count limits
    if req.storey_count < 1 or req.storey_count > 4:
        errors.append(f"Storey count ({req.storey_count}) must be between 1 and 4.")

    # 4. Check floor preferences against storey count
    for r in req.rooms:
        if r.floor_preference not in ("auto", "any"):
            try:
                fl_idx = int(r.floor_preference)
                if fl_idx < 0 or fl_idx >= req.storey_count:
                    errors.append(
                        f"Room '{r.custom_name or r.type}' has floor preference '{r.floor_preference}', "
                        f"which exceeds the building storey count of {req.storey_count} floors."
                    )
            except ValueError:
                pass

    # 5. Build normalized list of rooms (synthesizing from counts if rooms list is partial/empty)
    normalized_rooms: List[RoomRequirement] = list(req.rooms)
    existing_types = {r.type for r in normalized_rooms}

    # If living room was explicitly required or living_room_required is True
    if req.living_room_required and "living_room" not in existing_types:
        normalized_rooms.append(
            RoomRequirement(
                id="req_living_room_auto",
                type="living_room",
                quantity=1,
                required=True,
                preferred_min_area=22.0,
                floor_preference=0,
                priority=RoomPriority.HIGH,
                custom_name="Living Room"
            )
        )
        existing_types.add("living_room")

    # Kitchen
    if req.kitchen_required and "kitchen" not in existing_types:
        normalized_rooms.append(
            RoomRequirement(
                id="req_kitchen_auto",
                type="kitchen",
                quantity=1,
                required=True,
                preferred_min_area=12.0,
                floor_preference=0,
                priority=RoomPriority.HIGH,
                custom_name="Kitchen"
            )
        )
        existing_types.add("kitchen")

    # Dining
    if req.dining_room_required and "dining_area" not in existing_types:
        normalized_rooms.append(
            RoomRequirement(
                id="req_dining_auto",
                type="dining_area",
                quantity=1,
                required=True,
                preferred_min_area=14.0,
                floor_preference=0,
                priority=RoomPriority.HIGH,
                custom_name="Dining Area"
            )
        )
        existing_types.add("dining_area")

    # Reconcile bedrooms from summary counts if provided
    if bed_count is not None and total_beds_in_prog < bed_count:
        needed_master = (master_bed_count or 0) - prog_master
        if needed_master > 0:
            normalized_rooms.append(
                RoomRequirement(
                    id="req_master_bed_auto",
                    type="master_bedroom",
                    quantity=needed_master,
                    required=True,
                    preferred_min_area=16.0,
                    floor_preference="auto",
                    priority=RoomPriority.HIGH,
                    custom_name="Master Bedroom"
                )
            )
        needed_regular = bed_count - (master_bed_count or 0) - prog_beds
        if needed_regular > 0:
            normalized_rooms.append(
                RoomRequirement(
                    id="req_bed_auto",
                    type="bedroom",
                    quantity=needed_regular,
                    required=True,
                    preferred_min_area=12.0,
                    floor_preference="auto",
                    priority=RoomPriority.HIGH,
                    custom_name="Bedroom"
                )
            )

    # Reconcile bathrooms from summary counts if provided
    if bath_count is not None and total_baths_in_prog < bath_count:
        needed_att = (att_bath_count or 0) - prog_att_baths
        if needed_att > 0:
            normalized_rooms.append(
                RoomRequirement(
                    id="req_att_bath_auto",
                    type="attached_bathroom",
                    quantity=needed_att,
                    required=True,
                    preferred_min_area=4.5,
                    floor_preference="auto",
                    priority=RoomPriority.HIGH,
                    custom_name="Attached Bathroom"
                )
            )
        needed_common = bath_count - (att_bath_count or 0) - prog_common_baths
        if needed_common > 0:
            normalized_rooms.append(
                RoomRequirement(
                    id="req_common_bath_auto",
                    type="common_bathroom",
                    quantity=needed_common,
                    required=True,
                    preferred_min_area=4.0,
                    floor_preference="auto",
                    priority=RoomPriority.HIGH,
                    custom_name="Common Bathroom"
                )
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized_rooms": normalized_rooms
    }
