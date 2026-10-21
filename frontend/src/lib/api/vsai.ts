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

  segmentFloorPlan: async (
    file: File,
    scaleFt?: number,
    projectId?: string
  ): Promise<{
    master_json: any;
    validation: any;
    vastu_analysis: VastuAnalysis | null;
    segmentation: {
      source: string;
      rooms_detected: number;
      doors_detected: number;
      windows_detected: number;
      average_confidence: number;
      original_image_size: [number, number];
      scale_factor_ft_per_px: number;
    };
  }> => {
    const formData = new FormData();
    formData.append('file', file);
    if (scaleFt) {
      formData.append('scale_ft', scaleFt.toString());
    }

    const url = projectId ? `/projects/${projectId}/vsai-rectifier/segment` : '/projects/vsai-rectifier/segment';
    const response = await apiClient.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

