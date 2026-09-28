import { apiClient } from './client';

export const contactApi = {
  submitForm: async (data: any) => {
    const response = await apiClient.post('/contact', data);
    return response.data;
  },
  
  // Admin
  getMessages: async () => {
    const response = await apiClient.get('/admin/messages');
    return response.data;
  },
  markRead: async (id: string) => {
    const response = await apiClient.patch(`/admin/messages/${id}/read`);
    return response.data;
  },
  markUnread: async (id: string) => {
    const response = await apiClient.patch(`/admin/messages/${id}/unread`);
    return response.data;
  },
  deleteMessage: async (id: string) => {
    const response = await apiClient.delete(`/admin/messages/${id}`);
    return response.data;
  }
};
