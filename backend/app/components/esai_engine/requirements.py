"""
Requirements Module
Handles serialization, validation, and database abstraction for client requirements.
"""
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from .contracts import (
    RoomRequirementsDTO,
    ProjectPreferencesDTO,
    FurnitureRequirementItem
)
from .exceptions import RequirementValidationError


class ClientRequirementsHandler:
    """Processes, deserializes, and verifies client requirement structures."""

    @staticmethod
    def parse_room_requirements(data: Dict[str, Any]) -> RoomRequirementsDTO:
        try:
            return RoomRequirementsDTO(**data)
        except ValidationError as e:
            raise RequirementValidationError(
                message=f"Invalid room requirements payload: {str(e)}",
                details={"errors": e.errors()}
            )

    @staticmethod
    def parse_project_preferences(data: Dict[str, Any]) -> ProjectPreferencesDTO:
        try:
            return ProjectPreferencesDTO(**data)
        except ValidationError as e:
            raise RequirementValidationError(
                message=f"Invalid project preferences payload: {str(e)}",
                details={"errors": e.errors()}
            )
