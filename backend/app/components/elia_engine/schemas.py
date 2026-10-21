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
    length_m: FiniteFloat | None = Field(default=None, gt=0)
    width: FiniteFloat | None = Field(default=None, gt=0)
    width_m: FiniteFloat | None = Field(default=None, gt=0)
    minimum_turning_radius: FiniteFloat | None = Field(default=None, gt=0)
    minimum_turning_radius_m: FiniteFloat | None = Field(default=None, gt=0)


class UtilityInput(ELIAInputModel):
    known: bool = False
    position: list[FiniteFloat] | dict[str, FiniteFloat] | None = None
    position_m: list[FiniteFloat] | dict[str, FiniteFloat] | None = None

    @model_validator(mode="after")
    def validate_position_pair(self):
        for attr in ("position", "position_m"):
            pos = getattr(self, attr)
            if isinstance(pos, list) and len(pos) != 2:
                raise ValueError(f"Utility {attr} must contain exactly x and y")
            if isinstance(pos, dict) and not {"x", "y"} <= pos.keys():
                raise ValueError(f"Utility {attr} must contain x and y")
        return self


class AccessRequirements(ELIAInputModel):
    road_side: str | None = None
    road_access_edge: int | None = Field(default=None, ge=0)
    preferred_gate_location: list[FiniteFloat] | None = None
    preferred_gate_location_m: list[FiniteFloat] | None = None
    gate_type: str = "unspecified"
    gate_width: FiniteFloat | None = Field(default=None, gt=0)
    gate_width_m: FiniteFloat | None = Field(default=None, gt=0)
    gate_count: int = Field(default=1, ge=1)
    entrance_priority: str | None = None
    parking_required: bool = True
    parking_type: str = "no_preference"
    garage_required: bool = False
    garage_capacity: int = Field(default=1, ge=1, le=3)
    preferred_garage_location: list[FiniteFloat] | None = None
    preferred_garage_location_m: list[FiniteFloat] | None = None
    vehicle_count: int = Field(default=1, ge=0)
    vehicle_profiles: list[VehicleProfileInput] = Field(default_factory=list)
    driveway_required: bool = True
    preferred_driveway_width: FiniteFloat | None = Field(default=None, gt=0)
    preferred_driveway_width_m: FiniteFloat | None = Field(default=None, gt=0)
    driveway_style: str = "auto"
    driveway_surface: str | None = None
    walking_path_surface: str | None = None
    gate_required: bool = True
    gate_opening_mechanism: str = "unspecified"
    gate_style: str = "unspecified"
    turning_space_required: bool = True

    @model_validator(mode="before")
    @classmethod
    def validate_strict_types(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("vehicle_count", "garage_capacity", "gate_count", "road_access_edge"):
                val = data.get(field_name)
                if isinstance(val, bool):
                    raise ValueError(f"{field_name} must be an integer, not a boolean")
            # Contradictions
            veh_count = data.get("vehicle_count")
            garage_req = data.get("garage_required")
            parking_req = data.get("parking_required")
            if parking_req is False and garage_req is True:
                raise ValueError("ELIA_CONTRADICTORY_REQUIREMENTS: Cannot request a garage when parking_required is explicitly false.")
            if veh_count == 0 and garage_req is True:
                raise ValueError("ELIA_CONTRADICTORY_REQUIREMENTS: Cannot request a garage when vehicle_count is 0.")
        return data

    @model_validator(mode="after")
    def validate_preferred_coordinate_pairs(self):
        for name in ("preferred_gate_location", "preferred_gate_location_m",
                     "preferred_garage_location", "preferred_garage_location_m"):
            value = getattr(self, name)
            if value is not None and len(value) != 2:
                raise ValueError(f"{name} must contain exactly x and y")
        return self


FeasibilityStatus = Literal["feasible", "infeasible", "review_required", "evidence_missing", "not_applicable", "unsupported", "search_exhausted", "search_inconclusive", "provider_unavailable"]


class PlantAlternativeProposal(BaseModel):
    model_config = ConfigDict(extra="allow")

    proposal_id: str
    original_request: str
    reason: str
    alternative_plant_id: str
    alternative_display_name: str
    alternative_scientific_name: str | None = None
    alternative_category: str
    proposed_placement_type: str
    proposed_surface_id: str | None = None
    quantity: int = 1
    remaining_evidence: list[str] = Field(default_factory=list)
    suitability_explanation: str
    source_revision: int | None = None
    catalogue_version: str = "2.1"
    status: Literal["proposed", "accepted", "rejected"] = "proposed"


class AcceptedPlantAlternative(BaseModel):
    model_config = ConfigDict(extra="allow")

    original_request: str
    alternative_plant_id: str
    alternative_display_name: str
    placement_type: str = "ground"
    surface_id: str | None = None
    quantity: int = 1
    source_revision: int | None = None
    catalogue_version: str = "2.1"
    acceptance_status: Literal["accepted", "rejected", "unresolved"] = "accepted"


class PlantAlternativeAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    proposal_id: str | None = None
    original_request: str
    alternative_plant_id: str
    placement_type: str = "ground"
    surface_id: str | None = None
    quantity: int = 1
    decision: Literal["accept", "reject", "unresolved"] = "accept"
    catalogue_version: str = "2.1"


class PlantSuitabilityAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    plant_id: str
    display_name: str
    scientific_name: str | None = None
    placement_type: str = "ground"
    surface_id: str | None = None
    overall_status: FeasibilityStatus
    plant_suitability: FeasibilityStatus
    spatial_fit: FeasibilityStatus
    surface_eligibility: FeasibilityStatus
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str
    missing_evidence: list[str] = Field(default_factory=list)
    applicable_rule_ids: list[str] = Field(default_factory=list)
    suggested_alternatives: list[PlantAlternativeProposal] = Field(default_factory=list)
    source_revision: int | None = None
    catalogue_version: str = "2.1"


class PlantSuitabilityRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    plant_id: str
    placement_type: str = "ground"
    surface_id: str | None = None
    sunlight_score: float | None = None
    climate_zone: str | None = None


class PlantSuitabilityResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    assessment: PlantSuitabilityAssessment
    alternatives: list[PlantAlternativeProposal] = Field(default_factory=list)


class PlantCatalogueResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    catalogue_version: str
    total_entries: int
    entries: list[dict[str, Any]]
    sources: dict[str, Any]


class LandscapeRequirements(ELIAInputModel):
    garden_required: bool = False
    lawn_required: bool = False
    garden_ground_finish: str | None = None
    garden_seating_required: bool = False
    garden_seating_count: int | None = Field(default=None, ge=0)
    garden_table_set_required: bool = False
    garden_table_set_count: int | None = Field(default=None, ge=0)
    preferred_garden_zone: str | None = None
    preferred_open_space_ratio: FiniteFloat | None = Field(default=None, ge=0, le=1)
    greenery_density: str = "medium"
    trees_required: bool = True
    tree_quantity: int | None = Field(default=None, ge=0)
    compact_trees_preference: bool = False
    shrubs_required: bool = False
    shrubs_quantity: int | None = Field(default=None, ge=0)
    flower_beds_required: bool = False
    ground_planters_required: bool = False
    ground_planters_count: int | None = Field(default=None, ge=0)
    preferred_vegetation_categories: list[str] = Field(default_factory=list)
    vegetation_to_avoid: list[str] = Field(default_factory=list)
    shade_tree_preference: bool = False
    low_maintenance_preference: bool | None = None
    maintenance_preference: Literal["low", "medium", "high", "no_preference", "unknown"] | None = None
    water_availability: Literal["limited", "regular", "irrigation_available", "unknown"] | None = None
    preferred_plant_ids: list[str] = Field(default_factory=list)
    plant_ids_to_avoid: list[str] = Field(default_factory=list)
    accepted_plant_alternatives: list[AcceptedPlantAlternative] = Field(default_factory=list)
    rejected_plant_alternatives: list[str] = Field(default_factory=list)
    climate_zone: str | None = None
    site_exposure: str | None = None
    pedestrian_path_required: bool = False
    garden_path_required: bool = False
    boundary_wall_required: bool = False
    boundary_wall_type: str | None = None
    boundary_wall_height: FiniteFloat | None = Field(default=None, gt=0)
    boundary_wall_height_m: FiniteFloat | None = Field(default=None, gt=0)

    @model_validator(mode="before")
    @classmethod
    def strip_obsolete_financials_and_validate_strict(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = data.copy()
            data.pop("budget_limit_lkr", None)
            data.pop("budget_preference", None)
            data.pop("budget_estimate", None)
            data.pop("budget_assessment", None)
            for field_name in (
                "tree_quantity",
                "shrubs_quantity",
                "ground_planters_count",
                "garden_seating_count",
                "garden_table_set_count",
            ):
                val = data.get(field_name)
                if isinstance(val, bool):
                    raise ValueError(f"{field_name} must be an integer, not a boolean")
        return data


class VerticalGreeneryRequirements(ELIAInputModel):
    mode: Literal["automatic", "preferred", "disabled"] = "automatic"
    enabled: bool = True
    preferred_types: list[str] = Field(default_factory=list)
    wall_climbing_plants: bool = False
    wall_mounted_greenery: bool = False
    hanging_trailing_greenery: bool = False
    accept_vertical_alternatives: bool = False


class BalconyRequirements(ELIAInputModel):
    planting_required: bool = False
    potted_plants: bool = False
    hanging_plants: bool = False
    seating_required: bool = False
    preferred_plant_ids: list[str] = Field(default_factory=list)
    target_balcony_ids: list[str] = Field(default_factory=list)


class TerraceRequirements(ELIAInputModel):
    planting_required: bool = False
    planters_required: bool = False
    seating_required: bool = False
    tables_required: bool = False
    target_terrace_ids: list[str] = Field(default_factory=list)


class LightingRequirements(ELIAInputModel):
    required: bool = False
    style: str = "minimal"
    zones: list[str] = Field(default_factory=list)
    preferred_spacing: FiniteFloat | None = Field(default=None, gt=0)
    preferred_spacing_m: FiniteFloat | None = Field(default=None, gt=0)
    desired_fixture_count: int | None = Field(default=None, ge=0)
    garden_lighting: bool = False
    pathway_lighting: bool = False
    seating_lighting: bool = False
    wall_lighting: bool = False

    @model_validator(mode="before")
    @classmethod
    def validate_strict_lighting(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("desired_fixture_count")
            if isinstance(val, bool):
                raise ValueError("desired_fixture_count must be an integer, not a boolean")
        return data


class WaterFeatureRequirements(ELIAInputModel):
    well_required: bool = False
    garden_taps_required: bool = False
    garden_taps_count: int | None = Field(default=None, ge=0)
    pond_required: bool = False
    swimming_pool_required: bool = False
    septic_tank_required: bool = False

    @model_validator(mode="before")
    @classmethod
    def validate_strict_water(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("garden_taps_count")
            if isinstance(val, bool):
                raise ValueError("garden_taps_count must be an integer, not a boolean")
        return data


class SolarRequirements(ELIAInputModel):
    panels_required: bool = False
    preferred_roof_surface: str = "auto"
    placement_priority: str = "balanced"
    include_live_solar: bool = False


class ELIARequirements(ELIAInputModel):
    units: str = "m"
    design_style: str = "contemporary"
    greenery_level: str = "medium"
    landscape_priority: str = "balanced"
    vertical_greenery_enabled: bool = True
    maintenance_preference: Literal["low", "medium", "high", "no_preference", "unknown"] | None = None
    water_availability: Literal["limited", "regular", "irrigation_available", "unknown"] | None = None
    preferred_plant_ids: list[str] = Field(default_factory=list)
    plant_ids_to_avoid: list[str] = Field(default_factory=list)
    accepted_plant_alternatives: list[AcceptedPlantAlternative] = Field(default_factory=list)
    rejected_plant_alternatives: list[str] = Field(default_factory=list)
    climate_zone: str | None = None
    site_exposure: str | None = None
    locked_features: list[dict[str, Any]] = Field(default_factory=list)
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
    balconies: BalconyRequirements = Field(default_factory=BalconyRequirements)
    terrace: TerraceRequirements = Field(default_factory=TerraceRequirements)
    lighting: LightingRequirements = Field(default_factory=LightingRequirements)
    water_features: WaterFeatureRequirements = Field(default_factory=WaterFeatureRequirements)
    solar: SolarRequirements = Field(default_factory=SolarRequirements)
    additional_requirements: dict[str, Any] | str = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def strip_internal_markers(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = data.copy()
            data.pop("normalized_units", None)
            data.pop("_elia_internal_normalized", None)
            data.pop("budget_limit_lkr", None)
            data.pop("budget_preference", None)
            data.pop("budget_estimate", None)
            data.pop("budget_assessment", None)
            # Sync include_live_solar between root and solar
            if "solar" in data and isinstance(data["solar"], dict):
                if "include_live_solar" in data["solar"] and "include_live_solar" not in data:
                    data["include_live_solar"] = data["solar"]["include_live_solar"]
                elif "include_live_solar" in data and "include_live_solar" not in data["solar"]:
                    data["solar"]["include_live_solar"] = data["include_live_solar"]
        return data

    @model_validator(mode="after")
    def validate_location_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class ELIARequest(BaseModel):
    requirements: ELIARequirements = Field(default_factory=ELIARequirements)
    master_json: dict[str, Any] | None = None
    apply_to_project: bool = False
    generation_mode: Literal["baseline", "rule_based_geometric", "trained_model"] = "baseline"
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

    @model_validator(mode="before")
    @classmethod
    def strip_obsolete_financials(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = data.copy()
            obsolete_keys = [k for k in data if any(fin in k.lower() for fin in ("budget", "price", "cost", "quotation", "lkr", "subtotal"))]
            for k in obsolete_keys:
                data.pop(k, None)
        return data

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
    ground_surfaces: list[dict[str, Any]] = Field(default_factory=list)
    preference_fulfillment: dict[str, Any] = Field(default_factory=dict)
    validation_summary: ExteriorValidationResponse
    metrics: dict[str, Any]
    factors_assessment: dict[str, Any] | None = None
    concept_rules_applied: list[str] = Field(default_factory=list)
    rule_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    rule_summary: dict[str, Any] | None = None
    approval_status: str | None = None


ExteriorLandscape = ExteriorLandscapeResponse


class ELIAResponse(BaseModel):
    project_id: str
    run_id: str
    status: Literal["completed", "infeasible"]
    outcome: Literal["valid", "infeasible"]
    exterior_landscape: ExteriorLandscapeResponse
    master_json_updated: bool
    generation_mode: str


class CandidateValidationRequest(BaseModel):
    master_json: dict[str, Any] | None = None
    exterior_landscape: dict[str, Any]
    requirements: ELIARequirements = Field(default_factory=ELIARequirements)


class CandidateValidationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    valid: bool
    violations: list[str] = Field(default_factory=list)
    checks_passed: int = Field(default=0, ge=0)
    checks_total: int = Field(default=0, ge=0)
    constraint_satisfaction_rate: FiniteFloat = Field(default=0.0, ge=0, le=1)
    factors_assessment: dict[str, Any] | None = None
    rule_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    rule_summary: dict[str, Any] | None = None
    approval_status: str | None = None
    hard_blocks: list[dict[str, Any]] = Field(default_factory=list)
    conditional_reviews: list[dict[str, Any]] = Field(default_factory=list)
    validation_summary: dict[str, Any] | None = None
    canonical_candidate: dict[str, Any] | None = None


class CandidateSaveRequest(BaseModel):
    exterior_landscape: dict[str, Any]
    source_revision: int = Field(ge=1)
    requirements: ELIARequirements = Field(default_factory=ELIARequirements)
    run_id: str | None = None


class FeatureFeasibilityAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    feature_id: str
    requested_state: str
    feasibility_status: FeasibilityStatus
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str
    affected_object_ids: list[str] = Field(default_factory=list)
    applicable_rule_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    assessment_scope: str = ""
    source_revision: int | None = None
    suggested_alternatives: list[str] = Field(default_factory=list)


class CombinedConflictResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    conflicting_features: list[str] = Field(default_factory=list)
    conflict_type: str
    explanation: str
    affected_requests: dict[str, Any] = Field(default_factory=dict)
    suggested_alternatives: list[str] = Field(default_factory=list)


class ProjectFeasibilityResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str = ""
    source_revision: int | None = None
    overall_status: Literal["feasible", "infeasible", "review_required", "conflicts_detected"]
    feature_assessments: dict[str, FeatureFeasibilityAssessment] = Field(default_factory=dict)
    combined_conflicts: list[CombinedConflictResult] = Field(default_factory=list)
    spatial_metrics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


