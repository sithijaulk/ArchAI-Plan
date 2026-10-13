"use client"
/**
 * EliaOutputWrapper — ELIA-owned presentation wrapper.
 *
 * Encapsulates:
 *   - Derivation of in-memory EliaViewModel from upstream Master JSON and ELIA candidate output.
 *   - Preservation of source revisions and single-time unit normalization.
 *   - Dynamic SSR-safe loading of Three.js exterior viewer and SVG 2D plan renderer.
 *   - Clear distinction between Accepted Design (saved in Master JSON), Candidate Preview (unsaved),
 *     and Infeasible Candidates (unaccepted).
 *   - Standard tabs (2D Plan, 3D Scene, Raw JSON) with distinct Master JSON and Landscape JSON exports.
 *
 * Keeps all ELIA contract handling and props strictly isolated from shared output components.
 */
import React, { useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from '@/components/output/DownloadButtons'
import { FileJson, Layers, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'
import type { ExteriorLandscape, ExteriorValidation } from '@/types/elia'
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

export interface EliaOutputWrapperProps {
  projectName: string
  projectId?: string
  masterJson: any
  data?: unknown
  isProcessing?: boolean
  runError?: string
  viewStatus?: 'accepted' | 'preview' | 'infeasible'
  sourceRevision?: number | null
  generationMode?: string
  acceptedData?: unknown
  activeView?: 'candidate' | 'accepted'
  onToggleView?: (view: 'candidate' | 'accepted') => void
  validationSummary?: ExteriorValidation | null
}

export function EliaOutputWrapper({
  projectName,
  projectId,
  masterJson,
  data,
  isProcessing,
  runError,
  viewStatus = 'accepted',
  sourceRevision,
  generationMode,
  acceptedData,
  activeView = 'candidate',
  onToggleView,
  validationSummary,
}: EliaOutputWrapperProps) {
  const [jsonViewTab, setJsonViewTab] = useState<'landscape' | 'master'>('landscape')

  const landscape = data ? (data as ExteriorLandscape) : null

  // Authoritative ELIA view model derived from Master JSON and landscape
  const viewModel = useMemo(() => {
    return extractNormalizedUpstreamGeometry(masterJson, landscape, projectId)
  }, [masterJson, landscape, projectId])

  const hasBothVersions = Boolean(acceptedData && data && acceptedData !== data)

  // Download handler for authoritative Master JSON
  const handleDownloadMasterJson = () => {
    if (!masterJson) return
    const blob = new Blob([JSON.stringify(masterJson, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${projectName || 'project'}_authoritative_master.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      {/* Top Header Actions & Status Badges */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-xl font-bold">Landscape Visualization</h3>
            {viewStatus === 'accepted' && (
              <Badge variant="outline" className="bg-emerald-950/60 text-emerald-400 border-emerald-500/40 text-[11px] gap-1">
                <CheckCircle2 className="w-3 h-3" /> Accepted Design (Saved)
              </Badge>
            )}
            {viewStatus === 'preview' && (
              <Badge variant="outline" className="bg-amber-950/60 text-amber-300 border-amber-500/40 text-[11px] gap-1">
                <AlertTriangle className="w-3 h-3" /> Candidate Preview (Unsaved)
              </Badge>
            )}
            {viewStatus === 'infeasible' && (
              <Badge variant="outline" className="bg-rose-950/60 text-rose-300 border-rose-500/40 text-[11px] gap-1">
                <XCircle className="w-3 h-3" /> Infeasible Candidate (Unaccepted)
              </Badge>
            )}
            {sourceRevision !== undefined && sourceRevision !== null && (
              <span className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                rev {sourceRevision}
              </span>
            )}
            {generationMode && (
              <span className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                mode: {generationMode}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {projectName ? `${projectName} · ` : ''}Eco-Spatial Landscape Intelligence
          </p>
        </div>

        {/* Export Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
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
            filename={`${projectName || 'project'}_elia_${viewStatus}.json`}
            data={data}
            disabled={!data}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownloadMasterJson}
            disabled={!masterJson}
            title="Download full project Master JSON with exterior landscape layer"
          >
            <FileJson className="w-4 h-4 mr-2 text-primary" /> Master JSON
          </Button>
        </div>
      </div>

      {/* Version Switching Controls when candidate and accepted both exist */}
      {hasBothVersions && onToggleView && (
        <div className="flex items-center justify-between p-2.5 rounded-lg border border-border bg-card/60 text-xs">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary" />
            <span className="text-muted-foreground">Multiple design versions available:</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant={activeView === 'candidate' ? 'default' : 'outline'}
              className="h-7 text-xs px-2.5"
              onClick={() => onToggleView('candidate')}
            >
              Current Candidate {viewStatus === 'preview' ? '(Unsaved)' : ''}
            </Button>
            <Button
              size="sm"
              variant={activeView === 'accepted' ? 'default' : 'outline'}
              className="h-7 text-xs px-2.5"
              onClick={() => onToggleView('accepted')}
            >
              Saved Accepted Design
            </Button>
          </div>
        </div>
      )}

      {/* Infeasible notice */}
      {viewStatus === 'infeasible' && (
        <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-950/20 text-rose-200 text-xs space-y-1">
          <div className="font-semibold flex items-center gap-1.5 text-rose-300">
            <XCircle className="w-4 h-4 shrink-0" /> Candidate Layout Infeasible
          </div>
          <p className="text-rose-200/90 leading-relaxed">
            The requested exterior layout could not satisfy all spatial or boundary constraints. 
            The existing accepted exterior design in the project Master JSON has been kept intact and unmodified.
          </p>
          {validationSummary && validationSummary.violations && validationSummary.violations.length > 0 && (
            <ul className="list-disc pl-5 pt-1 space-y-0.5 text-rose-300/90 font-mono text-[11px]">
              {validationSummary.violations.map((violation, idx) => (
                <li key={idx}>{violation}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Tabs */}
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
          <div className="flex items-center justify-between mb-3 border-b border-border/60 pb-2">
            <div className="flex gap-2 text-xs">
              <Button
                variant={jsonViewTab === 'landscape' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setJsonViewTab('landscape')}
              >
                Exterior Landscape JSON ({viewStatus})
              </Button>
              <Button
                variant={jsonViewTab === 'master' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setJsonViewTab('master')}
              >
                Project Master JSON
              </Button>
            </div>
            <span className="text-[11px] font-mono text-muted-foreground">
              {jsonViewTab === 'landscape'
                ? data ? `${Object.keys(landscape?.access || {}).length} access elements` : 'No data'
                : masterJson ? `revision: ${sourceRevision ?? masterJson.revision ?? 1}` : 'No Master JSON'}
            </span>
          </div>

          <pre className="text-xs text-primary-foreground/90 font-mono whitespace-pre-wrap break-all leading-relaxed">
            {jsonViewTab === 'landscape'
              ? data
                ? JSON.stringify(data, null, 2)
                : '// No ELIA landscape output generated yet.\n// Click "Preview" or "Generate & Save" to run the exterior planner.'
              : masterJson
              ? JSON.stringify(masterJson, null, 2)
              : '// No project Master JSON loaded.'}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default EliaOutputWrapper
