import { apiClient } from './client';

export const settingsApi = {
  getPublic: async (): Promise<Record<string, string>> => {
    const response = await apiClient.get('/settings/public');
    return response.data;
  },
  getAdmin: async (): Promise<Record<string, string>> => {
    const response = await apiClient.get('/settings');
    return response.data;
  },
  update: async (values: Record<string, string>) => {
    const response = await apiClient.put('/settings/admin', values);
    return response.data;
  },
};
