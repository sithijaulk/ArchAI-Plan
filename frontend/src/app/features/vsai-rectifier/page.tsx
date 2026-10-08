"use client"
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { OutputPreview } from '@/components/output/OutputPreview'
import { useProjectStore } from '@/store/projectStore'
import { vsaiApi } from '@/lib/api/vsai'
import { Button } from '@/components/ui/button'

export default function VsaiRectifierPage() {
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
      await vsaiApi.run(projectId)
    } catch (e) {
      setComponentStatus('vsai_rectifier', 'failed')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleSkip = async () => {
    await skipComponent('vsai_rectifier')
    router.push('/features/esai-engine')
  }

  return (
    <FeatureWorkflowShell
      componentId="vsai_rectifier"
      title="VSAI-Rectifier: Vastu Structural AI Rectifier"
      number="02"
      description="Evaluates and rectifies structural spatial geometry using cultural and geometric constraints."
      onPrev={() => router.push('/features/gab-gen')}
      onNext={() => router.push('/features/esai-engine')}
      onSkip={handleSkip}
    >
      <div className="p-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 border-r border-border/50 pr-8">
            <h3 className="text-xl font-bold mb-4">Input Panel</h3>
            <div className="space-y-4 mb-6">
              <div className="p-4 bg-muted/50 rounded-lg border border-border text-sm">
                Requires: Baseline Geometry from GAB-Gen
              </div>
            </div>
            <Button 
              className="w-full electric-glow" 
              onClick={handleProcess} 
              disabled={isProcessing}
            >
              {isProcessing ? 'Processing...' : 'Rectify Structure'}
            </Button>
          </div>
          <div className="lg:col-span-2">
            <OutputPreview projectName={projectName} component="vsai-rectifier" data={outputs['vsai_rectifier']} />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
