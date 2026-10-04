import { apiClient } from './client';

export const esaiApi = {
  run: async (projectId: string, payload?: unknown): Promise<never> => {
    const response = await apiClient.post(`/projects/${projectId}/esai-engine/run`, payload ?? {});
    return response.data;
  },
};
