/**
 * ESAI Engine Frontend Types
 * Strictly typed interfaces for spatial geometry, client preferences,
 * saved Master JSON interior designs, and 3D WebGL / Three.js scene data.
 */

export interface Coordinate2D {
  x: number;
  y: number;
}

export interface Dimensions3D {
  width: number;
  depth: number;
  height: number;
}

export interface DoorDTO {
  id: string;
  room_id?: string;
  start: Coordinate2D;
  end: Coordinate2D;
  leaf_width: number;
  hinge?: string;
  opening_direction?: string;
  swing_angle?: number;
  protected_depth?: number;
  position?: Coordinate2D;
  width?: number;
  height?: number;
  rotation_deg?: number;
}

export interface WindowDTO {
  id: string;
  room_id?: string;
  start: Coordinate2D;
  end: Coordinate2D;
  length: number;
  sill_height?: number;
  height?: number;
  opening_type?: string;
  protected_access_depth?: number;
  position?: Coordinate2D;
  width?: number;
  rotation_deg?: number;
}

export interface WallDTO {
  id: string;
  floor_id?: string;
  start: Coordinate2D;
  end: Coordinate2D;
  thickness: number;
  height?: number;
  wall_type: string;
  related_room_ids?: string[];
  orientation?: string;
}

export interface FixedObstructionDTO {
  id: string;
  name: string;
  polygon: Coordinate2D[];
  height?: number;
  category: string;
}

export interface RoomDTO {
  floor_id: string;
  room_id: string;
  name: string;
  room_type: string;
  source_room_type?: string;
  is_unsupported_type?: boolean;
  polygon: Coordinate2D[];
  area_sqm: number;
  ceiling_height?: number;
  height_m?: number;
  elevation?: number;
  doors: DoorDTO[];
  windows: WindowDTO[];
  fixed_obstructions: FixedObstructionDTO[];
  walls?: WallDTO[];
  doors_data_available?: boolean;
  windows_data_available?: boolean;
  missing_upstream_fields?: string[];
}

export interface FloorDTO {
  floor_id: string;
  floor_name: string;
  level_index: number;
  elevation: number;
  elevation_m?: number;
  floor_height?: number;
  rooms: RoomDTO[];
  walls: WallDTO[];
}

export interface PlacedAssetPersistedDTO {
  instance_id: string;
  asset_id: string;
  catalog_id?: string;
  asset_name: string;
  category: string;
  subcategory?: string;
  variant_id?: string;
  variant?: string;
  dimensions: Dimensions3D;
  position: Coordinate2D;
  rotation_deg: number;
  placement_mode?: string;
  associated_wall_id?: string;
  attached_wall_id?: string;
  is_locked?: boolean;
  is_user_locked?: boolean;
  is_mandatory?: boolean;
  material?: string;
  color?: string;
  bounding_box?: {
    min_x: number;
    min_y: number;
    max_x: number;
    max_y: number;
  };
  validation_metadata?: Record<string, unknown>;
}

export interface PlacedFixturePointDTO {
  point_id?: string;
  fixture_id?: string;
  point_type?: string;
  fixture_type?: string;
  description?: string;
  purpose?: string;
  associated_instance_id?: string;
  associated_asset_instance_id?: string;
  position: Coordinate2D;
  installation_height_m?: number;
  height_from_floor_m?: number;
  wall_id?: string;
  status?: string;
  is_proposed?: boolean;
  requires_professional_verification?: boolean;
  spec?: Record<string, unknown>;
}

export interface PersistedRoomDesignDTO {
  project_id: string;
  floor_id: string;
  room_id: string;
  room_name: string;
  room_type: string;
  geometry_revision: number;
  geometry_fingerprint?: string;
  preference_revision?: number;
  design_revision: number;
  catalog_version?: string;
  generation_status?: string;
  generation_timestamp?: string;
  active_alternative_id?: string;
  polygon: Coordinate2D[];
  area_sqm: number;
  ceiling_height_m?: number;
  furniture?: PlacedAssetPersistedDTO[];
  cabinetry?: PlacedAssetPersistedDTO[];
  appliances?: PlacedAssetPersistedDTO[];
  sanitary_fixtures?: PlacedAssetPersistedDTO[];
  lighting?: PlacedFixturePointDTO[];
  electrical_points?: PlacedFixturePointDTO[];
  plumbing_requirements?: PlacedFixturePointDTO[];
  service_requirements?: Record<string, unknown>[];
  wall_finishes?: Record<string, unknown>;
  floor_finishes?: Record<string, unknown>;
  ceiling_finishes?: Record<string, unknown>;
  decorations?: PlacedAssetPersistedDTO[];
  placed_assets?: PlacedAssetPersistedDTO[];
  fixtures?: PlacedFixturePointDTO[];
  wall_finish?: string;
  wall_color?: string;
  floor_finish?: string;
  ceiling_finish?: string;
  validation?: {
    fitness_score?: number;
    fitness_breakdown?: Record<string, unknown>;
    hard_constraints_passed?: boolean;
    ergonomic_evaluations?: Record<string, unknown>[];
    diagnostics?: string[];
  };
  alternatives?: {
    alternative_index: number;
    fitness_score: number;
    distinctness_score: number;
    placed_assets: Record<string, unknown>[];
    fitness_breakdown?: Record<string, unknown>;
  }[];
  generation_metadata?: Record<string, unknown>;
}

export interface DesignStalenessRoomReportDTO {
  room_id: string;
  floor_id: string;
  room_name: string;
  has_saved_design: boolean;
  design_revision?: number;
  is_stale: boolean;
  geometry_stale: boolean;
  preference_stale: boolean;
  saved_geometry_fingerprint?: string;
  current_geometry_fingerprint?: string;
  saved_preference_revision?: number;
  current_preference_revision?: number;
  reason?: string;
}

export interface DesignStalenessReportDTO {
  project_id: string;
  current_geometry_fingerprint: string;
  is_any_room_stale: boolean;
  rooms: Record<string, DesignStalenessRoomReportDTO>;
}

export interface SceneDataResponse {
  project_id: string;
  project_name: string;
  unit: string;
  geometry_revision: number;
  design_revision: number;
  geometry_fingerprint?: string;
  floors: FloorDTO[];
  saved_designs: Record<string, PersistedRoomDesignDTO>;
  staleness: DesignStalenessReportDTO;
}

// ── 3D Viewer Specific Types ────────────────────────────────────────────────

export type ViewCameraMode = 'perspective' | 'top_down' | 'isometric' | 'walkthrough' | 'room_focus';

export interface LayerVisibilityState {
  walls: boolean;
  ceiling: boolean;
  furniture: boolean;
  cabinetry: boolean;
  appliances: boolean;
  sanitary: boolean;
  lighting: boolean;
  servicePoints: boolean;
  roomLabels: boolean;
  wireframe: boolean;
}

export interface ViewerSelectionState {
  selectedFloorId: string | null;
  selectedRoomId: string | null;
  selectedAsset: PlacedAssetPersistedDTO | null;
  selectedFixture: PlacedFixturePointDTO | null;
}

// ── Phase 7: Interactive Editing, Validation, Locking & Selective Regeneration ─

export interface ValidationDiagnosticDTO {
  code: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  instance_id?: string | null;
  room_id?: string | null;
  rule_id?: string | null;
  suggested_correction?: string | null;
}

export interface RoomEditValidateRequest {
  room_id: string;
  floor_id?: string;
  furniture?: PlacedAssetPersistedDTO[];
  cabinetry?: PlacedAssetPersistedDTO[];
  appliances?: PlacedAssetPersistedDTO[];
  sanitary_fixtures?: PlacedAssetPersistedDTO[];
  lighting?: PlacedFixturePointDTO[];
  electrical_points?: PlacedFixturePointDTO[];
  plumbing_requirements?: PlacedFixturePointDTO[];
  wall_finish?: string;
  floor_finish?: string;
  ceiling_finish?: string;
}

export interface RoomEditValidateResponse {
  is_valid: boolean;
  hard_constraints_passed: boolean;
  diagnostics: ValidationDiagnosticDTO[];
  overlap_area_sqm: number;
  out_of_bounds_area_sqm: number;
  door_violation_count: number;
  window_violation_count: number;
  ergonomic_score: number;
}

export interface SaveRoomEditRequest extends RoomEditValidateRequest {
  expected_design_revision?: number;
}

export interface SaveRoomEditResponse {
  success: boolean;
  project_id: string;
  room_id: string;
  design_revision: number;
  updated_at: string;
  saved_design: PersistedRoomDesignDTO;
}

export interface LockAssetRequest {
  instance_id: string;
  is_locked?: boolean;
  lock_type?: 'position' | 'rotation' | 'all';
  expected_design_revision?: number;
}

export interface LockAssetResponse {
  success: boolean;
  project_id: string;
  room_id: string;
  instance_id: string;
  is_locked: boolean;
  design_revision: number;
  updated_at: string;
}

export interface RegenerateUnlockedRequest {
  expected_design_revision?: number;
  seed?: number;
  population_size?: number;
  generations?: number;
  auto_save?: boolean;
}

export interface RegenerateUnlockedResponse {
  success: boolean;
  project_id: string;
  room_id: string;
  design_revision: number;
  saved_design?: PersistedRoomDesignDTO;
  diagnostics: string[];
}

// ── Phase 8: PDF Report & Final Export Types ─────────────────────────────────

export type ReportScope = 'building' | 'floor' | 'room';
export type ReportMode = 'final' | 'draft';
export type ReportSection =
  | 'cover'
  | 'table_of_contents'
  | 'project_overview'
  | 'building_floor_summary'
  | 'client_preferences'
  | 'room_layouts'
  | 'furniture_schedule'
  | 'kitchen_schedule'
  | 'bathroom_schedule'
  | 'lighting_schedule'
  | 'electrical_schedule'
  | 'plumbing_schedule'
  | 'finish_schedule'
  | 'ergonomic_validation'
  | 'optimization_summary'
  | 'layout_drawings'
  | 'interior_views_3d'
  | 'disclaimers';

export interface PdfReportRequest {
  scope?: ReportScope;
  mode?: ReportMode;
  target_floor_id?: string;
  target_room_id?: string;
  floor_id?: string;
  room_id?: string;
  floor_ids?: string[];
  room_ids?: string[];
  sections?: ReportSection[];
  include_2d_drawings?: boolean;
  include_3d_views?: boolean;
  view_captures?: Record<string, string>;
  viewer_3d_captures?: Record<string, string>;
  author_name?: string;
  notes?: string;
}

export interface ReportOptionsResponse {
  available_scopes: string[];
  available_modes: string[];
  available_sections: string[];
  default_sections: string[];
  supported_scopes?: string[];
  supported_sections?: string[];
  available_floors?: Array<{ id: string; name: string }>;
  available_rooms?: Array<{ id: string; name: string; floor_id?: string; type?: string }>;
  staleness?: {
    is_stale: boolean;
    reasons?: string[];
    geometry_staleness?: boolean;
    preference_staleness?: boolean;
  };
}


