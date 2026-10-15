"""
ESAI Serializer Module
Converts domain DTOs to serializable JSON structures and provides
canonical coordinate export for frontend 2D / 3D rendering.
"""
from typing import Dict, Any, List
from .contracts import (
    StructuralInputDTO,
    RoomDTO,
    FloorDTO,
    ValidationResultDTO,
    RoomRequirementsDTO,
)


class EsaiSerializer:
    """Serializes ESAI models to standardized dictionaries and JSON-compatible formats."""

    @staticmethod
    def serialize_structural_input(structural_input: StructuralInputDTO) -> Dict[str, Any]:
        return structural_input.model_dump()

    @staticmethod
    def serialize_room(room: RoomDTO) -> Dict[str, Any]:
        return room.model_dump()

    @staticmethod
    def serialize_validation_result(result: ValidationResultDTO) -> Dict[str, Any]:
        return result.model_dump()

    @staticmethod
    def serialize_requirements(requirements: RoomRequirementsDTO) -> Dict[str, Any]:
        return requirements.model_dump()
