import { create } from 'zustand';
import { MasterJson, ProjectComponentStatus } from '@/types/master-json';
import { projectsApi } from '@/lib/api/projects';

interface ProjectState {
  projectId: string | null;
  projectName: string;
  currentComponent: string | null;
  masterJson: MasterJson | null;
  componentStatuses: Record<string, ProjectComponentStatus>;
  outputs: Record<string, any>;
  loading: boolean;
  error?: string;
  
  createProject: (name: string, description?: string) => Promise<void>;
  loadProject: (project: { id: string; project_name: string; master_json: MasterJson }) => void;
  setCurrentComponent: (componentId: string) => void;
  updateMasterJson: (data: Partial<MasterJson>) => void;
  setComponentStatus: (componentId: keyof MasterJson['processing'], status: ProjectComponentStatus) => void;
  skipComponent: (componentId: keyof MasterJson['processing']) => Promise<void>;
  setOutput: (componentId: string, output: any) => void;
  resetProject: () => void;
}

const defaultMasterJson = (id: string, name: string): MasterJson => ({
  project_id: id,
  project_name: name,
  land_info: {},
  buildable_footprint: {},
  floor_plan: {},
  structural_rectification: {},
  interior_layout: {},
  exterior_landscape: {},
  processing: {
    gab_gen: { status: 'pending' },
    vsai_rectifier: { status: 'pending' },
    esai_engine: { status: 'pending' },
    elia_engine: { status: 'pending' },
  }
});

export const useProjectStore = create<ProjectState>((set) => ({
  projectId: null,
  projectName: '',
  currentComponent: null,
  masterJson: null,
  componentStatuses: {
    gab_gen: 'pending',
    vsai_rectifier: 'pending',
    esai_engine: 'pending',
    elia_engine: 'pending',
  },
  outputs: {},
  loading: false,

  createProject: async (name, description) => {
    const project = await projectsApi.createProject({ project_name: name, description });
    set({ projectId: project.id, projectName: project.project_name, masterJson: project.master_json, currentComponent: 'gab-gen', outputs: {}, error: undefined });
  },

  loadProject: (project) => set({
    projectId: project.id,
    projectName: project.project_name,
    masterJson: project.master_json,
    componentStatuses: {
      gab_gen: project.master_json.processing.gab_gen.status,
      vsai_rectifier: project.master_json.processing.vsai_rectifier.status,
      esai_engine: project.master_json.processing.esai_engine.status,
      elia_engine: project.master_json.processing.elia_engine.status,
    }
  }),

  setCurrentComponent: (componentId) => set({ currentComponent: componentId }),

  updateMasterJson: (data) => set((state) => ({
    masterJson: state.masterJson ? { ...state.masterJson, ...data } : null
  })),

  setComponentStatus: (componentId, status) => set((state) => {
    if (!state.masterJson) return state;
    
    const newMasterJson = { ...state.masterJson };
    newMasterJson.processing[componentId] = { status, updatedAt: new Date().toISOString() };
    
    return {
      masterJson: newMasterJson,
      componentStatuses: { ...state.componentStatuses, [componentId]: status }
    };
  }),

  skipComponent: async (componentId) => {
    const projectId = useProjectStore.getState().projectId;
    if (!projectId) return;
    const response = await projectsApi.skipComponent(projectId, componentId);
    set((state) => ({
      masterJson: response.master_json,
      componentStatuses: { ...state.componentStatuses, [componentId]: 'skipped' },
    }));
  },

  setOutput: (componentId, output) => set((state) => ({
    outputs: { ...state.outputs, [componentId]: output }
  })),

  resetProject: () => set({
    projectId: null,
    projectName: '',
    currentComponent: null,
    masterJson: null,
    componentStatuses: {
      gab_gen: 'pending',
      vsai_rectifier: 'pending',
      esai_engine: 'pending',
      elia_engine: 'pending',
    },
    outputs: {}
  })
}));
