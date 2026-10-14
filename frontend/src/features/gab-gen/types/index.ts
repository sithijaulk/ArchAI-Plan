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
  floor_preference: 'ground' | 'first' | 'second' | 'any';
  priority: 'high' | 'medium' | 'low';
  custom_name?: string;
}

export interface ClientRequirements {
  project_name?: string;
  description?: string;
  declared_land_extent: number;
  declared_land_unit: 'perches' | 'sqft' | 'sqm';
  drawing_scale?: string;
  road_frontage_edge_id?: string;
  source_notes?: string;
  building_type: 'residential_house' | 'residential_building';
  storey_count: number;
  preferred_total_building_area?: number;
  preferred_ground_coverage?: number;
  rooms: RoomRequirement[];
  occupant_count?: number;
  open_plan_living_dining?: boolean;
  separate_kitchen?: boolean;
  attached_bathroom_count?: number;
  parking_capacity?: number;
  staircase_preference?: string;
  additional_notes?: string;
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
  status: 'pending' | 'input_ready' | 'processing' | 'needs_verification' | 'completed' | 'failed' | 'infeasible';
  closure_error?: number;
  closure_tolerance?: number;
  declared_area_sqm?: number;
  reconstructed_area_sqm?: number;
  area_difference_sqm?: number;
  area_difference_percent?: number;
  violations: string[];
  warnings: string[];
}

export interface GabGenMasterJson {
  project_id: string;
  project_name: string;
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
  gab_gen_validation: GabGenValidation;
  processing: {
    gab_gen: {
      status: string;
      stage: string;
      survey_provider: string;
      allocation_provider: string;
    };
    [key: string]: any;
  };
}
