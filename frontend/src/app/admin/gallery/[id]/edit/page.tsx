"use client"
import { useEffect, useState } from 'react'
import { galleryApi } from '@/lib/api/gallery'
import { AdminProjectForm } from '@/components/admin/AdminProjectForm'

export default function EditProjectPage({ params }: { params: { id: string } }) {
  const [project, setProject] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    galleryApi.getAdminProject(params.id)
      .then(setProject)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [params.id])

  if (loading) return <div>Loading...</div>
  if (!project) return <div>Project not found</div>

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Edit Gallery Project</h1>
        <p className="text-muted-foreground mt-1">Update details for {project.title}.</p>
      </div>
      <AdminProjectForm initialData={project} />
    </div>
  )
}
