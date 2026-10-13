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
  generation_mode?: string;
  /** Raw land polygon coordinates passed back by some baseline implementations */
  land?: GeoJsonGeometry;
  house_exterior?: GeoJsonGeometry;
  [key: string]: unknown;
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
  garage_required?: boolean;
  garage_capacity?: number;
  vehicle_count?: number;
  driveway_required?: boolean;
  driveway_style?: string;
  turning_space_required?: boolean;
}

export interface EliaLandscapeRequirements {
  garden_required?: boolean;
  lawn_required?: boolean;
  garden_seating_required?: boolean;
  garden_table_set_required?: boolean;
  preferred_garden_zone?: string | null;
  preferred_open_space_ratio?: number | null;
  greenery_density?: 'low' | 'medium' | 'high';
  shade_tree_preference?: boolean;
  low_maintenance_preference?: boolean | null;
  pedestrian_path_required?: boolean;
  garden_path_required?: boolean;
  boundary_wall_required?: boolean;
  boundary_wall_type?: string | null;
  boundary_wall_height_m?: number | null;
}

export interface EliaVerticalGreeneryRequirements {
  mode?: 'automatic' | 'preferred' | 'disabled';
  enabled?: boolean;
}

export interface EliaLightingRequirements {
  required?: boolean;
  style?: string;
  zones?: string[];
  preferred_spacing_m?: number | null;
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
  lighting?: EliaLightingRequirements;
  additional_requirements?: Record<string, unknown> | string;
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

