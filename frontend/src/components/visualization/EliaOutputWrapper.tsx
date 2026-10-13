"use client"
/**
 * EliaOutputWrapper — ELIA-owned presentation wrapper.
 *
 * Encapsulates:
 *   - Derivation of in-memory EliaViewModel from upstream Master JSON and ELIA candidate output.
 *   - Preservation of source revisions and single-time unit normalization.
 *   - Dynamic SSR-safe loading of Three.js exterior viewer and SVG 2D plan renderer.
 *   - Standard tabs (2D Plan, 3D Scene, Raw JSON) with shared download actions.
 *
 * Keeps all ELIA contract handling and props strictly isolated from shared output components.
 */
import React, { useMemo, Suspense } from 'react'
import dynamic from 'next/dynamic'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from '@/components/output/DownloadButtons'
import type { ExteriorLandscape } from '@/types/elia'
import { extractNormalizedUpstreamGeometry } from '@/lib/eliaGeometry'

// Dynamically import Three.js components to prevent SSR hydration errors
const ExteriorSceneViewer = dynamic(
  () => import('@/components/visualization/ExteriorSceneViewer'),
  { ssr: false, loading: () => <LoadingPlaceholder label="Loading 3D Exterior Scene..." /> }
)

const EliaLandscape2D = dynamic(
  () => import('@/components/visualization/EliaLandscape2D'),
  { ssr: false, loading: () => <LoadingPlaceholder label="Loading 2D Plan View..." /> }
)

function LoadingPlaceholder({ label }: { label: string }) {
  return (
    <div className="w-full min-h-[480px] flex items-center justify-center bg-[#0a140a] rounded-lg">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        <span className="text-sm font-mono">{label}</span>
      </div>
    </div>
  )
}

interface EliaOutputWrapperProps {
  projectName: string
  projectId?: string
  masterJson: any
  data?: unknown
  isProcessing?: boolean
  runError?: string
}

export function EliaOutputWrapper({
  projectName,
  projectId,
  masterJson,
  data,
  isProcessing,
  runError,
}: EliaOutputWrapperProps) {
  const landscape = data ? (data as ExteriorLandscape) : null

  // Authoritative ELIA view model derived from Master JSON and landscape
  const viewModel = useMemo(() => {
    return extractNormalizedUpstreamGeometry(masterJson, landscape, projectId)
  }, [masterJson, landscape, projectId])

  return (
    <div className="space-y-4">
      {/* Top Header Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-bold">Landscape Visualization</h3>
          <p className="text-xs text-muted-foreground">
            {projectName ? `${projectName} · ` : ''}Eco-Spatial Landscape Intelligence
          </p>
        </div>
        <div className="flex gap-2">
          <DownloadImageButton
            filename={`${projectName || 'project'}_elia_plan.png`}
            targetId="elia-output-preview"
            disabled={!data}
          />
          <DownloadPdfButton
            filename={`${projectName || 'project'}_elia_plan.pdf`}
            targetId="elia-output-preview"
            disabled={!data}
          />
          <DownloadJsonButton
            filename={`${projectName || 'project'}_elia_landscape.json`}
            data={data}
            disabled={!data}
          />
        </div>
      </div>

      <Tabs defaultValue="2d" className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="2d">2D Plan View</TabsTrigger>
          <TabsTrigger value="3d">3D Exterior View</TabsTrigger>
          <TabsTrigger value="json">JSON Inspection</TabsTrigger>
        </TabsList>

        {/* 2D Plan View Tab */}
        <TabsContent
          value="2d"
          className="bg-card/50 border border-border p-4 rounded-xl min-h-[500px]"
          id="elia-output-preview"
        >
          {isProcessing ? (
            <LoadingPlaceholder label="Generating exterior spatial plan..." />
          ) : (
            <EliaLandscape2D viewModel={viewModel} landscape={landscape} />
          )}
        </TabsContent>

        {/* 3D Scene View Tab */}
        <TabsContent
          value="3d"
          className="bg-card/50 border border-border rounded-xl overflow-hidden min-h-[500px]"
        >
          {isProcessing ? (
            <LoadingPlaceholder label="Calculating 3D solar and spatial constraints..." />
          ) : (
            <ExteriorSceneViewer viewModel={viewModel} landscape={landscape} />
          )}
        </TabsContent>

        {/* JSON Inspector Tab */}
        <TabsContent
          value="json"
          className="bg-card/50 border border-border p-4 rounded-xl min-h-[500px] overflow-auto max-h-[640px]"
        >
          <pre className="text-xs text-primary-foreground/90 font-mono whitespace-pre-wrap break-all leading-relaxed">
            {data
              ? JSON.stringify(data, null, 2)
              : '// No ELIA component output generated yet.\n// Click "Generate Landscape" to run the exterior spatial planner.'}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default EliaOutputWrapper
