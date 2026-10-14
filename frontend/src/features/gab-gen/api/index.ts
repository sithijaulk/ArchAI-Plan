import { apiClient } from '@/lib/api/client';
import {
  ClientRequirements,
  ManualSurveyData,
  GabGenMasterJson,
} from '../types';

export const gabGenExtendedApi = {
  getContext: async (projectId: string) => {
    const res = await apiClient.get(`/projects/${projectId}/gab-gen/context`);
    return res.data;
  },

  uploadSurvey: async (projectId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/upload-survey`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  },

  saveRequirements: async (projectId: string, req: ClientRequirements) => {
    const res = await apiClient.put(`/projects/${projectId}/gab-gen/requirements`, req);
    return res.data;
  },

  saveManualSurveyData: async (projectId: string, data: ManualSurveyData) => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/manual-survey-data`, data);
    return res.data;
  },

  validateLand: async (projectId: string, data?: ManualSurveyData) => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/validate-land`, data || null);
    return res.data;
  },

  generate: async (projectId: string): Promise<GabGenMasterJson> => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/generate`);
    return res.data;
  },

  getResult: async (projectId: string): Promise<GabGenMasterJson> => {
    const res = await apiClient.get(`/projects/${projectId}/gab-gen/result`);
    return res.data;
  },

  getMasterJson: async (projectId: string): Promise<GabGenMasterJson> => {
    const res = await apiClient.get(`/projects/${projectId}/gab-gen/master-json`);
    return res.data;
  },
};
