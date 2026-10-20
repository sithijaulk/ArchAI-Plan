export interface DistanceValue {
  value: number;
  unit: 'm' | 'ft';
}

export interface BearingValue {
  raw: string;
  normalized_degrees: number;
}

export interface SurveyEdge {
  edge_id: string;
  distance: DistanceValue;
  bearing: BearingValue;
  edge_type?: 'road_front' | 'rear' | 'side' | 'side_left' | 'side_right' | 'other';
  source: 'manual' | 'fixture' | 'easyocr';
  confidence?: number | null;
  source_bbox?: number[] | null;
}

export interface ManualSurveyData {
  north_angle: number;
  reference_edge?: string | null;
  source: 'manual' | 'fixture';
  edges: SurveyEdge[];
}

export interface RoomRequirement {
  id: string;
  type: string;
  quantity: number;
  required: boolean;
  preferred_min_area?: number;
  floor_preference: number | string; // 'auto' or 0, 1, 2, 3
  priority: 'high' | 'medium' | 'low';
  custom_name?: string;
}

export interface RegulatoryContext {
  jurisdiction_id: string;
  province?: string;
  district?: string;
  local_authority_type?: string;
  local_authority_name?: string;
  authority_id?: string;
  development_zone?: string;
  zone_confirmed?: boolean;
  road_width?: number;
  road_category?: string;
  site_restrictions?: {
    restriction_type: string;
    checked: boolean;
    intersected?: boolean | null;
    verification_status?: string;
    notes?: string;
  }[];
}

export type ComplianceVerdict =
  | 'compliant'
  | 'non_compliant'
  | 'requires_regulatory_verification'
  | 'conflict_requires_review'
  | 'not_applicable';

export interface RegulatoryResolution {
  authority_id?: string | null;
  authority_name?: string | null;
  authority_type?: string | null;
  district?: string | null;
  province?: string;
  authority_verification_status?: string;
  planning_jurisdiction_id: string;
  uda_declared_area: boolean;
  uda_jurisdiction_status: string;
  development_zone?: string | null;
  zone_verification_status: string;
  applicability_status: string;
  governing_sources: string[];
  applicable_rule_ids: string[];
  unresolved_requirements: string[];
  disclaimers: string[];
}

export interface ClientRequirements {
  project_name?: string;
  description?: string;
  declared_land_extent: number;
  declared_land_unit: 'perches' | 'acres' | 'sqft' | 'sqm';
  drawing_scale?: string;
  road_frontage_edge_id?: string;
  source_notes?: string;
  regulatory_context?: RegulatoryContext;
  building_type: 'residential_house' | 'residential_building';
  storey_count: number;
  bedroom_count?: number;
  master_bedroom_count?: number;
  bathroom_count?: number;
  kitchen_required?: boolean;
  living_room_required?: boolean;
  dining_room_required?: boolean;
  parking_type?: string;

  preferred_total_building_area?: number;
  preferred_ground_coverage?: number;
  rooms: RoomRequirement[];
  occupant_count?: number;
  open_plan_living_dining?: boolean;
  separate_kitchen?: boolean;
  bathroom_requirements?: string;
  attached_bathroom_count?: number;
  study_office_requirement?: boolean;
  guest_room_requirement?: boolean;
  storage_requirement?: boolean;
  laundry_utility_requirement?: boolean;
  balcony_requirement?: boolean;
  parking_capacity?: number;
  staircase_preference?: string;
  additional_notes?: string;
  roof_preference?: RoofPreference;
}

export type RoofType = 'flat_slab' | 'accessible_rooftop' | 'gable' | 'hip' | 'mono_pitch';

export interface RoofPreference {
  roof_type: RoofType;
  material?: string;
  pitch_angle_deg: number;
  overhang_m: number;
  parapet_height_m?: number;
  rooftop_access: boolean;
  drainage_preference: string;
  notes?: string;
}

export interface RoofPlane {
  plane_id: string;
  polygon: Point2D[];
  pitch_deg: number;
  slope_azimuth: number;
  height_offset_m: number;
}

export interface GeneratedRoofGeometry {
  roof_type: string;
  ridge_points: Point2D[];
  eave_polygon: Point2D[];
  planes: RoofPlane[];
  max_height_m: number;
  drainage: string;
  provenance: string;
}

export interface Point2D {
  x: number;
  y: number;
}

export interface WallSegment {
  wall_id: string;
  floor_id: string;
  start: Point2D;
  end: Point2D;
  wall_type: 'exterior' | 'interior' | 'party';
  thickness: number;
  related_room_ids: string[];
}

export interface RoomPolygon {
  room_id: string;
  name: string;
  type: string;
  floor_id: string;
  area: number;
  target_area: number;
  polygon: Point2D[];
  center: Point2D;
  width_m?: number;
  length_m?: number;
  is_structural_stair?: boolean;
}

export interface FloorPlan {
  floor_id: string;
  floor_index: number;
  name: string;
  elevation: number;
  floor_height: number;
  available_area: number;
  target_allocated_area: number;
  rooms: RoomPolygon[];
  walls: WallSegment[];
}

export interface GabGenValidation {
  valid: boolean;
  status: 'pending' | 'input_ready' | 'processing' | 'needs_verification' | 'completed' | 'failed' | 'infeasible' | 'regulatory_configuration_required';
  closure_error?: number;
  closure_tolerance?: number;
  declared_area_sqm?: number;
  reconstructed_area_sqm?: number;
  area_difference_sqm?: number;
  area_difference_percent?: number;
  violations: string[];
  warnings: string[];
  compliance_verdict?: ComplianceVerdict;
  unresolved_requirements?: string[];
  conflicting_requirements?: string[];
  regulatory_resolution?: RegulatoryResolution;
}

export interface GabGenMasterJson {
  project_id: string;
  project_name: string;
  schema_version?: string;
  units: string;
  input_metadata: {
    source_file?: {
      original_filename: string;
      stored_filename: string;
      file_path: string;
      content_type: string;
      size_bytes: number;
      uploaded_at: string;
    };
    declared_land_extent?: {
      value: number;
      unit: string;
    };
    scale?: {
      ratio: string;
    };
    source_notes?: string;
    regulatory_context?: RegulatoryContext;
  };
  survey_extraction: {
    provider: string;
    north_angle: number;
    reference_edge?: string | null;
    edges: SurveyEdge[];
  };
  land_info: {
    source_land_polygon: Point2D[];
    reconstructed_area: number;
    declared_area: number;
    area_difference_percent: number;
    perimeter: number;
  };
  geometry_validation: {
    valid: boolean;
    closure_error: number;
    relative_error: number;
    warnings: string[];
  };
  regulatory_rules: {
    jurisdiction: string;
    applied_rules: any[];
  };
  buildable_footprint: {
    polygon: Point2D[];
    area: number;
    valid: boolean;
  };
  client_requirements: ClientRequirements;
  space_allocation: {
    provider: string;
    model_version?: string | null;
    total_demanded_area: number;
    total_capacity: number;
    floors: any[];
  };
  floor_plan: {
    floors: FloorPlan[];
  };
  roof_geometry?: GeneratedRoofGeometry;
  building_footprint?: {
    candidate_id: string;
    shape_type: string;
    polygon: Point2D[];
    area: number;
  };
  edit_history?: {
    timestamp: string;
    action: string;
    room_id?: string;
    target_floor_id?: string;
  }[];
  gab_gen_validation: GabGenValidation;
  processing: {
    gab_gen: {
      status: string;
      stage: string;
      gab_gen_version?: string;
      survey_provider: string;
      allocation_provider: string;
    };
    [key: string]: any;
  };
}

export interface GabGenRunOutput {
  project_id: string;
  project_name: string;
  units: string;
  status: 'pending' | 'input_ready' | 'processing' | 'needs_verification' | 'completed' | 'failed' | 'infeasible' | 'regulatory_configuration_required';
  master_json: GabGenMasterJson;
  validation: GabGenValidation;
  warnings: string[];
}
