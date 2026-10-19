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

  confirmMissingInfo: async (
    masterJson: any,
    confirmedAnswers: Record<string, any>,
    projectId?: string
  ): Promise<{
    is_complete: boolean;
    master_json: any;
    missing_info_report: any;
    validation: any;
    vastu_analysis: VastuAnalysis | null;
  }> => {
    const response = await apiClient.post('/projects/vsai-rectifier/confirm-missing-info', {
      master_json: masterJson,
      confirmed_answers: confirmedAnswers,
      project_id: projectId,
    });
    return response.data;
  },

  rectify: async (projectId?: string, masterJson?: any): Promise<any> => {
    const url = projectId ? `/projects/${projectId}/vsai-rectifier/rectify` : '/projects/vsai-rectifier/rectify';
    const payload = masterJson ? { master_json: masterJson, project_id: projectId } : {};
    const response = await apiClient.post(url, payload);
    return response.data;
  },
};
