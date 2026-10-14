import { apiClient } from './client';

export const eliaApi = {
  run: async (projectId: string, payload?: unknown): Promise<any> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/run`, payload ?? {});
    return response.data;
  },
};
