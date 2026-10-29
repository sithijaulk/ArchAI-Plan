from typing import Any, List, Optional, Dict
from pydantic import BaseModel, Field


class ElementCounts(BaseModel):
    rooms: int = 0
    structural_elements: int = 0
    walls: int = 0
    doors: int = 0
    windows: int = 0


class VastuReadinessCheck(BaseModel):
    ready: bool
    reason: Optional[str] = None


class VastuReadiness(BaseModel):
    status: str = Field(..., description="READY, PARTIALLY_READY, or NOT_READY")
    padavinyasa_9x9: VastuReadinessCheck
    brahmasthan: VastuReadinessCheck
    entrance_32_pada: VastuReadinessCheck
    directional_room_placement: VastuReadinessCheck


class SpatialSummary(BaseModel):
    room_count: int
    rooms: List[Dict[str, Any]]
    structural_elements_count: int
    walls_count: int = 0
    doors_count: int = 0
    windows_count: int = 0
    orientation: str
    road_facing: str
    area_sqft: Optional[float] = None
    boundary_points_count: int = 0
    bounding_box: Optional[Dict[str, float]] = None


class ValidationResult(BaseModel):
    status: str = Field(..., description="VALID, VALID_WITH_WARNINGS, INVALID, or INSUFFICIENT_DATA")
    is_valid: bool
    can_rectify: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    summary: str
    element_counts: ElementCounts
    vastu_readiness: VastuReadiness
    spatial_summary: SpatialSummary
