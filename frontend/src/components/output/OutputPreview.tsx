"use client"
import React from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from './DownloadButtons'
import { FloorPlan2DViewer } from '@/components/visualization/FloorPlan2DViewer'
import { useProjectStore } from '@/store/projectStore'
import { Layers, FileJson } from 'lucide-react'

interface OutputPreviewProps {
  projectName: string;
  component: string;
  data: any;
  masterJson?: any;
}

export function OutputPreview({ projectName, component, data, masterJson }: OutputPreviewProps) {
  const storeMasterJson = useProjectStore((s) => s.masterJson)
  
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
            {data ? 'Rectification results & spatial geometry' : 'Baseline 2D spatial layout'}
          </p>
        </div>
        <div className="flex gap-2">
          <DownloadImageButton filename={`${projectName}-${component}-output.png`} targetId="output-preview" disabled={!data && !floorPlan} />
          <DownloadPdfButton filename={`${projectName}-${component}-output.pdf`} targetId="output-preview" disabled={!data && !floorPlan} />
          <DownloadJsonButton filename={`${projectName}-${component}-output.json`} data={data || effectiveMaster} />
        </div>
      </div>

      <Tabs defaultValue="2d" className="w-full">
        <TabsList className="grid w-full grid-cols-2 mb-4">
          <TabsTrigger value="2d" className="flex items-center gap-2">
            <Layers className="w-4 h-4" /> 2D Blueprint Layout
          </TabsTrigger>
          <TabsTrigger value="json" className="flex items-center gap-2">
            <FileJson className="w-4 h-4" /> Output JSON Contract
          </TabsTrigger>
        </TabsList>
        
        {/* 2D Vector Blueprint Preview (3D View removed as requested) */}
        <TabsContent value="2d" id="output-preview" className="mt-0">
          <FloorPlan2DViewer 
            floorPlan={floorPlan} 
            landInfo={landInfo} 
            rectificationResult={data} 
          />
        </TabsContent>
        
        {/* Master JSON Output Contract */}
        <TabsContent value="json" className="bg-card/50 border border-border p-4 rounded-xl min-h-[420px] max-h-[560px] overflow-auto mt-0">
          <pre className="text-xs text-primary-foreground/90 font-mono">
            {data ? JSON.stringify(data, null, 2) : (effectiveMaster ? JSON.stringify(effectiveMaster, null, 2) : 'No component output is available yet.')}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}
