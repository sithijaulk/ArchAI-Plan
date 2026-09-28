"use client"
import React from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from './DownloadButtons'

interface OutputPreviewProps {
  projectName: string;
  component: string;
  data: any;
}

export function OutputPreview({ projectName, component, data }: OutputPreviewProps) {
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

      <Tabs defaultValue="2d" className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="2d">2D Preview</TabsTrigger>
          <TabsTrigger value="3d">3D Preview</TabsTrigger>
          <TabsTrigger value="json">JSON</TabsTrigger>
        </TabsList>
        
        <TabsContent value="2d" className="bg-card/50 border border-border p-4 rounded-xl min-h-[400px] flex items-center justify-center" id="output-preview">
          <div className="text-muted-foreground text-center">
            <p>{data ? 'No 2D geometry is available yet.' : 'No component output is available yet.'}</p>
          </div>
        </TabsContent>
        
        <TabsContent value="3d" className="bg-card/50 border border-border p-4 rounded-xl min-h-[400px] flex items-center justify-center">
          <div className="text-muted-foreground text-center">
            <p>{data ? 'No 3D geometry is available yet.' : 'No component output is available yet.'}</p>
          </div>
        </TabsContent>
        
        <TabsContent value="json" className="bg-card/50 border border-border p-4 rounded-xl min-h-[400px] overflow-auto">
          <pre className="text-xs text-primary-foreground/80 font-mono">
            {data ? JSON.stringify(data, null, 2) : 'No component output is available yet.'}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}
