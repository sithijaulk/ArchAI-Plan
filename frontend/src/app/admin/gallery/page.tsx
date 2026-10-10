"use client"
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { galleryApi } from '@/lib/api/gallery'
import { Button } from '@/components/ui/button'
import { Edit, Eye, Plus, Trash2 } from 'lucide-react'

export default function AdminGalleryPage() {
  const [projects, setProjects] = useState<any[]>([])

  const fetchProjects = async () => {
    try {
      const data = await galleryApi.getAdminProjects()
      setProjects(data.items || data)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    fetchProjects()
  }, [])

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this project?')) {
      await galleryApi.deleteProject(id)
      fetchProjects()
    }
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Gallery Projects</h1>
          <p className="text-muted-foreground mt-1">Manage public research gallery items.</p>
        </div>
        <Link href="/admin/gallery/new">
          <Button className="electric-glow">
            <Plus className="w-4 h-4 mr-2" /> Add Project
          </Button>
        </Link>
      </div>

      <div className="bg-card border border-border/50 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-b border-border/50">
              <tr>
                <th className="px-6 py-4 font-medium">Project</th>
                <th className="px-6 py-4 font-medium">Status</th>
                <th className="px-6 py-4 font-medium">Category</th>
                <th className="px-6 py-4 font-medium">Date</th>
                <th className="px-6 py-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {projects && projects.length > 0 ? projects.map((project) => (
                <tr key={project.id} className="bg-card border-b border-border/50 hover:bg-muted/20">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-4">
                      {project.cover_image_url ? (
                        <img src={project.cover_image_url} alt="" className="w-10 h-10 rounded object-cover border border-border/50" />
                      ) : (
                        <div className="w-10 h-10 rounded bg-muted border border-border/50"></div>
                      )}
                      <div>
                        <div className="font-semibold text-foreground">{project.title}</div>
                        <div className="text-xs text-muted-foreground">{project.slug}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    {project.published ? (
                      <span className="inline-flex items-center gap-1.5 py-1 px-2 rounded-md text-xs font-medium bg-green-500/10 text-green-500">Live</span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 py-1 px-2 rounded-md text-xs font-medium bg-yellow-500/10 text-yellow-500">Draft</span>
                    )}
                    {project.featured && (
                      <span className="inline-flex items-center gap-1.5 py-1 px-2 rounded-md text-xs font-medium bg-primary/10 text-primary ml-2">Featured</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">
                    {project.category || '-'}
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">
                    {new Date(project.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link href={`/gallery/${project.slug}`} target="_blank">
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
                          <Eye className="w-4 h-4" />
                        </Button>
                      </Link>
                      <Link href={`/admin/gallery/${project.id}/edit`}>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-primary">
                          <Edit className="w-4 h-4" />
                        </Button>
                      </Link>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => handleDelete(project.id)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                    No projects found. Click 'Add Project' to create one.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
