import { MasterJson } from './master-json';

export interface Project {
  id: string;
  project_name: string;
  projectName?: string;
  description?: string;
  current_component?: string | null;
  master_json: MasterJson;
  created_at?: string;
  updated_at?: string;
}

export interface ProjectCreate {
  project_name: string;
  description?: string;
}

export interface ProjectUpdate {
  project_name?: string;
  description?: string;
  current_component?: string;
  master_json?: Partial<MasterJson>;
}

export interface VastuReadinessCheck {
  ready: boolean;
  reason?: string | null;
}

export interface VastuReadiness {
  status: 'READY' | 'PARTIALLY_READY' | 'NOT_READY';
  padavinyasa_9x9: VastuReadinessCheck;
  brahmasthan: VastuReadinessCheck;
  entrance_32_pada: VastuReadinessCheck;
  directional_room_placement: VastuReadinessCheck;
}

export interface ElementCounts {
  rooms: number;
  structural_elements: number;
  walls: number;
  doors: number;
  windows: number;
}

export interface SpatialSummary {
  room_count: number;
  rooms: Array<{
    id: string;
    name: string;
    type: string;
    points_count: number;
  }>;
  structural_elements_count: number;
  walls_count?: number;
  doors_count?: number;
  windows_count?: number;
  orientation: string;
  road_facing: string;
  area_sqft?: number | null;
  boundary_points_count?: number;
  bounding_box?: {
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    width: number;
    height: number;
  } | null;
}

export interface VastuGoodAspect {
  rule_id: string;
  title: string;
  room_id?: string | null;
  room_name?: string;
  sector?: string;
  sector_display?: string;
  polygon?: [number, number][];
  description: string;
  points_earned: number;
}

export interface VastuDefect {
  rule_id: string;
  title: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'INFO';
  room_id?: string | null;
  room_name?: string;
  sector?: string;
  sector_display?: string;
  polygon?: [number, number][];
  description: string;
  remedy?: string;
  points_deducted: number;
}

export interface VastuAnalysis {
  score: number;
  grade: string;
  grade_description: string;
  good_aspects: VastuGoodAspect[];
  defects: VastuDefect[];
  total_rules_evaluated: number;
  passed_rules_count: number;
  failed_rules_count: number;
  room_sectors?: Record<string, {
    id: string;
    name: string;
    type: string;
    sector: string;
    sector_display: string;
    centroid: [number, number];
    polygon: [number, number][];
    overlaps_brahmasthan: boolean;
  }>;
  brahmasthan?: {
    status: string;
    obstructing_rooms: string[];
    exact_center?: [number, number];
    tolerance?: number;
    obstructing_objects?: string[];
  };
  dwara_sthana?: {
    house_type: string;
    classification: string;
    directions: string[];
    traditional_result?: string;
  };
  main_entrance?: {
    identified: boolean;
    door_id?: string | null;
    sector?: string | null;
    classification?: string | null;
  };
  bounding_box?: {
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    width: number;
    height: number;
    area_sqft: number;
  };
}

export interface MissingInfoOption {
  value: string;
  label: string;
}

export interface MissingInfoQuestion {
  id: string;
  category: 'orientation' | 'main_entrance' | 'door_direction' | 'room_type' | 'missing_geometry' | 'geometry_conflict';
  target_element_id?: string;
  title: string;
  description: string;
  field_path: string;
  current_value: any;
  suggested_value: any;
  has_conflict: boolean;
  is_required: boolean;
  input_type: 'select' | 'radio' | 'text' | 'number';
  options: MissingInfoOption[];
}

export interface MissingInfoReport {
  has_blocking_missing_info: boolean;
  questions_count: number;
  questions: MissingInfoQuestion[];
  summary: string;
}

export interface ValidationResult {
  status: 'VALID' | 'VALID_WITH_WARNINGS' | 'INVALID' | 'INSUFFICIENT_DATA';
  is_valid: boolean;
  can_rectify: boolean;
  errors: string[];
  warnings: string[];
  missing_fields: string[];
  summary: string;
  element_counts: ElementCounts;
  vastu_readiness: VastuReadiness;
  spatial_summary: SpatialSummary;
  missing_info_report?: MissingInfoReport;
  vastu_analysis?: VastuAnalysis;
}

export interface UploadMasterJsonResponse {
  project: Project;
  file_saved_path: string;
  filename: string;
  spatial_summary: SpatialSummary;
  validation?: ValidationResult;
  vastu_analysis?: VastuAnalysis;
}
