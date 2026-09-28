export type ProjectComponentStatus = "pending" | "processing" | "completed" | "failed" | "skipped";

export interface ComponentStatus {
  status: ProjectComponentStatus;
  updatedAt?: string;
}

export interface MasterJson {
  project_id: string;
  project_name: string;
  land_info: Record<string, any>;
  buildable_footprint: Record<string, any>;
  floor_plan: Record<string, any>;
  structural_rectification: Record<string, any>;
  interior_layout: Record<string, any>;
  exterior_landscape: Record<string, any>;
  processing: {
    gab_gen: ComponentStatus;
    vsai_rectifier: ComponentStatus;
    esai_engine: ComponentStatus;
    elia_engine: ComponentStatus;
  };
}
