import { apiClient } from './client';
import { VastuAnalysis } from '@/types/project';

export const vsaiApi = {
  run: async (projectId: string, payload?: unknown): Promise<any> => {
    const response = await apiClient.post(`/projects/${projectId}/vsai-rectifier/run`, payload ?? {});
    return response.data;
  },

  getVastuAnalysis: async (projectId: string): Promise<VastuAnalysis> => {
    const response = await apiClient.get(`/projects/${projectId}/vastu-analysis`);
    return response.data;
  },

  evaluateVastuDirect: async (masterJson: any): Promise<VastuAnalysis> => {
    const response = await apiClient.post('/projects/vastu-analysis', masterJson);
    return response.data;
  },

  getVastuRules: async (): Promise<{ rules: any[] }> => {
    const response = await apiClient.get('/projects/vastu-rules');
    return response.data;
  },
};
