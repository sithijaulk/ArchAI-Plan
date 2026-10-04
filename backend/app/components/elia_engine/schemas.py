from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ELIAInputModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class LocationInput(ELIAInputModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = None

    @model_validator(mode="after")
    def coordinates_are_a_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class VehicleProfileInput(ELIAInputModel):
    vehicle_type: str = "custom"
    length: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    minimum_turning_radius: float | None = Field(default=None, gt=0)


class UtilityInput(ELIAInputModel):
    known: bool = False
    position: list[float] | dict[str, float] | None = None


class AccessRequirements(ELIAInputModel):
    road_side: str | None = None
    road_access_edge: int | None = Field(default=None, ge=0)
    preferred_gate_location: list[float] | None = None
    gate_type: str = "unspecified"
    gate_width: float | None = Field(default=None, gt=0)
    gate_count: int = Field(default=1, ge=1)
    entrance_priority: str | None = None
    garage_required: bool = False
    garage_capacity: int = Field(default=1, ge=1, le=3)
    preferred_garage_location: list[float] | None = None
    vehicle_count: int = Field(default=1, ge=1)
    vehicle_profiles: list[VehicleProfileInput] = Field(default_factory=list)
    driveway_required: bool = True
    preferred_driveway_width: float | None = Field(default=None, gt=0)
    driveway_style: str = "auto"
    driveway_surface: str | None = None
    turning_space_required: bool = True


class LandscapeRequirements(ELIAInputModel):
    garden_required: bool = False
    lawn_required: bool = False
    garden_seating_required: bool = False
    garden_table_set_required: bool = False
    preferred_garden_zone: str | None = None
    preferred_open_space_ratio: float | None = Field(default=None, ge=0, le=1)
    greenery_density: str = "medium"
    preferred_vegetation_categories: list[str] = Field(default_factory=list)
    vegetation_to_avoid: list[str] = Field(default_factory=list)
    shade_tree_preference: bool = False
    low_maintenance_preference: bool | None = None
    pedestrian_path_required: bool = False
    garden_path_required: bool = False
    boundary_wall_required: bool = False
    boundary_wall_type: str | None = None
    boundary_wall_height: float | None = Field(default=None, gt=0)


class VerticalGreeneryRequirements(ELIAInputModel):
    mode: Literal["automatic", "preferred", "disabled"] = "automatic"
    enabled: bool = True
    preferred_types: list[str] = Field(default_factory=list)


class LightingRequirements(ELIAInputModel):
    required: bool = False
    style: str = "minimal"
    zones: list[str] = Field(default_factory=list)
    preferred_spacing: float | None = Field(default=None, gt=0)


class ELIARequirements(ELIAInputModel):
    units: str = "m"
    design_style: str = "contemporary"
    greenery_level: str = "medium"
    landscape_priority: str = "balanced"
    vertical_greenery_enabled: bool = True
    location: LocationInput = Field(default_factory=LocationInput)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = None
    solar_analysis_date: str | None = None
    solar_analysis_time_range: list[str] | None = None
    include_live_solar: bool = False
    property_orientation: str | float | None = None
    north_angle: float | None = None
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


class ELIAResponse(BaseModel):
    project_id: str
    run_id: str
    status: Literal["completed", "infeasible"]
    outcome: Literal["valid", "infeasible"]
    exterior_landscape: dict[str, Any]
    master_json_updated: bool
