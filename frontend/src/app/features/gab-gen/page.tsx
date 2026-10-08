"use client"
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { OutputPreview } from '@/components/output/OutputPreview'
import { useProjectStore } from '@/store/projectStore'
import { gabGenApi } from '@/lib/api/gabGen'
import { Button } from '@/components/ui/button'

export default function GabGenPage() {
  const router = useRouter()
  const { projectId, projectName, outputs, skipComponent } = useProjectStore()
  const [isProcessing, setIsProcessing] = useState(false)

  // Redirect to start if no project
  React.useEffect(() => {
    if (!projectId) {
      router.push('/start')
    }
  }, [projectId, router])

  if (!projectId) return null;

  const handleProcess = async () => {
    setIsProcessing(true)
    try {
      await gabGenApi.run(projectId)
    } catch {
      // The shared branch intentionally exposes a controlled pending response.
    } finally {
      setIsProcessing(false)
    }
  }

  const handleSkip = async () => {
    await skipComponent('gab_gen')
    router.push('/features/vsai-rectifier')
  }

  return (
    <FeatureWorkflowShell
      componentId="gab_gen"
      title="GAB-Gen: Geo-Spatial AI Blueprint Generator"
      number="01"
      description="Processes land/deed spatial information and produces baseline residential spatial geometry."
      onNext={() => router.push('/features/vsai-rectifier')}
      onSkip={handleSkip}
    >
      <div className="p-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 border-r border-border/50 pr-8">
            <h3 className="text-xl font-bold mb-4">Input Panel</h3>
            <div className="space-y-4 mb-6">
              <div className="p-4 bg-muted/50 rounded-lg border border-border">
                <p className="text-sm font-medium">Project ID: {projectId}</p>
                <p className="text-sm text-muted-foreground">{projectName}</p>
              </div>
              <div className="p-4 bg-muted/50 rounded-lg border border-border flex items-center justify-center h-32 border-dashed">
                <p className="text-sm text-muted-foreground text-center">Land geometry input will be connected by the GAB-Gen research branch.</p>
              </div>
            </div>
            <Button 
              className="w-full electric-glow" 
              onClick={handleProcess} 
              disabled={isProcessing}
            >
              {isProcessing ? 'Processing...' : 'Generate Blueprint'}
            </Button>
          </div>
          <div className="lg:col-span-2">
            <OutputPreview 
              projectName={projectName}
              component="gab-gen"
              data={outputs['gab_gen']}
            />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
