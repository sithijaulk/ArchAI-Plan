import { apiClient } from './client';

export const eliaApi = {
  run: async (projectId: string, payload?: unknown): Promise<never> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/run`, payload ?? {});
    return response.data;
  },
};
