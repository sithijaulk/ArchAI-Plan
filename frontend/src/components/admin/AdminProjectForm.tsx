"use client"
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { galleryApi } from '@/lib/api/gallery'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { ImageIcon, X } from 'lucide-react'

export function AdminProjectForm({ initialData }: { initialData?: any }) {
  const router = useRouter()
  const isEdit = !!initialData
  
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [formData, setFormData] = useState({
    title: initialData?.title || '',
    slug: initialData?.slug || '',
    short_description: initialData?.short_description || '',
    description: initialData?.description || '',
    category: initialData?.category || '',
    tags: initialData?.tags?.join(', ') || '',
    related_components: initialData?.related_components || [],
    project_date: initialData?.project_date || '',
    featured: initialData?.featured || false,
    published: initialData?.published || false,
    cover_image_url: initialData?.cover_image_url || ''
  })
  const [coverFile, setCoverFile] = useState<File | null>(null)

  const availableComponents = ['GAB-Gen', 'VSAI-Rectifier', 'ESAI-Engine', 'ELIA-Engine']

  const handleToggleComponent = (comp: string) => {
    setFormData(prev => {
      const exists = prev.related_components.includes(comp)
      if (exists) {
        return { ...prev, related_components: prev.related_components.filter((c: string) => c !== comp) }
      }
      return { ...prev, related_components: [...prev.related_components, comp] }
    })
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target
    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked
      setFormData(prev => ({ ...prev, [name]: checked }))
    } else {
      setFormData(prev => ({ ...prev, [name]: value }))
    }
  }

  const handleCoverUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCoverFile(file)
    const previewUrl = URL.createObjectURL(file)
    setFormData(prev => ({ ...prev, cover_image_url: previewUrl }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    
    const payload = {
      ...formData,
      tags: formData.tags.split(',').map((t: string) => t.trim()).filter((t: string) => t.length > 0)
    }

    try {
      let projectId = initialData?.id
      if (isEdit) {
        await galleryApi.updateProject(projectId, payload)
      } else {
        const newProj = await galleryApi.createProject(payload)
        projectId = newProj.id
      }
      
      if (coverFile && projectId) {
        await galleryApi.uploadImage(projectId, coverFile, 'cover')
      }
      
      router.push('/admin/gallery')
      router.refresh()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save project')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {error && <div className="p-4 bg-destructive/10 text-destructive rounded-md border border-destructive/20">{error}</div>}
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Project Title *</Label>
                <Input id="title" name="title" value={formData.title} onChange={handleChange} required />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="slug">Slug (URL identifier) *</Label>
                <Input id="slug" name="slug" value={formData.slug} onChange={handleChange} required />
                <p className="text-xs text-muted-foreground">Unique string, no spaces. e.g. villa-nova-project</p>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="short_description">Short Description</Label>
                <Textarea id="short_description" name="short_description" rows={2} value={formData.short_description} onChange={handleChange} />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="description">Full Description</Label>
                <Textarea id="description" name="description" rows={6} value={formData.description} onChange={handleChange} />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="category">Category</Label>
                  <Input id="category" name="category" value={formData.category} onChange={handleChange} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="project_date">Project Date</Label>
                  <Input id="project_date" name="project_date" type="date" value={formData.project_date} onChange={handleChange} />
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="tags">Tags (comma separated)</Label>
                <Input id="tags" name="tags" value={formData.tags} onChange={handleChange} placeholder="Residential, Concept, AI" />
              </div>
              
              <div className="space-y-2 pt-2">
                <Label>Related Components</Label>
                <div className="flex flex-wrap gap-2 mt-2">
                  {availableComponents.map(comp => (
                    <div 
                      key={comp}
                      onClick={() => handleToggleComponent(comp)}
                      className={`px-3 py-1 text-xs rounded-full border cursor-pointer transition-colors ${
                        formData.related_components.includes(comp) 
                          ? 'bg-primary text-primary-foreground border-primary' 
                          : 'bg-transparent text-muted-foreground border-border hover:border-foreground/50'
                      }`}
                    >
                      {comp}
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
        
        <div className="lg:col-span-1 space-y-6">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <Label>Visibility & Status</Label>
              <div className="flex items-center space-x-2 pt-2">
                <input 
                  type="checkbox" 
                  id="published" 
                  name="published" 
                  checked={formData.published} 
                  onChange={handleChange}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <Label htmlFor="published" className="font-normal cursor-pointer">Published (Public)</Label>
              </div>
              <div className="flex items-center space-x-2 pt-2">
                <input 
                  type="checkbox" 
                  id="featured" 
                  name="featured" 
                  checked={formData.featured} 
                  onChange={handleChange}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <Label htmlFor="featured" className="font-normal cursor-pointer">Featured Project</Label>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-6 space-y-4">
              <Label>Cover Image</Label>
              
              {formData.cover_image_url ? (
                <div className="relative aspect-video rounded-md overflow-hidden border border-border">
                  <img src={formData.cover_image_url} alt="Cover" className="w-full h-full object-cover" />
                  <button 
                    type="button"
                    onClick={() => {
                      setFormData(prev => ({ ...prev, cover_image_url: '' }))
                      setCoverFile(null)
                    }}
                    className="absolute top-2 right-2 bg-black/50 text-white p-1 rounded-full hover:bg-black"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="border-2 border-dashed border-border rounded-md p-6 text-center">
                  <ImageIcon className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                  <p className="text-xs text-muted-foreground mb-4">Upload a cover image</p>
                  <Input type="file" accept="image/*" onChange={handleCoverUpload} className="w-full text-xs" />
                </div>
              )}
            </CardContent>
          </Card>

          <Button type="submit" className="w-full electric-glow" disabled={loading}>
            {loading ? 'Saving...' : isEdit ? 'Update Project' : 'Create Project'}
          </Button>
          <Button type="button" variant="outline" className="w-full mt-2" onClick={() => router.back()}>
            Cancel
          </Button>
        </div>
      </div>
    </form>
  )
}
