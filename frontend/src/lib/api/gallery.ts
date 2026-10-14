import { apiClient } from './client';

export const galleryApi = {
  // Public
  getPublicProjects: async () => {
    const response = await apiClient.get('/gallery');
    return response.data;
  },
  getPublicProject: async (slug: string) => {
    const response = await apiClient.get(`/gallery/${slug}`);
    return response.data;
  },
  
  // Admin
  getAdminProjects: async () => {
    const response = await apiClient.get('/admin/gallery');
    return response.data;
  },
  getAdminProject: async (id: string) => {
    const response = await apiClient.get(`/admin/gallery/${id}`);
    return response.data;
  },
  createProject: async (data: any) => {
    const response = await apiClient.post('/admin/gallery', data);
    return response.data;
  },
  updateProject: async (id: string, data: any) => {
    const response = await apiClient.put(`/admin/gallery/${id}`, data);
    return response.data;
  },
  deleteProject: async (id: string) => {
    const response = await apiClient.delete(`/admin/gallery/${id}`);
    return response.data;
  },
  uploadImage: async (id: string, file: File, type: 'cover' | 'gallery') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', type);
    const response = await apiClient.post(`/admin/gallery/${id}/images`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  }
};
