"""
ESAI Exception Classes
Controlled error types for structural input, client requirements, standards, and persistence.
"""
from typing import Any, Optional


class EsaiException(Exception):
    """Base exception for all ESAI-Engine operations."""

    def __init__(self, message: str, code: str = "ESAI_ERROR", details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class StructuralInputValidationError(EsaiException):
    """Raised when structural geometry or floor plan in Master JSON is invalid or incomplete."""

    def __init__(self, message: str, room_id: Optional[str] = None, path: str = "floor_plan", details: Optional[dict[str, Any]] = None):
        merged_details = details or {}
        if room_id:
            merged_details["room_id"] = room_id
        merged_details["path"] = path
        super().__init__(message=message, code="STRUCTURAL_INPUT_VALIDATION_ERROR", details=merged_details)


class RequirementValidationError(EsaiException):
    """Raised when client furniture or room requirements fail catalog/ergonomic constraints."""

    def __init__(self, message: str, room_id: Optional[str] = None, asset_id: Optional[str] = None, details: Optional[dict[str, Any]] = None):
        merged_details = details or {}
        if room_id:
            merged_details["room_id"] = room_id
        if asset_id:
            merged_details["asset_id"] = asset_id
        super().__init__(message=message, code="REQUIREMENT_VALIDATION_ERROR", details=merged_details)


class CatalogItemNotFoundError(EsaiException):
    """Raised when a requested catalog ID is not found in the furniture catalog."""

    def __init__(self, catalog_id: str):
        super().__init__(
            message=f"Furniture catalog asset '{catalog_id}' was not found in catalog repository.",
            code="CATALOG_ITEM_NOT_FOUND",
            details={"catalog_id": catalog_id}
        )


class NeufertStandardRuleNotFoundError(EsaiException):
    """Raised when an ergonomic rule ID is referenced but does not exist in the standards repository."""

    def __init__(self, rule_id: str):
        super().__init__(
            message=f"Ergonomic standard rule '{rule_id}' was not found.",
            code="STANDARD_RULE_NOT_FOUND",
            details={"rule_id": rule_id}
        )


class ProjectAccessDeniedError(EsaiException):
    """Raised when user is not authorized to access or mutate this project."""

    def __init__(self, project_id: str):
        super().__init__(
            message=f"Access denied for project '{project_id}'.",
            code="PROJECT_ACCESS_DENIED",
            details={"project_id": project_id}
        )
