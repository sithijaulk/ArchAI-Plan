"""
Normalizer Module
Converts and maps varied legacy or loosely structured floor/room data
into canonical ESAI internal data representations.
"""
from typing import Dict, Any, List
from .contracts import (
    StructuralInputDTO,
    RoomDTO,
    FloorDTO,
    LengthUnit,
    RoomType
)
from .parser import StructuralInputParser


class SpatialNormalizer:
    """Normalizes project geometry into canonical metric representations."""

    @staticmethod
    def normalize_project_data(master_json: Dict[str, Any]) -> StructuralInputDTO:
        """Parses and normalizes Master JSON into canonical meters representation."""
        return StructuralInputParser.parse(master_json)

    @staticmethod
    def find_all_floors(structural_input: StructuralInputDTO) -> List[FloorDTO]:
        return structural_input.floors

    @staticmethod
    def find_all_rooms(structural_input: StructuralInputDTO) -> List[RoomDTO]:
        all_rooms: List[RoomDTO] = []
        for fl in structural_input.floors:
            all_rooms.extend(fl.rooms)
        return all_rooms

    @staticmethod
    def find_room_by_id(structural_input: StructuralInputDTO, room_id: str) -> RoomDTO | None:
        for fl in structural_input.floors:
            for rm in fl.rooms:
                if rm.room_id == room_id:
                    return rm
        return None

    @staticmethod
    def find_rooms_by_type(structural_input: StructuralInputDTO, room_type: RoomType) -> List[RoomDTO]:
        return [
            rm for fl in structural_input.floors
            for rm in fl.rooms
            if rm.room_type == room_type
        ]
