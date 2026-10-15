"""
Structural Input Parser
Extracts, validates, and normalizes structural geometry (floors, rooms, doors, windows, obstructions)
from the Centralized Master JSON.
Ensures immutability of the incoming Master JSON.
"""
from copy import deepcopy
from typing import Any, Dict, List, Optional

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
    convert_to_meters,
)
from .exceptions import StructuralInputValidationError
from .geometry import validate_room_polygon


class StructuralInputParser:
    """Parses structural geometry from Master JSON without modifying the original document."""

    @staticmethod
    def parse(master_json: Dict[str, Any]) -> StructuralInputDTO:
        if not isinstance(master_json, dict):
            raise StructuralInputValidationError("Master JSON must be a dictionary.")

        # Deepcopy to guarantee immutability
        doc = deepcopy(master_json)

        project_id = str(doc.get("project_id", "")).strip()
        project_name = str(doc.get("project_name", "")).strip()

        # Detect source unit
        raw_unit = doc.get("unit") or doc.get("floor_plan", {}).get("unit", "m")
        try:
            unit = LengthUnit(str(raw_unit).lower())
        except ValueError:
            unit = LengthUnit.METERS

        floor_plan_data = doc.get("floor_plan") or {}

        # Support both structures: floor_plan.floors array or direct floor_plan with rooms
        floors_list: List[FloorDTO] = []

        if isinstance(floor_plan_data, dict) and "floors" in floor_plan_data:
            raw_floors = floor_plan_data.get("floors", [])
            for f_idx, raw_floor in enumerate(raw_floors):
                floor_dto = StructuralInputParser._parse_floor(raw_floor, f_idx, unit)
                floors_list.append(floor_dto)
        elif isinstance(floor_plan_data, dict) and "rooms" in floor_plan_data:
            # Single floor default
            floor_dto = StructuralInputParser._parse_floor(
                {"floor_id": "floor_0", "floor_name": "Ground Floor", "rooms": floor_plan_data.get("rooms", [])},
                0,
                unit
            )
            floors_list.append(floor_dto)

        return StructuralInputDTO(
            project_id=project_id,
            project_name=project_name,
            unit=unit,
            floors=floors_list
        )

    @staticmethod
    def _parse_floor(raw_floor: Dict[str, Any], default_index: int, unit: LengthUnit) -> FloorDTO:
        floor_id = str(raw_floor.get("floor_id") or f"floor_{default_index}")
        floor_name = str(raw_floor.get("floor_name") or f"Floor {default_index + 1}")
        elevation = float(raw_floor.get("elevation", 0.0))

        raw_rooms = raw_floor.get("rooms", [])
        rooms: List[RoomDTO] = []

        for r_idx, raw_room in enumerate(raw_rooms):
            room_dto = StructuralInputParser._parse_room(raw_room, floor_id, r_idx, unit)
            rooms.append(room_dto)

        return FloorDTO(
            floor_id=floor_id,
            floor_name=floor_name,
            level_index=default_index,
            elevation=elevation,
            rooms=rooms
        )

    @staticmethod
    def _parse_room(raw_room: Dict[str, Any], floor_id: str, default_index: int, unit: LengthUnit) -> RoomDTO:
        room_id = str(raw_room.get("room_id") or f"room_{default_index}")
        name = str(raw_room.get("name") or raw_room.get("room_name") or f"Room {default_index + 1}")

        # Room Type mapping
        raw_type = str(raw_room.get("room_type") or raw_room.get("type", "other")).lower().replace(" ", "_")
        try:
            room_type = RoomType(raw_type)
        except ValueError:
            room_type = RoomType.OTHER

        # Coordinates parsing: support [[x,y],...] or [{"x":x,"y":y},...]
        raw_polygon = raw_room.get("polygon") or raw_room.get("boundary_points") or []
        coords: List[Coordinate2D] = []

        for pt in raw_polygon:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                x = convert_to_meters(float(pt[0]), unit)
                y = convert_to_meters(float(pt[1]), unit)
                coords.append(Coordinate2D(x=x, y=y))
            elif isinstance(pt, dict) and "x" in pt and "y" in pt:
                x = convert_to_meters(float(pt["x"]), unit)
                y = convert_to_meters(float(pt["y"]), unit)
                coords.append(Coordinate2D(x=x, y=y))

        # Validate polygon geometry
        is_valid, err_msg, computed_area = validate_room_polygon(coords)
        if not is_valid:
            raise StructuralInputValidationError(
                message=f"Room '{room_id}' has invalid polygon geometry: {err_msg}",
                room_id=room_id,
                path=f"floor_plan.rooms[{default_index}].polygon"
            )

        # Doors
        doors: List[DoorDTO] = []
        for d_idx, raw_door in enumerate(raw_room.get("doors", [])):
            door_dto = StructuralInputParser._parse_door(raw_door, room_id, d_idx, unit)
            doors.append(door_dto)

        # Windows
        windows: List[WindowDTO] = []
        for w_idx, raw_window in enumerate(raw_room.get("windows", [])):
            window_dto = StructuralInputParser._parse_window(raw_window, room_id, w_idx, unit)
            windows.append(window_dto)

        # Fixed obstructions (columns, built-in features)
        fixed_obstructions: List[FixedObstructionDTO] = []
        for obs_idx, raw_obs in enumerate(raw_room.get("fixed_obstructions", [])):
            obs_dto = StructuralInputParser._parse_fixed_obstruction(raw_obs, obs_idx, unit)
            fixed_obstructions.append(obs_dto)

        return RoomDTO(
            floor_id=floor_id,
            room_id=room_id,
            name=name,
            room_type=room_type,
            polygon=coords,
            area_sqm=computed_area,
            ceiling_height=float(raw_room.get("ceiling_height", 2.8)),
            elevation=float(raw_room.get("elevation", 0.0)),
            doors=doors,
            windows=windows,
            fixed_obstructions=fixed_obstructions
        )

    @staticmethod
    def _parse_door(raw_door: Dict[str, Any], room_id: str, default_idx: int, unit: LengthUnit) -> DoorDTO:
        door_id = str(raw_door.get("id") or f"door_{default_idx}")
        start_pt = raw_door.get("start", [0.0, 0.0])
        end_pt = raw_door.get("end", [0.9, 0.0])

        start_x = convert_to_meters(start_pt[0] if isinstance(start_pt, (list, tuple)) else start_pt.get("x", 0.0), unit)
        start_y = convert_to_meters(start_pt[1] if isinstance(start_pt, (list, tuple)) else start_pt.get("y", 0.0), unit)
        end_x = convert_to_meters(end_pt[0] if isinstance(end_pt, (list, tuple)) else end_pt.get("x", 0.0), unit)
        end_y = convert_to_meters(end_pt[1] if isinstance(end_pt, (list, tuple)) else end_pt.get("y", 0.0), unit)

        raw_width = raw_door.get("leaf_width") or raw_door.get("width", 0.9)
        leaf_width = convert_to_meters(float(raw_width), unit)

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
            protected_depth=convert_to_meters(float(raw_door.get("protected_depth")), unit) if raw_door.get("protected_depth") else None
        )

    @staticmethod
    def _parse_window(raw_window: Dict[str, Any], room_id: str, default_idx: int, unit: LengthUnit) -> WindowDTO:
        window_id = str(raw_window.get("id") or f"window_{default_idx}")
        start_pt = raw_window.get("start", [0.0, 0.0])
        end_pt = raw_window.get("end", [1.2, 0.0])

        start_x = convert_to_meters(start_pt[0] if isinstance(start_pt, (list, tuple)) else start_pt.get("x", 0.0), unit)
        start_y = convert_to_meters(start_pt[1] if isinstance(start_pt, (list, tuple)) else start_pt.get("y", 0.0), unit)
        end_x = convert_to_meters(end_pt[0] if isinstance(end_pt, (list, tuple)) else end_pt.get("x", 0.0), unit)
        end_y = convert_to_meters(end_pt[1] if isinstance(end_pt, (list, tuple)) else end_pt.get("y", 0.0), unit)

        raw_len = raw_window.get("length") or raw_window.get("width", 1.2)
        length = convert_to_meters(float(raw_len), unit)

        sill_height = convert_to_meters(float(raw_window.get("sill_height", 0.9)), unit) if raw_window.get("sill_height") is not None else 0.9
        height = convert_to_meters(float(raw_window.get("height", 1.2)), unit) if raw_window.get("height") is not None else 1.2

        return WindowDTO(
            id=window_id,
            room_id=room_id,
            start=Coordinate2D(x=start_x, y=start_y),
            end=Coordinate2D(x=end_x, y=end_y),
            length=length,
            sill_height=sill_height,
            height=height,
            opening_type=str(raw_window.get("opening_type", "sliding")),
            protected_access_depth=convert_to_meters(float(raw_window.get("protected_access_depth", 0.6)), unit)
        )

    @staticmethod
    def _parse_fixed_obstruction(raw_obs: Dict[str, Any], default_idx: int, unit: LengthUnit) -> FixedObstructionDTO:
        obs_id = str(raw_obs.get("id") or f"obs_{default_idx}")
        name = str(raw_obs.get("name") or f"Obstruction {default_idx + 1}")
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
            height=convert_to_meters(float(raw_obs.get("height")), unit) if raw_obs.get("height") else None,
            category=str(raw_obs.get("category", "structural"))
        )
