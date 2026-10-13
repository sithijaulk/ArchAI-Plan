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
