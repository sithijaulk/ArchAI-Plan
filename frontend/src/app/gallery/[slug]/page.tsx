"use client"
import { notFound } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { galleryApi } from '@/lib/api/gallery'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ArrowLeft, ImageIcon, Calendar, Tag, Layers } from 'lucide-react'

export default function GalleryProjectPage({ params }: { params: { slug: string } }) {
  const [project, setProject] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    galleryApi.getPublicProject(params.slug)
      .then(setProject)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [params.slug])

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  if (!project) return notFound()

  const images = project.gallery_images?.sort((a: any, b: any) => a.sort_order - b.sort_order) || []

  return (
    <div className="min-h-screen pb-24">
      {/* Hero Section */}
      <div className="w-full h-[50vh] md:h-[70vh] bg-muted relative">
        {project.cover_image_url ? (
          <img 
            src={project.cover_image_url} 
            alt={project.title} 
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-card">
            <ImageIcon className="w-24 h-24 text-muted-foreground/20" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent"></div>
        
        <div className="absolute bottom-0 left-0 w-full p-8 md:p-16 container">
          <Link href="/gallery" className="inline-flex items-center text-muted-foreground hover:text-white mb-6 transition-colors">
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Gallery
          </Link>
          <div className="flex flex-wrap gap-2 mb-4">
            {project.category && <Badge variant="default" className="bg-primary">{project.category}</Badge>}
            {project.featured && <Badge variant="secondary">Featured Research</Badge>}
          </div>
          <h1 className="text-4xl md:text-6xl font-bold text-white mb-4">{project.title}</h1>
          {project.short_description && (
            <p className="text-xl text-muted-foreground max-w-3xl">{project.short_description}</p>
          )}
        </div>
      </div>

      <div className="container px-4 pt-16">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-16">
          {/* Main Content */}
          <div className="lg:col-span-2">
            <div className="prose prose-invert prose-lg max-w-none mb-16 whitespace-pre-wrap">
              {project.description || "No detailed description provided."}
            </div>

            {/* Additional Images */}
            {images.length > 0 && (
              <div className="space-y-8">
                <h3 className="text-2xl font-bold border-b border-border/50 pb-4">Project Gallery</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {images.map((img: any) => (
                    <div key={img.id} className="bg-muted rounded-xl overflow-hidden aspect-video relative border border-border/50">
                      <img src={img.image_url} alt={img.alt_text || project.title} className="w-full h-full object-cover hover:scale-105 transition-transform duration-500" />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-8">
            <div className="bg-card/40 border border-border/50 rounded-xl p-6">
              <h4 className="font-semibold text-lg mb-6 border-b border-border/50 pb-2">Project Details</h4>
              
              <div className="space-y-4">
                {project.project_date && (
                  <div className="flex items-start gap-3">
                    <Calendar className="w-5 h-5 text-primary shrink-0" />
                    <div>
                      <span className="block text-sm text-muted-foreground">Date</span>
                      <span className="font-medium">{project.project_date}</span>
                    </div>
                  </div>
                )}
                
                {project.category && (
                  <div className="flex items-start gap-3">
                    <Layers className="w-5 h-5 text-primary shrink-0" />
                    <div>
                      <span className="block text-sm text-muted-foreground">Category</span>
                      <span className="font-medium">{project.category}</span>
                    </div>
                  </div>
                )}
                
                {project.tags && project.tags.length > 0 && (
                  <div className="flex items-start gap-3">
                    <Tag className="w-5 h-5 text-primary shrink-0" />
                    <div>
                      <span className="block text-sm text-muted-foreground mb-1">Tags</span>
                      <div className="flex flex-wrap gap-1">
                        {project.tags.map((tag: string) => (
                          <Badge key={tag} variant="outline" className="text-xs bg-background/50">{tag}</Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {project.related_components && project.related_components.length > 0 && (
              <div className="bg-card/40 border border-border/50 rounded-xl p-6">
                <h4 className="font-semibold text-lg mb-4">Utilized Engines</h4>
                <div className="flex flex-col gap-2">
                  {project.related_components.map((comp: string) => (
                    <div key={comp} className="p-3 bg-background rounded-lg text-sm font-medium border border-border/50 flex items-center justify-between">
                      {comp}
                      <Link href={`/features/${comp.toLowerCase().replace(' ', '-')}`}>
                        <Button variant="ghost" size="sm" className="h-6 text-xs text-primary">View</Button>
                      </Link>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
