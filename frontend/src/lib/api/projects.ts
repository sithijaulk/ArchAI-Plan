import { apiClient } from './client';
import { MasterJson } from '@/types/master-json';
import { Project, ProjectCreate, ProjectUpdate } from '@/types/project';

export const projectsApi = {
  getProject: async (projectId: string): Promise<Project> => {
    const response = await apiClient.get(`/projects/${projectId}`);
    return response.data;
  },
  
  createProject: async (data: ProjectCreate): Promise<Project> => {
    const response = await apiClient.post('/projects', data);
    return response.data;
  },
  
  updateProject: async (projectId: string, data: ProjectUpdate): Promise<Project> => {
    const response = await apiClient.put(`/projects/${projectId}`, data);
    return response.data;
  },

  skipComponent: async (projectId: string, component: string): Promise<{ component: string; status: string; master_json: MasterJson }> => {
    const response = await apiClient.post(`/projects/${projectId}/skip/${component}`);
    return response.data;
  }
};
