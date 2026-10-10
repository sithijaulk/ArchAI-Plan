"use client"
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { OutputPreview } from '@/components/output/OutputPreview'
import { useProjectStore } from '@/store/projectStore'
import { esaiApi } from '@/lib/api/esai'
import { Button } from '@/components/ui/button'

export default function EsaiEnginePage() {
  const router = useRouter()
  const { projectId, projectName, masterJson, setComponentStatus, setOutput, outputs, skipComponent } = useProjectStore()
  const [isProcessing, setIsProcessing] = useState(false)

  React.useEffect(() => {
    if (!projectId) router.push('/start')
  }, [projectId, router])

  if (!projectId) return null;

  const handleProcess = async () => {
    setIsProcessing(true)
    try {
      await esaiApi.run(projectId)
    } catch (e) {
      setComponentStatus('esai_engine', 'failed')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleSkip = async () => {
    await skipComponent('esai_engine')
    router.push('/features/elia-engine')
  }

  return (
    <FeatureWorkflowShell
      componentId="esai_engine"
      title="ESAI-Engine: Ergonomic Spatial Intelligence"
      number="03"
      description="Optimizes furniture and interior asset placement using ergonomic clearance and spatial constraints."
      onPrev={() => router.push('/features/vsai-rectifier')}
      onNext={() => router.push('/features/elia-engine')}
      onSkip={handleSkip}
    >
      <div className="p-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 border-r border-border/50 pr-8">
            <h3 className="text-xl font-bold mb-4">Input Panel</h3>
            <div className="space-y-4 mb-6">
              <div className="p-4 bg-muted/50 rounded-lg border border-border text-sm">
                Requires: Rectified Structure from VSAI
              </div>
            </div>
            <Button className="w-full electric-glow" onClick={handleProcess} disabled={isProcessing}>
              {isProcessing ? 'Processing...' : 'Optimize Ergonomics'}
            </Button>
          </div>
          <div className="lg:col-span-2">
            <OutputPreview projectName={projectName} component="esai-engine" data={outputs['esai_engine']} />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
