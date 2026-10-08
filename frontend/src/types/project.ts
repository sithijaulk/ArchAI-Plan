import { MasterJson } from './master-json';

export interface Project {
  id: string;
  projectName: string;
  description?: string;
  current_component: string | null;
  master_json: MasterJson;
  created_at: string;
  updated_at: string;
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
