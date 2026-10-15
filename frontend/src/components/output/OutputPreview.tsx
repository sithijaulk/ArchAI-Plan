"use client"
import React from 'react'
import dynamic from 'next/dynamic'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from './DownloadButtons'
import { FloorPlan2DViewer } from '@/components/visualization/FloorPlan2DViewer'
import { useProjectStore } from '@/store/projectStore'
import { Layers, FileJson, Box } from 'lucide-react'
import type { ExteriorLandscape } from '@/types/elia'

// Dynamically import heavy Three.js components to avoid SSR hydration errors
const ExteriorSceneViewer = dynamic(
  () => import('@/components/visualization/ExteriorSceneViewer'),
  { ssr: false, loading: () => <SceneLoading label="Loading 3D scene..." /> }
)

const EliaLandscape2D = dynamic(
  () => import('@/components/visualization/EliaLandscape2D'),
  { ssr: false, loading: () => <SceneLoading label="Loading 2D plan..." /> }
)

function SceneLoading({ label }: { label: string }) {
  return (
    <div className="w-full min-h-[400px] flex items-center justify-center bg-[#0a140a] rounded-lg">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        <span className="text-sm font-mono">{label}</span>
      </div>
    </div>
  )
}

interface OutputPreviewProps {
  projectName: string;
  component: string;
  data: any;
  masterJson?: any;
}

export function OutputPreview({ projectName, component, data, masterJson }: OutputPreviewProps) {
  const storeMasterJson = useProjectStore((s) => s.masterJson)
  
  const isElia = component === 'elia-engine'
  const landscape = isElia && data ? (data as ExteriorLandscape) : null

  // Resolve geometry: preference given to rectified output, then supplied/store masterJson
  const effectiveMaster = data?.master_json || masterJson || storeMasterJson
  const floorPlan = data?.corrected_geometry || effectiveMaster?.floor_plan
  const landInfo = effectiveMaster?.land_info

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-bold">Output Results</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {data ? 'Processing results & spatial geometry' : 'Baseline spatial layout'}
          </p>
        </div>
        <div className="flex gap-2">
          <DownloadImageButton filename={`${projectName}-${component}-output.png`} targetId="output-preview" disabled={!data && !floorPlan && !landscape} />
          <DownloadPdfButton filename={`${projectName}-${component}-output.pdf`} targetId="output-preview" disabled={!data && !floorPlan && !landscape} />
          <DownloadJsonButton filename={`${projectName}-${component}-output.json`} data={data || effectiveMaster} />
        </div>
      </div>

      <Tabs defaultValue="2d" className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="2d" className="flex items-center gap-2">
            <Layers className="w-4 h-4" /> 2D Preview
          </TabsTrigger>
          <TabsTrigger value="3d" className="flex items-center gap-2">
            <Box className="w-4 h-4" /> 3D Preview
          </TabsTrigger>
          <TabsTrigger value="json" className="flex items-center gap-2">
            <FileJson className="w-4 h-4" /> Output JSON
          </TabsTrigger>
        </TabsList>
        
        {/* 2D Plan view */}
        <TabsContent value="2d" id="output-preview" className="mt-0">
          {landscape ? (
            <EliaLandscape2D landscape={landscape} />
          ) : floorPlan ? (
            <FloorPlan2DViewer 
              floorPlan={floorPlan} 
              landInfo={landInfo} 
              rectificationResult={data} 
            />
          ) : (
            <div className="bg-card/50 border border-border p-4 rounded-xl min-h-[400px] flex items-center justify-center text-muted-foreground text-center">
              <p>{data ? 'No 2D geometry is available yet.' : 'No component output is available yet.'}</p>
            </div>
          )}
        </TabsContent>

        {/* 3D Scene */}
        <TabsContent value="3d" className="bg-card/50 border border-border rounded-xl overflow-hidden min-h-[480px]">
          {isElia ? (
            <ExteriorSceneViewer landscape={landscape} />
          ) : (
            <div className="min-h-[480px] flex items-center justify-center text-muted-foreground text-center p-4">
              <p>{data ? 'No 3D geometry is available yet.' : 'No component output is available yet.'}</p>
            </div>
          )}
        </TabsContent>
        
        {/* Master JSON Output Contract */}
        <TabsContent value="json" className="bg-card/50 border border-border p-4 rounded-xl min-h-[420px] max-h-[560px] overflow-auto mt-0">
          <pre className="text-xs text-primary-foreground/90 font-mono whitespace-pre-wrap break-all">
            {data ? JSON.stringify(data, null, 2) : (effectiveMaster ? JSON.stringify(effectiveMaster, null, 2) : 'No component output is available yet.')}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}
