/**
 * TypeScript types for the ELIA ExteriorLandscape response.
 * Mirrors backend schemas.py ExteriorLandscapeResponse.
 * All coordinate values are in meters. Polygons are [x, y][] ring arrays.
 */

export interface GeoJsonPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface GeoJsonPoint {
  type: 'Point';
  coordinates: number[];
}

export type GeoJsonGeometry = GeoJsonPolygon | GeoJsonPoint | { type: string; coordinates: unknown };

/** A single located exterior feature (gate, garage, vegetation node, light, etc.) */
export interface ExteriorFeature {
  json_id: string;
  type?: string | null;
  category?: string | null;
  /** [x, y] in meters */
  position?: [number, number] | { x: number; y: number } | null;
  /** Ring array [x, y][] in meters */
  polygon?: [number, number][] | null;
  /** GeoJSON geometry in meters */
  geometry?: GeoJsonGeometry | null;
  dimensions?: Record<string, number> | null;
  rotation_degrees?: number | null;
  units?: string;
  floor_id?: string | null;
  support_json_id?: string | null;
  height_m?: number | null;
  canopy_radius_m?: number | null;
  width_m?: number | null;
  depth_m?: number | null;
  elevation_m?: number | null;
  /** Validation override – allows unplaced features */
  validation?: { valid?: boolean };
  /** Extra fields from extra="allow" */
  [key: string]: unknown;
}

export interface ExteriorAccess {
  gate?: ExteriorFeature | null;
  gates?: ExteriorFeature[];
  garage?: ExteriorFeature | null;
  driveway?: ExteriorFeature | null;
}

export interface ExteriorLighting {
  nodes: ExteriorFeature[];
}

export interface ExteriorVertical {
  elements: ExteriorFeature[];
}

export interface ExteriorValidation {
  valid: boolean;
  violations: string[];
  checks_passed: number;
  checks_total: number;
  constraint_satisfaction_rate: number;
}

export interface ExteriorEnvironment {
  north_angle?: number;
  north_orientation_convention?: string;
  solar_samples?: unknown[];
  shadows?: unknown[];
  [key: string]: unknown;
}

export interface PreferenceFulfillment {
  unsupported_preferences?: string[];
  unfulfilled_preferences?: string[];
  label_only_preferences?: string[];
}

export interface ExteriorLandscape {
  version: string;
  schema_version: string;
  run_id: string;
  coordinate_reference: string;
  access: ExteriorAccess;
  site_analysis: Record<string, unknown>;
  utility_safety: Record<string, unknown>;
  environment: ExteriorEnvironment;
  vegetation_nodes: ExteriorFeature[];
  vertical_greenery: ExteriorVertical;
  outdoor_lighting: ExteriorLighting;
  outdoor_elements: ExteriorFeature[];
  validation_summary: ExteriorValidation;
  metrics: Record<string, unknown>;
  preference_fulfillment?: PreferenceFulfillment;
  generation_mode?: string;
  factors_assessment?: FactorsAssessment;
  concept_rules_applied?: string[];
  rule_evaluations?: RuleEvaluationResult[];
  rule_summary?: Record<string, CategorySummary>;
  approval_status?: string;
  /** Raw land polygon coordinates passed back by some baseline implementations */
  land?: GeoJsonGeometry;
  house_exterior?: GeoJsonGeometry;
  [key: string]: unknown;
}

export interface EliaCandidateRecord {
  projectId: string;
  runId?: string | null;
  sourceRevision: number | null;
  sourceSnapshot: Record<string, unknown> | null;
  submittedFingerprint: string;
  generationMode: 'baseline' | 'trained_model';
  outcome: 'valid' | 'infeasible';
  kind: 'preview' | 'persisted_run';
  landscape: ExteriorLandscape;
  timestamp: string;
}

export type EliaContextFreshness = 'loading' | 'current' | 'stale' | 'unavailable';

export interface EliaProvenance {
  projectId: string;
  sourceRevision: number | null;
  requirementsFingerprint: string;
  runId?: string | null;
  outcome?: 'valid' | 'infeasible' | null;
  persisted?: boolean;
  timestamp: string;
  generationMode?: string;
  sourceSnapshot?: Record<string, unknown> | null;
}

/**
 * Derived in-memory view model that pairs authoritative upstream geometry
 * from Master JSON with the ELIA proposal, enforcing single unit normalization
 * and revision synchronization without mutating the persisted Master JSON.
 */
export interface EliaViewModel {
  projectId?: string;
  sourceRevision?: number | null;
  /** Authoritative land boundary polygon in meters (with supported interior holes) */
  landPolygon: GeoJsonPolygon | null;
  /** Authoritative house footprint polygon in meters (with supported interior holes) */
  housePolygon: GeoJsonPolygon | null;
  /** Upstream building height in meters if supplied */
  buildingHeightM?: number | null;
  /** Whether building height is an estimate or surveyed */
  isHeightEstimated: boolean;
  /** The generated exterior landscape candidate / result */
  landscape: ExteriorLandscape | null;
  /** State of input geometry */
  geometryState: 'ready' | 'missing_land' | 'missing_house' | 'missing_all' | 'revision_mismatch';
  /** Human-readable explanatory message */
  geometryMessage?: string;
}

// ---------------------------------------------------------------------------
// Client Requirements & API Request/Response Types
// ---------------------------------------------------------------------------

export interface EliaLocationInput {
  latitude?: number | null;
  longitude?: number | null;
  timezone?: string | null;
  city?: string | null;
}

export interface EliaAccessRequirements {
  road_side?: string | null;
  road_access_edge?: number | null;
  gate_type?: string;
  gate_width_m?: number | null;
  gate_count?: number;
  parking_required?: boolean;
  parking_type?: 'garage' | 'covered' | 'open' | 'no_preference';
  garage_required?: boolean;
  garage_capacity?: number;
  vehicle_count?: number;
  driveway_required?: boolean;
  driveway_style?: string;
  driveway_surface?: string;
  walking_path_surface?: string;
  gate_required?: boolean;
  gate_opening_mechanism?: string;
  gate_style?: string;
  turning_space_required?: boolean;
}

export interface EliaLandscapeRequirements {
  garden_required?: boolean;
  lawn_required?: boolean;
  garden_ground_finish?: 'grass' | 'interlock' | 'paving_stones' | 'mixed';
  garden_seating_required?: boolean;
  garden_seating_count?: number | null;
  garden_table_set_required?: boolean;
  garden_table_set_count?: number | null;
  preferred_garden_zone?: string | null;
  preferred_open_space_ratio?: number | null;
  greenery_density?: 'low' | 'medium' | 'high';
  trees_required?: boolean;
  tree_quantity?: number | null;
  compact_trees_preference?: boolean;
  shrubs_required?: boolean;
  shrubs_quantity?: number | null;
  flower_beds_required?: boolean;
  ground_planters_required?: boolean;
  ground_planters_count?: number | null;
  shade_tree_preference?: boolean;
  low_maintenance_preference?: boolean | null;
  maintenance_preference?: 'low' | 'medium' | 'high' | 'no_preference' | 'unknown';
  water_availability?: 'limited' | 'regular' | 'irrigation_available' | 'unknown';
  preferred_plant_ids?: string[];
  plant_ids_to_avoid?: string[];
  climate_zone?: string | null;
  site_exposure?: string | null;
  pedestrian_path_required?: boolean;
  garden_path_required?: boolean;
  boundary_wall_required?: boolean;
  boundary_wall_type?: string | null;
  boundary_wall_height_m?: number | null;
}

export interface EliaVerticalGreeneryRequirements {
  mode?: 'automatic' | 'preferred' | 'disabled';
  enabled?: boolean;
  wall_climbing_plants?: boolean;
  wall_mounted_greenery?: boolean;
  hanging_trailing_greenery?: boolean;
  accept_vertical_alternatives?: boolean;
}

export interface EliaBalconyRequirements {
  planting_required?: boolean;
  potted_plants?: boolean;
  hanging_plants?: boolean;
  seating_required?: boolean;
  preferred_plant_ids?: string[];
  target_balcony_ids?: string[];
}

export interface EliaTerraceRequirements {
  planting_required?: boolean;
  planters_required?: boolean;
  seating_required?: boolean;
  tables_required?: boolean;
  target_terrace_ids?: string[];
}

export interface EliaLightingRequirements {
  required?: boolean;
  style?: string;
  zones?: string[];
  preferred_spacing_m?: number | null;
  desired_fixture_count?: number | null;
  garden_lighting?: boolean;
  pathway_lighting?: boolean;
  seating_lighting?: boolean;
  wall_lighting?: boolean;
}

export interface EliaWaterFeatureRequirements {
  well_required?: boolean;
  garden_taps_required?: boolean;
  garden_taps_count?: number | null;
  pond_required?: boolean;
  swimming_pool_required?: boolean;
  septic_tank_required?: boolean;
}

export interface EliaSolarRequirements {
  panels_required?: boolean;
  preferred_roof_surface?: 'flat_roof' | 'south_facing' | 'north_facing' | 'auto' | 'any';
  placement_priority?: 'maximum_yield' | 'concealed_from_street' | 'balanced';
  include_live_solar?: boolean;
}

export interface LockedExteriorFeature {
  json_id: string;
  category?: string | null;
  plant_id?: string | null;
  position: [number, number];
  canopy_radius_m?: number | null;
  height_m?: number | null;
  locked: boolean;
}

export type LockedFeatureRequirement = LockedExteriorFeature;

export interface FactorAssessmentRow {
  factor: string;
  factor_label: string;
  input_value: string;
  data_source: string;
  status: 'satisfied' | 'unmet' | 'unknown' | 'not_applicable';
  reason_and_limitations: string;
}

export type RuleOutcome = 'pass' | 'fail' | 'unknown' | 'not_applicable' | 'review_required';
export type RuleClass = 'L' | 'E' | 'P' | 'D';
export type RuleCategory = 'geometric_validity' | 'environmental_suitability' | 'legal_assessment' | 'elevated_installation' | 'user_preference';

export interface RuleEvaluationResult {
  rule_id: string;
  version: string;
  rule_class: RuleClass;
  category: string;
  title: string;
  applicability: 'applicable' | 'not_applicable' | 'unknown';
  outcome: RuleOutcome;
  affected_object_ids?: string[];
  measured_value?: unknown;
  measured_units?: string;
  evidence?: string;
  missing_inputs?: string[];
  explanation?: string;
  practical_remedy?: string;
  evaluation_time?: string;
  upstream_revision?: number;
}

export interface CategorySummary {
  total: number;
  pass: number;
  fail: number;
  unknown: number;
  review_required: number;
  not_applicable: number;
}

export interface FactorsAssessment {
  overall_status?: 'satisfactory' | 'compromised' | 'unverified';
  assessment_version?: string;
  summary?: {
    total_factors: number;
    satisfied: number;
    unmet: number;
    unknown: number;
    not_applicable: number;
  };
  factors?: FactorAssessmentRow[];
  object_level_explanations?: Array<{
    json_id: string;
    display_name?: string;
    category?: string;
    suitability_explanation?: string;
    locked?: boolean;
  }>;
  summary_notes?: string[];
  rule_evaluations?: RuleEvaluationResult[];
  category_summaries?: Record<string, CategorySummary>;
  approval_status?: string;
}

export interface ELIARequirements {
  units?: string;
  design_style?: string;
  greenery_level?: string;
  landscape_priority?: string;
  vertical_greenery_enabled?: boolean;
  location?: EliaLocationInput;
  latitude?: number | null;
  longitude?: number | null;
  timezone?: string | null;
  include_live_solar?: boolean;
  access?: EliaAccessRequirements;
  landscape?: EliaLandscapeRequirements;
  vertical_greenery?: EliaVerticalGreeneryRequirements;
  balconies?: EliaBalconyRequirements;
  terrace?: EliaTerraceRequirements;
  lighting?: EliaLightingRequirements;
  water_features?: EliaWaterFeatureRequirements;
  solar?: EliaSolarRequirements;
  maintenance_preference?: 'low' | 'medium' | 'high' | 'no_preference';
  low_maintenance_preference?: boolean | null;
  water_availability?: 'limited' | 'regular' | 'irrigation_available' | 'unknown';
  climate_zone?: 'wet_zone' | 'intermediate_zone' | 'dry_zone' | 'arid_zone' | 'unknown';
  site_exposure?: 'sheltered' | 'moderate' | 'exposed' | 'coastal_wind' | 'unknown';
  preferred_plant_ids?: string[];
  plant_ids_to_avoid?: string[];
  locked_features?: LockedExteriorFeature[];
  additional_requirements?: Record<string, unknown> | string;
}

export interface CandidateValidationRequest {
  exterior_landscape: ExteriorLandscape;
  requirements?: ELIARequirements;
}

export interface CandidateValidationResponse {
  valid: boolean;
  violations: string[];
  checks_passed: number;
  checks_total: number;
  constraint_satisfaction_rate?: number;
  factors_assessment?: FactorsAssessment;
  rule_evaluations?: RuleEvaluationResult[];
  rule_summary?: Record<string, CategorySummary>;
  approval_status?: string;
  hard_blocks?: RuleEvaluationResult[];
  conditional_reviews?: RuleEvaluationResult[];
  validation_summary?: ExteriorValidation;
  canonical_candidate?: ExteriorLandscape;
}

export interface CandidateSaveRequest {
  exterior_landscape: ExteriorLandscape;
  source_revision: number;
  requirements?: ELIARequirements;
}

export interface CandidateSaveResponse {
  project_id: string;
  run_id: string;
  status: 'completed' | 'infeasible';
  outcome: 'valid' | 'infeasible';
  revision: number;
  exterior_landscape: ExteriorLandscape;
}

export interface ELIARequestPayload {
  requirements?: ELIARequirements;
  master_json?: Record<string, unknown> | null;
  apply_to_project?: boolean;
  generation_mode?: 'baseline' | 'trained_model';
  source_revision?: number | null;
}

export interface ELIAResponse {
  project_id: string;
  run_id: string;
  status: 'completed' | 'infeasible';
  outcome: 'valid' | 'infeasible';
  exterior_landscape: ExteriorLandscape;
  master_json_updated: boolean;
  generation_mode: 'baseline' | 'trained_model';
}

export interface ELIAPreviewResponse {
  run_id: string;
  status: 'completed' | 'infeasible';
  outcome: 'valid' | 'infeasible';
  exterior_landscape: ExteriorLandscape;
  master_json: Record<string, unknown>;
  generation_mode: string;
  persisted: boolean;
}

export type FeasibilityStatus =
  | 'feasible'
  | 'infeasible'
  | 'review_required'
  | 'not_applicable'
  | 'unsupported'
  | 'search_inconclusive';

export interface FeatureFeasibilityAssessment {
  feature_id: string;
  requested_state: string;
  feasibility_status: FeasibilityStatus;
  reason_codes: string[];
  explanation: string;
  affected_object_ids?: string[];
  applicable_rule_ids?: string[];
  missing_evidence?: string[];
  assessment_scope?: string;
  source_revision?: number | null;
  suggested_alternatives?: string[];
}

export interface CombinedConflictResult {
  conflicting_features: string[];
  conflict_type: string;
  explanation: string;
  affected_requests?: Record<string, unknown>;
  suggested_alternatives?: string[];
}

export interface ProjectFeasibilityResponse {
  project_id?: string;
  source_revision?: number | null;
  overall_status: 'feasible' | 'infeasible' | 'review_required' | 'conflicts_detected';
  feature_assessments: Record<string, FeatureFeasibilityAssessment>;
  combined_conflicts: CombinedConflictResult[];
  spatial_metrics: Record<string, unknown>;
  limitations: string[];
}

export interface ELIAValidationResponse {
  valid: boolean;
  project_id: string;
  normalized_requirements: Record<string, unknown>;
  geometry: {
    land_area_m2: number;
    house_footprint_area_m2: number;
    source_units: string;
  };
  orientation: {
    north_angle_degrees: number;
    convention: string;
  };
  feasibility?: ProjectFeasibilityResponse;
}

export interface ELIAContextResponse {
  project_id: string;
  master_json: Record<string, unknown> | null;
  revision?: number | null;
}

export interface ELIAResultResponse {
  run_id: string;
  status: string;
  output: ExteriorLandscape | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface EliaUnresolvedMutation {
  projectId: string;
  sourceRevision: number;
  submittedFingerprint: string;
  submittedGenerationMode: 'baseline' | 'trained_model';
  snapshotAtSubmit: Record<string, unknown> | null;
  submittedAt: string;
  status: 'unresolved' | 'processing' | 'correlated_terminal';
  correlatedRunId?: string;
  reconciliationError?: string | null;
}

