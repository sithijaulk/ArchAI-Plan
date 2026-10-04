from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class ELIAInputModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class LocationInput(ELIAInputModel):
    latitude: FiniteFloat | None = Field(default=None, ge=-90, le=90)
    longitude: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = None

    @model_validator(mode="after")
    def coordinates_are_a_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class VehicleProfileInput(ELIAInputModel):
    vehicle_type: str = "custom"
    length: FiniteFloat | None = Field(default=None, gt=0)
    width: FiniteFloat | None = Field(default=None, gt=0)
    minimum_turning_radius: FiniteFloat | None = Field(default=None, gt=0)


class UtilityInput(ELIAInputModel):
    known: bool = False
    position: list[FiniteFloat] | dict[str, FiniteFloat] | None = None

    @model_validator(mode="after")
    def validate_position_pair(self):
        if isinstance(self.position, list) and len(self.position) != 2:
            raise ValueError("Utility position must contain exactly x and y")
        if isinstance(self.position, dict) and not {"x", "y"} <= self.position.keys():
            raise ValueError("Utility position must contain x and y")
        return self


class AccessRequirements(ELIAInputModel):
    road_side: str | None = None
    road_access_edge: int | None = Field(default=None, ge=0)
    preferred_gate_location: list[FiniteFloat] | None = None
    gate_type: str = "unspecified"
    gate_width: FiniteFloat | None = Field(default=None, gt=0)
    gate_count: int = Field(default=1, ge=1)
    entrance_priority: str | None = None
    garage_required: bool = False
    garage_capacity: int = Field(default=1, ge=1, le=3)
    preferred_garage_location: list[FiniteFloat] | None = None
    vehicle_count: int = Field(default=1, ge=1)
    vehicle_profiles: list[VehicleProfileInput] = Field(default_factory=list)
    driveway_required: bool = True
    preferred_driveway_width: FiniteFloat | None = Field(default=None, gt=0)
    driveway_style: str = "auto"
    driveway_surface: str | None = None
    turning_space_required: bool = True

    @model_validator(mode="after")
    def validate_preferred_coordinate_pairs(self):
        for name in ("preferred_gate_location", "preferred_garage_location"):
            value = getattr(self, name)
            if value is not None and len(value) != 2:
                raise ValueError(f"{name} must contain exactly x and y")
        return self


class LandscapeRequirements(ELIAInputModel):
    garden_required: bool = False
    lawn_required: bool = False
    garden_seating_required: bool = False
    garden_table_set_required: bool = False
    preferred_garden_zone: str | None = None
    preferred_open_space_ratio: FiniteFloat | None = Field(default=None, ge=0, le=1)
    greenery_density: str = "medium"
    preferred_vegetation_categories: list[str] = Field(default_factory=list)
    vegetation_to_avoid: list[str] = Field(default_factory=list)
    shade_tree_preference: bool = False
    low_maintenance_preference: bool | None = None
    pedestrian_path_required: bool = False
    garden_path_required: bool = False
    boundary_wall_required: bool = False
    boundary_wall_type: str | None = None
    boundary_wall_height: FiniteFloat | None = Field(default=None, gt=0)


class VerticalGreeneryRequirements(ELIAInputModel):
    mode: Literal["automatic", "preferred", "disabled"] = "automatic"
    enabled: bool = True
    preferred_types: list[str] = Field(default_factory=list)


class LightingRequirements(ELIAInputModel):
    required: bool = False
    style: str = "minimal"
    zones: list[str] = Field(default_factory=list)
    preferred_spacing: FiniteFloat | None = Field(default=None, gt=0)


class ELIARequirements(ELIAInputModel):
    units: str = "m"
    design_style: str = "contemporary"
    greenery_level: str = "medium"
    landscape_priority: str = "balanced"
    vertical_greenery_enabled: bool = True
    location: LocationInput = Field(default_factory=LocationInput)
    latitude: FiniteFloat | None = Field(default=None, ge=-90, le=90)
    longitude: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = None
    solar_analysis_date: str | None = None
    solar_analysis_time_range: list[str] | None = None
    include_live_solar: bool = False
    property_orientation: str | float | None = None
    north_angle: FiniteFloat | None = None
    access: AccessRequirements = Field(default_factory=AccessRequirements)
    utilities: dict[str, UtilityInput] = Field(default_factory=dict)
    utility_relocation_allowed: bool = False
    landscape: LandscapeRequirements = Field(default_factory=LandscapeRequirements)
    vertical_greenery: VerticalGreeneryRequirements = Field(default_factory=VerticalGreeneryRequirements)
    lighting: LightingRequirements = Field(default_factory=LightingRequirements)
    additional_requirements: dict[str, Any] | str = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_location_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class ELIARequest(BaseModel):
    requirements: ELIARequirements = Field(default_factory=ELIARequirements)
    master_json: dict[str, Any] | None = None
    apply_to_project: bool = False
    generation_mode: Literal["trained_model", "baseline"] = "trained_model"
    source_revision: int | None = Field(default=None, ge=1)


class ExteriorFeatureResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    json_id: str = Field(min_length=1)
    type: str | None = None
    category: str | None = None
    position: list[FiniteFloat] | dict[str, FiniteFloat] | None = None
    polygon: list[list[FiniteFloat]] | None = None
    geometry: dict[str, Any] | None = None
    dimensions: dict[str, FiniteFloat] | None = None
    rotation_degrees: FiniteFloat | None = None
    units: str = "m"
    floor_id: str | None = None
    support_json_id: str | None = None

    @model_validator(mode="after")
    def validate_units_and_coordinates(self):
        if self.units != "m":
            raise ValueError("Exterior output units must be meters")
        if isinstance(self.position, list) and len(self.position) < 2:
            raise ValueError("Exterior position must contain x and y")
        if isinstance(self.position, dict) and not {"x", "y"} <= self.position.keys():
            raise ValueError("Exterior position must contain x and y")
        if self.dimensions and any(value <= 0 for value in self.dimensions.values()):
            raise ValueError("Exterior dimensions must be positive")
        if self.position is None and self.polygon is None and self.geometry is None:
            validation = self.model_extra.get("validation", {}) if self.model_extra else {}
            if not isinstance(validation, Mapping) or validation.get("valid") is not False:
                raise ValueError("Exterior feature requires position or geometry unless it is marked unplaced")
        return self


class ExteriorAccessResponse(ELIAInputModel):
    gate: ExteriorFeatureResponse | None = None
    gates: list[ExteriorFeatureResponse] = Field(default_factory=list)
    garage: ExteriorFeatureResponse | None = None
    driveway: ExteriorFeatureResponse | None = None


class ExteriorLightingResponse(ELIAInputModel):
    nodes: list[ExteriorFeatureResponse] = Field(default_factory=list)


class ExteriorVerticalResponse(ELIAInputModel):
    elements: list[ExteriorFeatureResponse] = Field(default_factory=list)


class ExteriorValidationResponse(ELIAInputModel):
    valid: bool
    violations: list[str] = Field(default_factory=list)
    checks_passed: int = Field(default=0, ge=0)
    checks_total: int = Field(default=0, ge=0)
    constraint_satisfaction_rate: FiniteFloat = Field(default=0.0, ge=0, le=1)


class ExteriorLandscapeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    coordinate_reference: str = Field(min_length=1)
    access: ExteriorAccessResponse
    site_analysis: dict[str, Any]
    utility_safety: dict[str, Any]
    environment: dict[str, Any]
    vegetation_nodes: list[ExteriorFeatureResponse] = Field(default_factory=list)
    vertical_greenery: ExteriorVerticalResponse = Field(default_factory=ExteriorVerticalResponse)
    outdoor_lighting: ExteriorLightingResponse = Field(default_factory=ExteriorLightingResponse)
    outdoor_elements: list[ExteriorFeatureResponse] = Field(default_factory=list)
    validation_summary: ExteriorValidationResponse
    metrics: dict[str, Any]


class ELIAResponse(BaseModel):
    project_id: str
    run_id: str
    status: Literal["completed", "infeasible"]
    outcome: Literal["valid", "infeasible"]
    exterior_landscape: ExteriorLandscapeResponse
    master_json_updated: bool
    generation_mode: Literal["trained_model", "baseline"]
