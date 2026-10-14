"use client"
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { OutputPreview } from '@/components/output/OutputPreview'
import { useProjectStore } from '@/store/projectStore'
import { eliaApi } from '@/lib/api/elia'
import { Button } from '@/components/ui/button'

export default function EliaEnginePage() {
  const router = useRouter()
  const { projectId, projectName, masterJson, setComponentStatus, setOutput, outputs } = useProjectStore()
  const [isProcessing, setIsProcessing] = useState(false)

  React.useEffect(() => {
    if (!projectId) router.push('/start')
  }, [projectId, router])

  if (!projectId) return null;

  const handleProcess = async () => {
    setIsProcessing(true)
    try {
      await eliaApi.run(projectId)
    } catch (e) {
      setComponentStatus('elia_engine', 'failed')
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <FeatureWorkflowShell
      componentId="elia_engine"
      title="ELIA-Engine: Eco-Spatial Landscape Intelligence"
      number="04"
      description="Generates exterior spatial planning including access, safety zoning, shading and adaptive greenery."
      onPrev={() => router.push('/features/esai-engine')}
    >
      <div className="p-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 border-r border-border/50 pr-8">
            <h3 className="text-xl font-bold mb-4">Input Panel</h3>
            <div className="space-y-4 mb-6">
              <div className="p-4 bg-muted/50 rounded-lg border border-border text-sm">
                Requires: Master Project JSON
              </div>
            </div>
            <Button className="w-full electric-glow" onClick={handleProcess} disabled={isProcessing}>
              {isProcessing ? 'Processing...' : 'Generate Landscape'}
            </Button>
          </div>
          <div className="lg:col-span-2">
            <OutputPreview projectName={projectName} component="elia-engine" data={outputs['elia_engine']} />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
