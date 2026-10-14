import { apiClient } from './client'

export type TeamMember = {
  id?: string
  name: string
  role: string
  bio?: string
  sort_order: number
  image_url?: string | null
}

export const aboutApi = {
  getContent: async () => (await apiClient.get('/about/content')).data,
  getDocuments: async () => (await apiClient.get('/admin/about/documents')).data,
  uploadDocument: async (title: string, description: string, file: File) => {
    const data = new FormData()
    data.append('title', title)
    data.append('description', description)
    data.append('file', file)
    return (await apiClient.post('/admin/about/documents', data, { headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  deleteDocument: async (id: string) => apiClient.delete(`/admin/about/documents/${id}`),
  getMembers: async (): Promise<TeamMember[]> => (await apiClient.get('/admin/about/members')).data,
  saveMember: async (member: TeamMember, image?: File) => {
    const data = new FormData()
    data.append('name', member.name)
    data.append('role', member.role)
    data.append('bio', member.bio || '')
    data.append('sort_order', String(member.sort_order))
    if (image) data.append('image', image)
    const path = member.id ? `/admin/about/members/${member.id}` : '/admin/about/members'
    return (await apiClient.request({ method: member.id ? 'PUT' : 'POST', url: path, data, headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  deleteMember: async (id: string) => apiClient.delete(`/admin/about/members/${id}`),
}