import { apiClient } from './client';

export const vsaiApi = {
  run: async (projectId: string, payload?: unknown): Promise<never> => {
    const response = await apiClient.post(`/projects/${projectId}/vsai-rectifier/run`, payload ?? {});
    return response.data;
  },
};
