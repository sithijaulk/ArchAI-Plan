"use client"
import React, { Suspense } from 'react'
import dynamic from 'next/dynamic'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from './DownloadButtons'
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
}

export function OutputPreview({ projectName, component, data }: OutputPreviewProps) {
  const isElia = component === 'elia-engine'
  const landscape = isElia && data ? (data as ExteriorLandscape) : null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold">Output Results</h3>
        <div className="flex gap-2">
          <DownloadImageButton filename={`${projectName}-${component}-output.png`} targetId="output-preview" disabled={!data} />
          <DownloadPdfButton filename={`${projectName}-${component}-output.pdf`} targetId="output-preview" disabled={!data} />
          <DownloadJsonButton filename={`${projectName}-${component}-output.json`} data={data} />
        </div>
      </div>

      <Tabs defaultValue={isElia ? '2d' : 'json'} className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="2d">2D Preview</TabsTrigger>
          <TabsTrigger value="3d">3D Preview</TabsTrigger>
          <TabsTrigger value="json">JSON</TabsTrigger>
        </TabsList>

        {/* 2D Plan view */}
        <TabsContent
          value="2d"
          className="bg-card/50 border border-border p-4 rounded-xl min-h-[480px]"
          id="output-preview"
        >
          {landscape ? (
            <EliaLandscape2D landscape={landscape} />
          ) : (
            <div className="min-h-[400px] flex items-center justify-center text-muted-foreground text-center">
              <p>{data ? 'No 2D geometry is available yet.' : 'Run ELIA to generate the exterior landscape plan.'}</p>
            </div>
          )}
        </TabsContent>

        {/* 3D Scene */}
        <TabsContent
          value="3d"
          className="bg-card/50 border border-border rounded-xl overflow-hidden min-h-[480px]"
        >
          {isElia ? (
            <ExteriorSceneViewer landscape={landscape} />
          ) : (
            <div className="min-h-[480px] flex items-center justify-center text-muted-foreground text-center p-4">
              <p>{data ? 'No 3D geometry is available yet.' : 'No component output is available yet.'}</p>
            </div>
          )}
        </TabsContent>

        {/* JSON inspector */}
        <TabsContent value="json" className="bg-card/50 border border-border p-4 rounded-xl min-h-[480px] overflow-auto">
          <pre className="text-xs text-primary-foreground/80 font-mono whitespace-pre-wrap break-all">
            {data ? JSON.stringify(data, null, 2) : 'No component output is available yet.'}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}
