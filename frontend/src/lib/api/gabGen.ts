import { apiClient } from './client';

export const gabGenApi = {
  run: async (projectId: string, payload?: unknown): Promise<never> => {
    const response = await apiClient.post(`/projects/${projectId}/gab-gen/run`, payload ?? {});
    return response.data;
  },
};
