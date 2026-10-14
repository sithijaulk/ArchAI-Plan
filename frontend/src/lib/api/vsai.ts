import { apiClient } from './client';

export const vsaiApi = {
  run: async (projectId: string, payload?: unknown): Promise<any> => {
    const response = await apiClient.post(`/projects/${projectId}/vsai-rectifier/run`, payload ?? {});
    return response.data;
  },
};
