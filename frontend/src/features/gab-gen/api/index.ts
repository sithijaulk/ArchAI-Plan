import { apiClient } from '@/lib/api/client';
import {
  ClientRequirements,
  ManualSurveyData,
  GabGenMasterJson,
  GabGenRunOutput,
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

  removeSurveyFile: async (projectId: string) => {
    const res = await apiClient.delete(`/projects/${projectId}/gab-gen/survey-file`);
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

  getRegulatoryRules: async (allowResearchTest: boolean = false) => {
    const res = await apiClient.get(`/projects/dummy/gab-gen/regulatory-rules?allow_research_test=${allowResearchTest}`);
    return res.data;
  },

  loadTestFixture: async (projectId: string, fixtureName: string = 'standard_10_perch') => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/load-test-fixture?fixture_name=${fixtureName}`);
    return res.data;
  },

  generate: async (projectId: string, devTestMode: boolean = false): Promise<GabGenRunOutput> => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/generate?dev_test_mode=${devTestMode}`);
    return res.data;
  },

  getResult: async (projectId: string): Promise<GabGenMasterJson> => {
    const res = await apiClient.get(`/projects/${projectId}/gab-gen/result`);
    return res.data;
  },

  extractSurvey: async (projectId: string) => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/extract-survey`);
    return res.data;
  },

  editRoom: async (projectId: string, payload: { room_id: string; target_floor_id: string; polygon: { x: number; y: number }[] }) => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/edit-room`, payload);
    return res.data;
  },

  removeRoom: async (projectId: string, roomId: string) => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/remove-room`, { room_id: roomId });
    return res.data;
  },

  addRoom: async (projectId: string, targetFloorId: string, roomData: any) => {
    const res = await apiClient.post(`/projects/${projectId}/gab-gen/add-room`, {
      target_floor_id: targetFloorId,
      room_data: roomData,
    });
    return res.data;
  },

  getMasterJson: async (projectId: string): Promise<GabGenMasterJson> => {
    const res = await apiClient.get(`/projects/${projectId}/gab-gen/master-json`);
    return res.data;
  },
};

