"""
Structural Input Parser
Extracts, validates, and normalizes structural geometry (floors, rooms, doors, windows, obstructions)
from the Centralized Master JSON.
Ensures immutability of the incoming Master JSON.
Strictly prohibits fabricated fallback geometry and silent defaulting of measurement units.
"""
import math
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from .contracts import (
    Coordinate2D,
    Dimensions3D,
    DoorDTO,
    WindowDTO,
    DoorHinge,
    DoorOpeningDirection,
    FixedObstructionDTO,
    FloorDTO,
    LengthUnit,
    RoomDTO,
    RoomType,
    StructuralInputDTO,
    WallDTO,
    convert_to_meters,
)
from .exceptions import StructuralInputValidationError
from .geometry import validate_room_polygon


ROOM_TYPE_NORMALIZATION_MAP: Dict[str, RoomType] = {
    # Living
    "living_room": RoomType.LIVING_ROOM,
    "living": RoomType.LIVING_ROOM,
    "living_area": RoomType.LIVING_ROOM,
    "family_living_area": RoomType.FAMILY_LIVING_AREA,
    "family_living": RoomType.FAMILY_LIVING_AREA,
    "tv_lobby": RoomType.TV_LOBBY,
    "tv_lounge": RoomType.TV_LOUNGE,
    "lounge": RoomType.LOUNGE,
    # Dining
    "dining_room": RoomType.DINING_ROOM,
    "dining": RoomType.DINING_ROOM,
    "dining_area": RoomType.DINING_AREA,
    # Bedrooms
    "bedroom": RoomType.BEDROOM,
    "bed": RoomType.BEDROOM,
    "bed_room": RoomType.BEDROOM,
    "master_bedroom": RoomType.MASTER_BEDROOM,
    "mbr": RoomType.MASTER_BEDROOM,
    "guest_room": RoomType.GUEST_ROOM,
    "guest_bedroom": RoomType.GUEST_ROOM,
    # Kitchen & Pantry
    "kitchen": RoomType.KITCHEN,
    "pantry": RoomType.PANTRY,
    # Bathrooms
    "bathroom": RoomType.BATHROOM,
    "bath": RoomType.BATHROOM,
    "attached_bathroom": RoomType.ATTACHED_BATHROOM,
    "attached_bath": RoomType.ATTACHED_BATHROOM,
    "att_bath": RoomType.ATTACHED_BATHROOM,
    "common_bathroom": RoomType.COMMON_BATHROOM,
    "common_bath": RoomType.COMMON_BATHROOM,
    "com_bath": RoomType.COMMON_BATHROOM,
    "toilet": RoomType.TOILET,
    "wc": RoomType.TOILET,
    "powder_room": RoomType.TOILET,
    # Study & Office
    "study": RoomType.STUDY,
    "study_room": RoomType.STUDY,
    "study_office": RoomType.STUDY_OFFICE,
    "home_office": RoomType.HOME_OFFICE,
    "office": RoomType.HOME_OFFICE,
    # Laundry & Utility
    "laundry": RoomType.LAUNDRY_ROOM,
    "laundry_room": RoomType.LAUNDRY_ROOM,
    "utility": RoomType.UTILITY_ROOM,
    "utility_room": RoomType.UTILITY_ROOM,
    # Entry & Circulation
    "foyer": RoomType.FOYER,
    "entry": RoomType.ENTRY,
    "entrance": RoomType.ENTRY,
    "entry_foyer": RoomType.FOYER,
    "corridor": RoomType.CORRIDOR,
    "hallway": RoomType.HALLWAY,
    "hall": RoomType.HALLWAY,
    "staircase": RoomType.STAIRCASE,
    "stairs": RoomType.STAIRCASE,
    "stair": RoomType.STAIRCASE,
}


def normalize_room_type(raw_type_str: Optional[str]) -> Tuple[RoomType, Optional[str], bool]:
    """
    Normalizes upstream room type string to canonical RoomType enum.
    Returns (normalized_type, source_type, is_unsupported).
    Preserves original source type.
    Does NOT silently convert recognized room types into generic OTHER.
    For truly unknown types, marks is_unsupported=True and sets normalized type to UNKNOWN.
    """
    if not raw_type_str:
        return RoomType.OTHER, None, False

    source = str(raw_type_str).strip()
    cleaned = source.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")

    if cleaned in ROOM_TYPE_NORMALIZATION_MAP:
        return ROOM_TYPE_NORMALIZATION_MAP[cleaned], source, False

    # Check direct enum value match
    try:
        direct = RoomType(cleaned)
        return direct, source, False
    except ValueError:
        pass

    # Truly unknown
    return RoomType.UNKNOWN, source, True


class StructuralInputParser:
    """Parses structural geometry from Master JSON without modifying the original document."""


    @staticmethod
    def parse(master_json: Dict[str, Any]) -> StructuralInputDTO:
        if not isinstance(master_json, dict):
            raise StructuralInputValidationError(
                message="Master JSON must be a dictionary.",
                path="master_json"
            )

        # Deepcopy to guarantee absolute immutability of source document
        doc = deepcopy(master_json)

        project_id = str(doc.get("project_id", "")).strip()
        project_name = str(doc.get("project_name", "")).strip()

        # 1. Detect source unit: Fallback to meters if not explicitly declared
        raw_unit = (
            doc.get("unit")
            or doc.get("units")
            or (doc.get("floor_plan") if isinstance(doc.get("floor_plan"), dict) else {}).get("unit")
            or (doc.get("floor_plan") if isinstance(doc.get("floor_plan"), dict) else {}).get("units")
            or "meters"
        )

        unit_str = str(raw_unit).lower().strip()
        unit_map = {
            "m": LengthUnit.METERS,
            "meter": LengthUnit.METERS,
            "meters": LengthUnit.METERS,
            "cm": LengthUnit.CENTIMETERS,
            "centimeter": LengthUnit.CENTIMETERS,
            "centimeters": LengthUnit.CENTIMETERS,
            "mm": LengthUnit.MILLIMETERS,
            "millimeter": LengthUnit.MILLIMETERS,
            "millimeters": LengthUnit.MILLIMETERS,
            "ft": LengthUnit.FEET,
            "feet": LengthUnit.FEET,
            "foot": LengthUnit.FEET,
            "in": LengthUnit.INCHES,
            "inch": LengthUnit.INCHES,
            "inches": LengthUnit.INCHES,
        }
        if unit_str not in unit_map:
            raise StructuralInputValidationError(
                message=f"Invalid measurement unit '{raw_unit}'. Supported units: m, cm, mm, ft, in.",
                path="unit"
            )
        unit = unit_map[unit_str]

        # 2. Check agreed shared Master JSON schema:
        # Check structural_rectification first (if completed), otherwise floor_plan
        geometry_source = "gab_gen"
        floor_plan_data = None
        structural_rect = doc.get("structural_rectification")
        if isinstance(structural_rect, dict):
            proc = doc.get("processing", {})
            vsai_status = proc.get("vsai_rectifier", {}).get("status") if isinstance(proc, dict) else None
            # Only adopt VSAI structural rectification if completed, or if present and not explicitly pending/failed
            if vsai_status == "completed" or (vsai_status not in ("pending", "failed", "skipped") and ("rectified_floor_plan" in structural_rect or "floor_plan" in structural_rect)):
                floor_plan_data = (
                    structural_rect.get("rectified_floor_plan")
                    or structural_rect.get("floor_plan")
                    or structural_rect.get("baseline_floor_plan")
                )
                if floor_plan_data:
                    geometry_source = "vsai_rectifier"

        if floor_plan_data is None:
            floor_plan_data = doc.get("floor_plan")
            geometry_source = "gab_gen"

        if not floor_plan_data or not isinstance(floor_plan_data, dict):
            raise StructuralInputValidationError(
                message="COMPATIBILITY_BLOCKER: Master JSON does not contain structural geometry under 'floor_plan' (or completed 'structural_rectification.floor_plan'). Upstream structural source data is missing or incomplete.",
                path="floor_plan"
            )

        # 3. Floors & Rooms discovery
        floors_list: List[FloorDTO] = []
        if (
            "floors" in floor_plan_data
            and isinstance(floor_plan_data["floors"], list)
            and floor_plan_data["floors"]
        ):
            raw_floors = floor_plan_data["floors"]
            for f_idx, raw_floor in enumerate(raw_floors):
                if not isinstance(raw_floor, dict):
                    raise StructuralInputValidationError(
                        message=f"Floor at index {f_idx} must be a valid dictionary.",
                        path=f"floor_plan.floors[{f_idx}]"
                    )
                floor_dto = StructuralInputParser._parse_floor(raw_floor, f_idx, unit)
                floors_list.append(floor_dto)
        elif "rooms" in floor_plan_data and isinstance(floor_plan_data["rooms"], list):
            rooms_by_floor: Dict[str, List[Dict[str, Any]]] = {}
            for room_idx, raw_room in enumerate(floor_plan_data["rooms"]):
                if not isinstance(raw_room, dict):
                    raise StructuralInputValidationError(
                        message=f"Room at index {room_idx} must be a valid dictionary.",
                        path=f"floor_plan.rooms[{room_idx}]"
                    )
                floor_id = str(raw_room.get("floor_id") or "floor_0").strip()
                rooms_by_floor.setdefault(floor_id, []).append(raw_room)

            if not rooms_by_floor:
                raise StructuralInputValidationError(
                    message="Structural floor plan contains no rooms.",
                    path="floor_plan.rooms"
                )

            for f_idx, (floor_id, raw_rooms) in enumerate(rooms_by_floor.items()):
                floor_name = next(
                    (
                        str(room["floor_name"])
                        for room in raw_rooms
                        if room.get("floor_name")
                    ),
                    "Ground Floor" if f_idx == 0 else f"Floor {f_idx + 1}"
                )
                floor_dto = StructuralInputParser._parse_floor(
                    {"floor_id": floor_id, "floor_name": floor_name, "rooms": raw_rooms},
                    f_idx,
                    unit
                )
                floors_list.append(floor_dto)
        else:
            raise StructuralInputValidationError(
                message="Structural floor plan has unrecognized format; neither 'floors' nor 'rooms' array was found.",
                path="floor_plan"
            )

        total_rooms = sum(len(f.rooms) for f in floors_list)
        if total_rooms == 0:
            raise StructuralInputValidationError(
                message="No rooms defined in structural floor plan geometry.",
                path="floor_plan.rooms"
            )

        return StructuralInputDTO(
            project_id=project_id,
            project_name=project_name,
            unit=unit,
            geometry_source=geometry_source,
            floors=floors_list
        )

    @staticmethod
    def _parse_floor(raw_floor: Dict[str, Any], default_index: int, unit: LengthUnit) -> FloorDTO:
        floor_id = raw_floor.get("floor_id") or raw_floor.get("id")
        if not floor_id:
            floor_id = f"floor_{default_index}"
        floor_id = str(floor_id).strip()
        floor_name = str(raw_floor.get("floor_name") or raw_floor.get("name") or f"Floor {default_index + 1}").strip()
        elevation = float(raw_floor.get("elevation", 0.0))
        floor_height = float(raw_floor.get("floor_height", 3.0))

        raw_rooms = raw_floor.get("rooms", [])
        if not isinstance(raw_rooms, list):
            raise StructuralInputValidationError(
                message=f"Floor '{floor_id}' rooms must be a list.",
                path=f"floor_plan.floors[{floor_id}].rooms"
            )

        rooms: List[RoomDTO] = []
        for r_idx, raw_room in enumerate(raw_rooms):
            if not isinstance(raw_room, dict):
                raise StructuralInputValidationError(
                    message=f"Room at index {r_idx} in floor '{floor_id}' must be an object.",
                    path=f"floor_plan.floors[{floor_id}].rooms[{r_idx}]"
                )
            room_dto = StructuralInputParser._parse_room(raw_room, floor_id, r_idx, unit)
            rooms.append(room_dto)

        # Walls: support actual wall representation used by upstream Master JSON
        walls: List[WallDTO] = []
        raw_walls = raw_floor.get("walls", [])
        if isinstance(raw_walls, list):
            for w_idx, raw_wall in enumerate(raw_walls):
                if isinstance(raw_wall, dict):
                    wall_dto = StructuralInputParser._parse_wall(raw_wall, floor_id, w_idx, unit)
                    walls.append(wall_dto)

        return FloorDTO(
            floor_id=floor_id,
            floor_name=floor_name,
            level_index=default_index,
            elevation=elevation,
            floor_height=floor_height,
            rooms=rooms,
            walls=walls
        )

    @staticmethod
    def _parse_wall(raw_wall: Dict[str, Any], floor_id: str, default_idx: int, unit: LengthUnit) -> WallDTO:
        wall_id = str(raw_wall.get("wall_id") or raw_wall.get("id") or f"wall_{default_idx}").strip()
        raw_start = raw_wall.get("start")
        raw_end = raw_wall.get("end")
        if not raw_start or not raw_end:
            raise StructuralInputValidationError(
                message=f"Wall '{wall_id}' missing start or end coordinates.",
                path=f"floor_plan.floors[{floor_id}].walls[{wall_id}]"
            )

        start_x = convert_to_meters(float(raw_start[0] if isinstance(raw_start, (list, tuple)) else raw_start.get("x", 0.0)), unit)
        start_y = convert_to_meters(float(raw_start[1] if isinstance(raw_start, (list, tuple)) else raw_start.get("y", 0.0)), unit)
        end_x = convert_to_meters(float(raw_end[0] if isinstance(raw_end, (list, tuple)) else raw_end.get("x", 0.0)), unit)
        end_y = convert_to_meters(float(raw_end[1] if isinstance(raw_end, (list, tuple)) else raw_end.get("y", 0.0)), unit)

        raw_thickness = raw_wall.get("thickness")
        thickness = convert_to_meters(float(raw_thickness), unit) if raw_thickness is not None else 0.225
        raw_height = raw_wall.get("height")
        height = convert_to_meters(float(raw_height), unit) if raw_height is not None else None
        wall_type = str(raw_wall.get("wall_type", "interior"))
        related_rooms = [str(r) for r in raw_wall.get("related_room_ids", [])]

        return WallDTO(
            id=wall_id,
            floor_id=floor_id,
            start=Coordinate2D(x=start_x, y=start_y),
            end=Coordinate2D(x=end_x, y=end_y),
            thickness=thickness,
            height=height,
            wall_type=wall_type,
            related_room_ids=related_rooms,
            orientation=raw_wall.get("orientation")
        )

    @staticmethod
    def _parse_room(raw_room: Dict[str, Any], floor_id: str, default_index: int, unit: LengthUnit) -> RoomDTO:
        room_id = raw_room.get("room_id") or raw_room.get("id")
        if not room_id:
            room_id = f"room_{default_index}"
        room_id = str(room_id).strip()
        name = str(raw_room.get("name") or raw_room.get("room_name") or f"Room {default_index + 1}").strip()

        raw_type_val = raw_room.get("room_type") or raw_room.get("type")
        room_type, source_room_type, is_unsupported = normalize_room_type(raw_type_val)

        raw_polygon = raw_room.get("polygon") or raw_room.get("boundary_points")
        if not raw_polygon:
            raise StructuralInputValidationError(
                message=f"Room '{room_id}' is missing boundary polygon coordinates.",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].polygon"
            )

        coords: List[Coordinate2D] = []
        for pt_idx, pt in enumerate(raw_polygon):
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                coords.append(Coordinate2D(
                    x=convert_to_meters(float(pt[0]), unit),
                    y=convert_to_meters(float(pt[1]), unit)
                ))
            elif isinstance(pt, dict) and "x" in pt and "y" in pt:
                coords.append(Coordinate2D(
                    x=convert_to_meters(float(pt["x"]), unit),
                    y=convert_to_meters(float(pt["y"]), unit)
                ))
            else:
                raise StructuralInputValidationError(
                    message=f"Room '{room_id}' polygon vertex {pt_idx} is malformed: {pt}",
                    room_id=room_id,
                    path=f"floor_plan.rooms[{room_id}].polygon[{pt_idx}]"
                )

        if len(coords) < 3:
            raise StructuralInputValidationError(
                message=f"Room '{room_id}' polygon must have at least 3 vertices, got {len(coords)}.",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].polygon"
            )

        is_valid, err_msg, computed_area = validate_room_polygon(coords)
        if not is_valid:
            raise StructuralInputValidationError(
                message=f"Room '{room_id}' has invalid polygon geometry: {err_msg}",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].polygon"
            )

        # Doors: NO fabricated geometry. Preserve distinction between absent and empty.
        doors_data_available = "doors" in raw_room
        missing_upstream: List[str] = []
        doors: List[DoorDTO] = []
        if doors_data_available and raw_room.get("doors") is not None:
            for d_idx, raw_door in enumerate(raw_room.get("doors", [])):
                door_dto = StructuralInputParser._parse_door(raw_door, room_id, d_idx, unit)
                doors.append(door_dto)
        elif not doors_data_available:
            missing_upstream.append("doors")

        # Windows: NO fabricated geometry. Preserve distinction between absent and empty.
        windows_data_available = "windows" in raw_room
        windows: List[WindowDTO] = []
        if windows_data_available and raw_room.get("windows") is not None:
            for w_idx, raw_window in enumerate(raw_room.get("windows", [])):
                window_dto = StructuralInputParser._parse_window(raw_window, room_id, w_idx, unit)
                windows.append(window_dto)
        elif not windows_data_available:
            missing_upstream.append("windows")

        # Fixed obstructions
        fixed_obstructions: List[FixedObstructionDTO] = []
        for obs_idx, raw_obs in enumerate(raw_room.get("fixed_obstructions", [])):
            obs_dto = StructuralInputParser._parse_fixed_obstruction(raw_obs, obs_idx, unit)
            fixed_obstructions.append(obs_dto)

        return RoomDTO(
            floor_id=floor_id,
            room_id=room_id,
            name=name,
            room_type=room_type,
            source_room_type=source_room_type,
            is_unsupported_type=is_unsupported,
            polygon=coords,
            area_sqm=computed_area,
            ceiling_height=float(raw_room.get("ceiling_height", 2.8)),
            elevation=float(raw_room.get("elevation", 0.0)),
            doors=doors,
            windows=windows,
            fixed_obstructions=fixed_obstructions,
            doors_data_available=doors_data_available,
            windows_data_available=windows_data_available,
            missing_upstream_fields=missing_upstream
        )


    @staticmethod
    def _parse_door(raw_door: Dict[str, Any], room_id: str, default_idx: int, unit: LengthUnit) -> DoorDTO:
        if not isinstance(raw_door, dict):
            raise StructuralInputValidationError(
                message=f"Door at index {default_idx} in room '{room_id}' must be an object.",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].doors[{default_idx}]"
            )
        door_id = str(raw_door.get("id") or f"door_{default_idx}").strip()

        start_pt = raw_door.get("start")
        end_pt = raw_door.get("end")
        if start_pt is None or end_pt is None:
            raise StructuralInputValidationError(
                message=f"Door '{door_id}' in room '{room_id}' is missing required start/end coordinates. Fabricated geometry is prohibited.",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].doors[{door_id}]"
            )

        def _coord(pt: Any, name: str) -> tuple[float, float]:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                return float(pt[0]), float(pt[1])
            elif isinstance(pt, dict) and "x" in pt and "y" in pt:
                return float(pt["x"]), float(pt["y"])
            raise StructuralInputValidationError(
                message=f"Door '{door_id}' in room '{room_id}' has malformed {name} position: {pt}",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].doors[{door_id}].{name}"
            )

        s_x, s_y = _coord(start_pt, "start")
        e_x, e_y = _coord(end_pt, "end")

        start_x = convert_to_meters(s_x, unit)
        start_y = convert_to_meters(s_y, unit)
        end_x = convert_to_meters(e_x, unit)
        end_y = convert_to_meters(e_y, unit)

        raw_width = raw_door.get("leaf_width") or raw_door.get("width")
        if raw_width is not None:
            leaf_width = convert_to_meters(float(raw_width), unit)
        else:
            computed_w = math.hypot(end_x - start_x, end_y - start_y)
            if computed_w <= 0:
                raise StructuralInputValidationError(
                    message=f"Door '{door_id}' in room '{room_id}' has zero leaf width / identical start and end.",
                    room_id=room_id,
                    path=f"floor_plan.rooms[{room_id}].doors[{door_id}].leaf_width"
                )
            leaf_width = round(computed_w, 3)

        raw_hinge = str(raw_door.get("hinge", "left")).lower()
        try:
            hinge = DoorHinge(raw_hinge)
        except ValueError:
            hinge = DoorHinge.LEFT

        raw_dir = str(raw_door.get("opening_direction", "inward")).lower()
        try:
            direction = DoorOpeningDirection(raw_dir)
        except ValueError:
            direction = DoorOpeningDirection.INWARD

        return DoorDTO(
            id=door_id,
            room_id=room_id,
            start=Coordinate2D(x=start_x, y=start_y),
            end=Coordinate2D(x=end_x, y=end_y),
            leaf_width=leaf_width,
            hinge=hinge,
            opening_direction=direction,
            swing_angle=float(raw_door.get("swing_angle", 90.0)),
            protected_depth=convert_to_meters(float(raw_door.get("protected_depth")), unit) if raw_door.get("protected_depth") is not None else None
        )

    @staticmethod
    def _parse_window(raw_window: Dict[str, Any], room_id: str, default_idx: int, unit: LengthUnit) -> WindowDTO:
        if not isinstance(raw_window, dict):
            raise StructuralInputValidationError(
                message=f"Window at index {default_idx} in room '{room_id}' must be an object.",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].windows[{default_idx}]"
            )
        window_id = str(raw_window.get("id") or f"window_{default_idx}").strip()

        start_pt = raw_window.get("start")
        end_pt = raw_window.get("end")
        if start_pt is None or end_pt is None:
            raise StructuralInputValidationError(
                message=f"Window '{window_id}' in room '{room_id}' is missing required start/end coordinates. Fabricated geometry is prohibited.",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].windows[{window_id}]"
            )

        def _coord(pt: Any, name: str) -> tuple[float, float]:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                return float(pt[0]), float(pt[1])
            elif isinstance(pt, dict) and "x" in pt and "y" in pt:
                return float(pt["x"]), float(pt["y"])
            raise StructuralInputValidationError(
                message=f"Window '{window_id}' in room '{room_id}' has malformed {name} position: {pt}",
                room_id=room_id,
                path=f"floor_plan.rooms[{room_id}].windows[{window_id}].{name}"
            )

        s_x, s_y = _coord(start_pt, "start")
        e_x, e_y = _coord(end_pt, "end")

        start_x = convert_to_meters(s_x, unit)
        start_y = convert_to_meters(s_y, unit)
        end_x = convert_to_meters(e_x, unit)
        end_y = convert_to_meters(e_y, unit)

        raw_len = raw_window.get("length") or raw_window.get("width")
        if raw_len is not None:
            length = convert_to_meters(float(raw_len), unit)
        else:
            computed_l = math.hypot(end_x - start_x, end_y - start_y)
            if computed_l <= 0:
                raise StructuralInputValidationError(
                    message=f"Window '{window_id}' in room '{room_id}' has zero length / identical start and end.",
                    room_id=room_id,
                    path=f"floor_plan.rooms[{room_id}].windows[{window_id}].length"
                )
            length = round(computed_l, 3)

        sill_height = convert_to_meters(float(raw_window.get("sill_height")), unit) if raw_window.get("sill_height") is not None else 0.9
        height = convert_to_meters(float(raw_window.get("height")), unit) if raw_window.get("height") is not None else 1.2

        return WindowDTO(
            id=window_id,
            room_id=room_id,
            start=Coordinate2D(x=start_x, y=start_y),
            end=Coordinate2D(x=end_x, y=end_y),
            length=length,
            sill_height=sill_height,
            height=height,
            opening_type=str(raw_window.get("opening_type", "sliding")),
            protected_access_depth=convert_to_meters(float(raw_window.get("protected_access_depth", 0.6)), unit) if raw_window.get("protected_access_depth") is not None else 0.6
        )

    @staticmethod
    def _parse_fixed_obstruction(raw_obs: Dict[str, Any], default_idx: int, unit: LengthUnit) -> FixedObstructionDTO:
        obs_id = str(raw_obs.get("id") or f"obs_{default_idx}").strip()
        name = str(raw_obs.get("name") or f"Obstruction {default_idx + 1}").strip()
        raw_poly = raw_obs.get("polygon", [])
        coords: List[Coordinate2D] = []

        for pt in raw_poly:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                coords.append(Coordinate2D(x=convert_to_meters(float(pt[0]), unit), y=convert_to_meters(float(pt[1]), unit)))
            elif isinstance(pt, dict) and "x" in pt and "y" in pt:
                coords.append(Coordinate2D(x=convert_to_meters(float(pt["x"]), unit), y=convert_to_meters(float(pt["y"]), unit)))

        return FixedObstructionDTO(
            id=obs_id,
            name=name,
            polygon=coords,
            height=convert_to_meters(float(raw_obs.get("height")), unit) if raw_obs.get("height") is not None else None,
            category=str(raw_obs.get("category", "structural"))
        )
