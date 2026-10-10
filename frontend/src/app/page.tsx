"use client"
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { galleryApi } from '@/lib/api/gallery'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ArrowRight, Map, Home, Box, TreePine, ImageIcon } from "lucide-react"
import dynamic from 'next/dynamic'

const ArchitecturalScene = dynamic(() => import('@/components/visualization/ArchitecturalScene'), {
  ssr: false,
  loading: () => <div className="w-full h-full min-h-[400px] flex items-center justify-center bg-muted/20 border border-border/50 rounded-xl">Loading Spatial Model...</div>
})

export default function HomePage() {
  const [featuredProjects, setFeaturedProjects] = useState<any[]>([])

  useEffect(() => {
    galleryApi.getPublicProjects().then(data => {
      const items = data.items || data
      const featured = items.filter((p: any) => p.featured).slice(0, 3)
      setFeaturedProjects(featured)
    }).catch(console.error)
  }, [])

  return (
    <div className="flex flex-col min-h-screen">
      {/* SECTION A — HERO */}
      <section className="relative pt-32 pb-20 md:pt-48 md:pb-32 overflow-hidden border-b border-border/50">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/10 via-background to-background z-0"></div>
        <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-primary/30 to-transparent"></div>
        
        <div className="container px-4 relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-secondary/50 border border-border/50 text-xs font-mono text-muted-foreground mb-6">
                <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                ArchAI-Plan v2.0 Platform
              </div>
              <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6 leading-[1.1]">
                From Land Geometry to <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-blue-400">Intelligent</span> Living Spaces.
              </h1>
              <p className="text-xl text-muted-foreground mb-10 max-w-2xl leading-relaxed">
                ArchAI-Plan is a multi-agent spatial AI architecture designed to transform residential spatial information into structured, optimized and interactive architectural outputs.
              </p>
              
              <div className="flex flex-wrap gap-4">
                <Link href="/features">
                  <Button size="lg" className="h-12 px-8 electric-glow text-base">
                    Explore Features <ArrowRight className="ml-2 w-5 h-5" />
                  </Button>
                </Link>
                <Link href="/start">
                  <Button size="lg" variant="outline" className="h-12 px-8 border-border/50 hover:bg-muted/50 text-base">
                    Start a Project
                  </Button>
                </Link>
              </div>
            </div>

            <div className="relative h-[400px] lg:h-[600px] w-full rounded-2xl border border-border/50 bg-black/20 overflow-hidden backdrop-blur-sm">
              <ArchitecturalScene />
            </div>
          </div>
        </div>
      </section>

      {/* SECTION B — PLATFORM OVERVIEW */}
      <section className="py-24 bg-muted/20">
        <div className="container px-4">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">One Connected Workflow</h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">Non-destructive propagation through four specialized AI engines.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            {[
              { num: '01', title: 'Understand Spatial Geometry' },
              { num: '02', title: 'Rectify Structural Constraints' },
              { num: '03', title: 'Optimize Interior Ergonomics' },
              { num: '04', title: 'Generate Eco-Spatial Landscapes' }
            ].map((step, i) => (
              <div key={i} className="relative p-6 bg-card border border-border/50 rounded-xl overflow-hidden group hover:border-primary/50 transition-colors">
                <div className="text-5xl font-bold text-muted/30 absolute -right-2 -top-2 group-hover:text-primary/10 transition-colors">{step.num}</div>
                <h3 className="text-lg font-semibold relative z-10">{step.title}</h3>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* SECTION C — FEATURES */}
      <section className="py-24 container px-4">
        <div className="text-center mb-16">
          <h2 className="text-3xl font-bold mb-4">Four Spatial Engines</h2>
          <p className="text-muted-foreground">Specialized AI agents working in harmony.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FeatureCard 
            title="GAB-Gen"
            subtitle="Geo-Spatial AI Blueprint Generator"
            desc="Processes land/deed spatial information and produces baseline residential spatial geometry."
            icon={<Map className="h-8 w-8 text-primary" />}
            href="/features/gab-gen"
          />
          <FeatureCard 
            title="VSAI-Rectifier"
            subtitle="Vastu Structural AI Rectifier"
            desc="Evaluates and rectifies structural spatial geometry using cultural and geometric constraints."
            icon={<Home className="h-8 w-8 text-primary" />}
            href="/features/vsai-rectifier"
          />
          <FeatureCard 
            title="ESAI-Engine"
            subtitle="Ergonomic Spatial Intelligence AI"
            desc="Optimizes furniture and interior asset placement using ergonomic clearance and spatial constraints."
            icon={<Box className="h-8 w-8 text-primary" />}
            href="/features/esai-engine"
          />
          <FeatureCard 
            title="ELIA-Engine"
            subtitle="Eco-Spatial Landscape Intelligence AI"
            desc="Generates exterior spatial planning including access, safety zoning, shading and adaptive greenery."
            icon={<TreePine className="h-8 w-8 text-primary" />}
            href="/features/elia-engine"
          />
        </div>
      </section>

      {/* SECTION D — WHY ARCHAI-PLAN */}
      <section className="py-24 bg-card/30 border-y border-border/40">
        <div className="container px-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-3xl font-bold mb-6">Why ArchAI-Plan</h2>
              <p className="text-muted-foreground text-lg mb-8">
                Designed for precision and scalability, our multi-agent architecture ensures every stage of design is data-driven and structurally sound.
              </p>
              <ul className="space-y-4">
                {[
                  "Vector-first spatial representation",
                  "Centralized Master JSON",
                  "Non-destructive data propagation",
                  "Human-centered spatial intelligence",
                  "Modular AI architecture",
                  "2D/3D-ready structured outputs"
                ].map((item, i) => (
                  <li key={i} className="flex items-center">
                    <div className="mr-4 h-2 w-2 rounded-full bg-primary"></div>
                    <span className="text-foreground">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="relative aspect-square md:aspect-video rounded-xl overflow-hidden border border-border bg-background flex items-center justify-center">
              <div className="absolute inset-0 opacity-20 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
              <Box className="h-32 w-32 text-primary/40" />
            </div>
          </div>
        </div>
      </section>
      
      {/* SECTION E — GALLERY PREVIEW */}
      <section className="py-24 container px-4">
        <div className="flex flex-col md:flex-row justify-between items-end mb-12">
          <div>
            <h2 className="text-3xl font-bold mb-4">Featured Research</h2>
            <p className="text-muted-foreground">Recent spatial outputs generated by our framework.</p>
          </div>
          <Link href="/gallery" className="mt-4 md:mt-0 text-primary font-medium hover:underline inline-flex items-center">
            View All Projects <ArrowRight className="w-4 h-4 ml-1" />
          </Link>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {featuredProjects.map((project) => (
            <Link key={project.id} href={`/gallery/${project.slug}`}>
              <Card className="h-full overflow-hidden flex flex-col group bg-card/40 hover:bg-card/60 transition-all border-border/50 hover:border-primary/50">
                <div className="aspect-[4/3] bg-muted relative overflow-hidden">
                  {project.cover_image_url ? (
                    <img 
                      src={project.cover_image_url} 
                      alt={project.title} 
                      className="object-cover w-full h-full group-hover:scale-105 transition-transform duration-500"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-card">
                      <ImageIcon className="w-12 h-12 text-muted-foreground/30" />
                    </div>
                  )}
                  <div className="absolute top-4 left-4">
                    <Badge variant="default" className="bg-primary text-primary-foreground">Featured</Badge>
                  </div>
                </div>
                <CardContent className="p-6 flex-1 flex flex-col">
                  <div className="flex items-center justify-between mb-3">
                    <Badge variant="outline" className="text-xs">{project.category || 'Uncategorized'}</Badge>
                    {project.project_date && <span className="text-xs text-muted-foreground">{project.project_date}</span>}
                  </div>
                  <h3 className="text-xl font-bold mb-2 group-hover:text-primary transition-colors">{project.title}</h3>
                  <p className="text-muted-foreground text-sm line-clamp-2 mb-4">
                    {project.short_description || project.description}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
          
          {featuredProjects.length === 0 && (
            <div className="col-span-3 text-center py-12 text-muted-foreground border border-dashed border-border/50 rounded-xl">
              No featured projects available yet.
            </div>
          )}
        </div>
      </section>

      {/* SECTION F — CTA */}
      <section className="py-32 text-center container px-4 relative">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-primary/10 via-background to-background"></div>
        <h2 className="text-4xl font-bold mb-6">Explore the ArchAI-Plan Workflow</h2>
        <p className="text-muted-foreground mb-10 max-w-xl mx-auto text-lg">
          Experience the future of residential spatial planning through our modular, intelligent research platform.
        </p>
        <div className="flex flex-col sm:flex-row justify-center gap-4">
          <Link href="/start">
            <Button size="lg" className="electric-glow h-12 px-8">Start Project</Button>
          </Link>
          <Link href="/features">
            <Button size="lg" variant="outline" className="h-12 px-8">View Features</Button>
          </Link>
        </div>
      </section>
    </div>
  )
}

function FeatureCard({ title, subtitle, desc, icon, href }: { title: string, subtitle: string, desc: string, icon: React.ReactNode, href: string }) {
  return (
    <Card className="flex flex-col h-full bg-card/50 backdrop-blur border-border/50 hover:border-primary/50 transition-all hover:-translate-y-1 duration-300">
      <CardHeader>
        <div className="mb-4 bg-primary/10 w-16 h-16 rounded-xl flex items-center justify-center">
          {icon}
        </div>
        <CardTitle className="text-2xl">{title}</CardTitle>
        <CardDescription className="text-primary font-medium">{subtitle}</CardDescription>
      </CardHeader>
      <CardContent className="flex-1">
        <p className="text-muted-foreground">{desc}</p>
      </CardContent>
      <div className="p-6 pt-0 mt-auto">
        <Link href={href} className="inline-block w-full">
          <Button variant="secondary" className="w-full group">
            Explore Feature <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
          </Button>
        </Link>
      </div>
    </Card>
  )
}
