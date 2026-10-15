"use client"
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Map, Home, Box, TreePine } from 'lucide-react'

export default function FeaturesPage() {
  return (
    <div className="container px-4 py-24 min-h-screen">
      <div className="text-center mb-16">
        <h1 className="text-4xl md:text-5xl font-bold mb-6">Four Intelligent Spatial Engines.<br/>One Connected Workflow.</h1>
        <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
          ArchAI-Plan modules can be used sequentially to build a complete architectural model, or independently for specific analysis tasks.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-6xl mx-auto">
        <FeatureCard 
          id="gab-gen"
          num="01"
          title="GAB-Gen: Geo-Spatial AI Blueprint Generator"
          desc="Processes land/deed spatial information and produces baseline residential spatial geometry."
          icon={<Map className="w-10 h-10 text-primary" />}
        />
        <FeatureCard 
          id="vsai-rectifier"
          num="02"
          title="VSAI-Rectifier: Vastu Structural AI Rectifier"
          desc="Evaluates and rectifies structural spatial geometry using cultural and geometric constraints."
          icon={<Home className="w-10 h-10 text-primary" />}
        />
        <FeatureCard 
          id="esai-engine"
          num="03"
          title="ESAI-Engine: Ergonomic Spatial Intelligence AI"
          desc="Optimizes furniture and interior asset placement using ergonomic clearance and spatial constraints."
          icon={<Box className="w-10 h-10 text-primary" />}
        />
        <FeatureCard 
          id="elia-engine"
          num="04"
          title="ELIA-Engine: Eco-Spatial Landscape Intelligence AI"
          desc="Generates exterior spatial planning including access, safety zoning, shading and adaptive greenery."
          icon={<TreePine className="w-10 h-10 text-primary" />}
        />
      </div>
    </div>
  )
}

function FeatureCard({ id, num, title, desc, icon }: any) {
  return (
    <Card className="flex flex-col bg-card/40 border-border/60 hover:border-primary/40 transition-colors">
      <CardHeader className="flex flex-row items-start gap-6 pb-2">
        <div className="p-4 bg-primary/10 rounded-2xl">
          {icon}
        </div>
        <div>
          <span className="text-sm font-bold text-primary mb-1 block">COMPONENT {num}</span>
          <CardTitle className="text-2xl leading-tight">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col pt-4">
        <p className="text-muted-foreground text-lg mb-8 flex-1">
          {desc}
        </p>
        <Link href={`/features/${id}`}>
          <Button variant="secondary" className="w-full">
            Open {title.split(':')[0]}
          </Button>
        </Link>
      </CardContent>
    </Card>
  )
}
