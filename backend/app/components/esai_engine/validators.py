"""
Validators Module
Cross-validates client requirements against:
- Furniture Catalog (existence, supported room types, allowed dimensions/rotations)
- Ergonomic Standards (clearances, enforceable rules)
- Room Spatial Geometry (room area, boundaries, door conflicts)
Returns structured ValidationResultDTO with errors, warnings, and informational notices.
"""
from typing import List, Optional
from shapely.geometry import Point

from .contracts import (
    FurnitureRequirementItem,
    RoomRequirementsDTO,
    RoomDTO,
    ValidationMessage,
    ValidationResultDTO,
    StructuralInputDTO,
)
from .catalog import FurnitureCatalogRepository
from .rules import ErgonomicStandardsRepository
from .geometry import (
    compute_footprint_polygon,
    is_footprint_within_room,
    is_point_inside_room
)
from .openings import compute_door_swing_box


class EsaiInputValidator:
    """Performs comprehensive validation of structural input and client furniture requirements."""

    def __init__(
        self,
        catalog_repo: Optional[FurnitureCatalogRepository] = None,
        standards_repo: Optional[ErgonomicStandardsRepository] = None
    ):
        self.catalog_repo = catalog_repo or FurnitureCatalogRepository.get_instance()
        self.standards_repo = standards_repo or ErgonomicStandardsRepository.get_instance()

    def validate_structural_input(self, structural_input: StructuralInputDTO) -> ValidationResultDTO:
        errors: List[ValidationMessage] = []
        warnings: List[ValidationMessage] = []
        info: List[ValidationMessage] = []

        if not structural_input.floors:
            warnings.append(ValidationMessage(
                code="NO_FLOORS_FOUND",
                path="floor_plan.floors",
                message="No floors or rooms were detected in the structural input floor plan.",
                severity="warning"
            ))

        seen_room_ids = set()
        for floor in structural_input.floors:
            for room in floor.rooms:
                if room.room_id in seen_room_ids:
                    errors.append(ValidationMessage(
                        code="DUPLICATE_ROOM_ID",
                        path=f"floor_plan.floors[{floor.floor_id}].rooms",
                        room_id=room.room_id,
                        message=f"Duplicate room ID '{room.room_id}' detected across floors.",
                        severity="error"
                    ))
                seen_room_ids.add(room.room_id)

                if room.area_sqm < 1.0:
                    errors.append(ValidationMessage(
                        code="ROOM_AREA_TOO_SMALL",
                        path="floor_plan",
                        room_id=room.room_id,
                        message=f"Room '{room.room_id}' area is unrealistically small ({room.area_sqm:.2f} m²).",
                        severity="error"
                    ))

                if not room.doors:
                    warnings.append(ValidationMessage(
                        code="ROOM_WITHOUT_DOORS",
                        path="floor_plan",
                        room_id=room.room_id,
                        message=f"Room '{room.room_id}' does not have any doors defined.",
                        severity="warning"
                    ))

        return ValidationResultDTO(
            valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings,
            info=info
        )

    def validate_room_requirements(
        self,
        requirements: RoomRequirementsDTO,
        room: Optional[RoomDTO] = None
    ) -> ValidationResultDTO:
        errors: List[ValidationMessage] = []
        warnings: List[ValidationMessage] = []
        info: List[ValidationMessage] = []

        # Check room match
        if room and room.room_id != requirements.room_id:
            errors.append(ValidationMessage(
                code="ROOM_ID_MISMATCH",
                path="requirements.room_id",
                room_id=requirements.room_id,
                message=f"Requirements room ID '{requirements.room_id}' does not match target room '{room.room_id}'.",
                severity="error"
            ))

        seen_instance_ids = set()
        total_furniture_footprint_sqm = 0.0

        for item in requirements.items:
            # 1. Instance ID uniqueness
            if item.instance_id in seen_instance_ids:
                errors.append(ValidationMessage(
                    code="DUPLICATE_INSTANCE_ID",
                    path="requirements.items",
                    room_id=requirements.room_id,
                    asset_id=item.instance_id,
                    message=f"Duplicate instance ID '{item.instance_id}' in room requirements.",
                    severity="error"
                ))
            seen_instance_ids.add(item.instance_id)

            # 2. Check catalog existence
            try:
                catalog_item = self.catalog_repo.get_by_id(item.catalog_id)
            except Exception:
                errors.append(ValidationMessage(
                    code="CATALOG_ITEM_UNKNOWN",
                    path=f"requirements.items.{item.instance_id}.catalog_id",
                    room_id=requirements.room_id,
                    asset_id=item.instance_id,
                    message=f"Catalog item '{item.catalog_id}' does not exist in the furniture catalog.",
                    severity="error"
                ))
                continue

            # 3. Supported room type
            effective_room_type = requirements.room_type.value
            if (
                effective_room_type not in catalog_item.supported_room_types
                and "all" not in catalog_item.supported_room_types
            ):
                warnings.append(ValidationMessage(
                    code="UNCONVENTIONAL_ROOM_ASSET",
                    path=f"requirements.items.{item.instance_id}",
                    room_id=requirements.room_id,
                    asset_id=item.instance_id,
                    message=f"Asset '{catalog_item.name}' ({catalog_item.category.value}) is uncommon for room type '{effective_room_type}'.",
                    severity="warning"
                ))

            # 4. Check dimension validity
            dims = item.custom_dimensions or catalog_item.dimensions
            if dims.width <= 0 or dims.depth <= 0 or dims.height <= 0:
                errors.append(ValidationMessage(
                    code="INVALID_DIMENSIONS",
                    path=f"requirements.items.{item.instance_id}.dimensions",
                    room_id=requirements.room_id,
                    asset_id=item.instance_id,
                    message=f"Dimensions for '{item.instance_id}' must be positive numbers.",
                    severity="error"
                ))
            else:
                total_furniture_footprint_sqm += (dims.width * dims.depth * item.quantity)

            # 5. Check clearance rule
            rule_id = catalog_item.default_clearance_rule_id
            try:
                rule = self.standards_repo.get_by_id(rule_id)
                if not rule.is_enforceable:
                    warnings.append(ValidationMessage(
                        code="UNVERIFIED_ERGONOMIC_RULE",
                        path=f"rules.{rule_id}",
                        room_id=requirements.room_id,
                        asset_id=item.instance_id,
                        message=f"Rule '{rule_id}' is marked unverified in standards repository.",
                        severity="warning"
                    ))
            except Exception:
                warnings.append(ValidationMessage(
                    code="RULE_NOT_FOUND",
                    path=f"rules.{rule_id}",
                    room_id=requirements.room_id,
                    asset_id=item.instance_id,
                    message=f"Referenced clearance rule '{rule_id}' not found in standards.",
                    severity="warning"
                ))

            # 6. User locked asset checks
            if item.user_locked:
                if not item.locked_position:
                    errors.append(ValidationMessage(
                        code="LOCKED_POSITION_MISSING",
                        path=f"requirements.items.{item.instance_id}.locked_position",
                        room_id=requirements.room_id,
                        asset_id=item.instance_id,
                        message=f"Asset '{item.instance_id}' is user_locked but no locked_position was provided.",
                        severity="error"
                    ))
                elif room:
                    # Verify locked position is inside room polygon
                    if not is_point_inside_room(item.locked_position, room.polygon):
                        errors.append(ValidationMessage(
                            code="LOCKED_POSITION_OUTSIDE_ROOM",
                            path=f"requirements.items.{item.instance_id}.locked_position",
                            room_id=requirements.room_id,
                            asset_id=item.instance_id,
                            message=f"Locked position ({item.locked_position.x}, {item.locked_position.y}) is outside the room polygon.",
                            severity="error"
                        ))
                    else:
                        rot = item.locked_rotation or 0
                        footprint = compute_footprint_polygon(item.locked_position, dims, rot)
                        if not is_footprint_within_room(footprint, room.polygon):
                            warnings.append(ValidationMessage(
                                code="LOCKED_FOOTPRINT_CLIPS_WALL",
                                path=f"requirements.items.{item.instance_id}.locked_position",
                                room_id=requirements.room_id,
                                asset_id=item.instance_id,
                                message=f"Locked footprint partially intersects room boundary walls.",
                                severity="warning"
                            ))

                        # Check collision with door swing
                        for door in room.doors:
                            door_swing = compute_door_swing_box(door)
                            if footprint.intersects(door_swing):
                                errors.append(ValidationMessage(
                                    code="LOCKED_ASSET_BLOCKS_DOOR",
                                    path=f"requirements.items.{item.instance_id}.locked_position",
                                    room_id=requirements.room_id,
                                    asset_id=item.instance_id,
                                    message=f"Locked asset '{item.instance_id}' blocks door '{door.id}' swing clearance.",
                                    severity="error"
                                ))

        # 7. Total furniture density check against room area
        if room and room.area_sqm > 0:
            coverage_ratio = total_furniture_footprint_sqm / room.area_sqm
            if coverage_ratio > 0.65:
                warnings.append(ValidationMessage(
                    code="EXCESSIVE_FURNITURE_DENSITY",
                    path="requirements.items",
                    room_id=requirements.room_id,
                    message=f"Total furniture footprint covers {coverage_ratio * 100:.1f}% of room area (exceeds recommended 60%).",
                    severity="warning"
                ))
            info.append(ValidationMessage(
                code="ROOM_DENSITY_INFO",
                path="requirements.items",
                room_id=requirements.room_id,
                message=f"Estimated furniture coverage: {coverage_ratio * 100:.1f}% of {room.area_sqm:.2f} m².",
                severity="info"
            ))

        return ValidationResultDTO(
            valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings,
            info=info
        )
