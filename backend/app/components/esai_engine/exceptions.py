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


class GeometryStalenessError(EsaiException):
    """Raised when attempting to save a design generated against stale geometry."""

    def __init__(self, message: str, project_id: str, generated_fingerprint: Optional[str] = None, current_fingerprint: Optional[str] = None):
        super().__init__(
            message=message,
            code="GEOMETRY_STALENESS_CONFLICT",
            details={
                "project_id": project_id,
                "generated_fingerprint": generated_fingerprint,
                "current_fingerprint": current_fingerprint,
            }
        )


class PreferenceStalenessError(EsaiException):
    """Raised when attempting to save a design generated against stale client preferences."""

    def __init__(self, message: str, project_id: str, room_id: Optional[str] = None, generated_rev: Optional[int] = None, current_rev: Optional[int] = None):
        super().__init__(
            message=message,
            code="PREFERENCE_STALENESS_CONFLICT",
            details={
                "project_id": project_id,
                "room_id": room_id,
                "generated_preference_revision": generated_rev,
                "current_preference_revision": current_rev,
            }
        )


class DesignRevisionConflictError(EsaiException):
    """Raised when concurrent saves or edits conflict with expected design revision."""

    def __init__(self, message: str, project_id: str, expected_rev: Optional[int] = None, current_rev: Optional[int] = None):
        super().__init__(
            message=message,
            code="DESIGN_REVISION_CONFLICT",
            details={
                "project_id": project_id,
                "expected_design_revision": expected_rev,
                "current_design_revision": current_rev,
            }
        )


class InvalidDesignSaveError(EsaiException):
    """Raised when attempting to save an invalid, unvalidated or infeasible design as valid."""

    def __init__(self, message: str, room_id: Optional[str] = None, violations: Optional[list] = None):
        super().__init__(
            message=message,
            code="INVALID_DESIGN_SAVE_ERROR",
            details={
                "room_id": room_id,
                "violations": violations or [],
            }
        )


class AlternativeNotFoundError(EsaiException):
    """Raised when a requested alternative index or ID is not found in the room's generated alternatives."""

    def __init__(self, message: str, room_id: str, alternative_id: str):
        super().__init__(
            message=message,
            code="ALTERNATIVE_NOT_FOUND",
            details={
                "room_id": room_id,
                "alternative_id": alternative_id,
            }
        )
