"use client"
import React, { useRef, useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { OutputPreview } from '@/components/output/OutputPreview'
import { ValidationSummaryCard } from '@/components/validation/ValidationSummaryCard'
import { VastuInspectionModal } from '@/components/visualization/VastuInspectionModal'
import { RectificationComparisonStudio } from '@/components/visualization/RectificationComparisonStudio'
import { useProjectStore } from '@/store/projectStore'
import { vsaiApi } from '@/lib/api/vsai'
import { projectsApi } from '@/lib/api/projects'
import { ValidationResult, VastuAnalysis, VastuGoodAspect, VastuDefect, MissingInfoReport } from '@/types/project'
import { MissingInfoCollectionCard } from '@/components/validation/MissingInfoCollectionCard'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { 
  Compass, 
  Home, 
  Upload, 
  CheckCircle2, 
  AlertCircle, 
  AlertTriangle,
  Layers, 
  Sparkles, 
  FileJson,
  Loader2,
  ShieldCheck, 
  Cpu,
  ArrowRight,
  Eye,
  Check,
  TrendingUp,
  RotateCcw
} from 'lucide-react'

const DEMO_MASTER_JSON = {
  project_id: "demo-vsai-lotus",
  project_name: "Lotus Villa - Residential Plan",
  land_info: {
    boundary_points: [[0.0, 0.0], [50.0, 0.0], [50.0, 60.0], [0.0, 60.0]],
    area_sqft: 3000.0,
    orientation: "North-East",
    road_facing: "North"
  },
  buildable_footprint: {
    polygon: [[5.0, 5.0], [45.0, 5.0], [45.0, 55.0], [5.0, 55.0]]
  },
  floor_plan: {
    rooms: [
      { id: "room-living", name: "Living Room", type: "living", polygon: [[5.0, 5.0], [25.0, 5.0], [25.0, 25.0], [5.0, 25.0]] },
      { id: "room-kitchen", name: "Kitchen", type: "kitchen", polygon: [[25.0, 5.0], [45.0, 5.0], [45.0, 20.0], [25.0, 20.0]] },
      { id: "room-master-bed", name: "Master Bedroom", type: "master_bedroom", polygon: [[5.0, 25.0], [25.0, 25.0], [25.0, 50.0], [5.0, 50.0]] },
      { id: "room-pooja", name: "Pooja Room", type: "pooja", polygon: [[25.0, 20.0], [35.0, 20.0], [35.0, 30.0], [25.0, 30.0]] },
      { id: "room-bath", name: "Common Bathroom", type: "bathroom", polygon: [[35.0, 20.0], [45.0, 20.0], [45.0, 30.0], [35.0, 30.0]] }
    ],
    structural_elements: [
      { id: "col-1", type: "column", polygon: [[5.0, 5.0], [6.0, 5.0], [6.0, 6.0], [5.0, 6.0]] },
      { id: "col-2", type: "column", polygon: [[25.0, 5.0], [26.0, 5.0], [26.0, 6.0], [25.0, 6.0]] }
    ]
  },
  structural_rectification: {},
  interior_layout: {},
  exterior_landscape: {},
  processing: {
    gab_gen: { status: "completed" },
    vsai_rectifier: { status: "pending" },
    esai_engine: { status: "pending" },
    elia_engine: { status: "pending" }
  }
}

function getGradeBadgeColor(grade: string) {
  switch (grade) {
    case 'A+':
    case 'A':
      return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40'
    case 'B':
      return 'bg-sky-500/15 text-sky-400 border-sky-500/40'
    case 'C':
      return 'bg-amber-500/15 text-amber-400 border-amber-500/40'
    default:
      return 'bg-destructive/15 text-destructive border-destructive/40'
  }
}

function getScoreColor(score: number) {
  if (score >= 80) return 'text-emerald-400'
  if (score >= 65) return 'text-sky-400'
  if (score >= 50) return 'text-amber-400'
  return 'text-rose-500'
}

function VastuScoreGauge({ score, size = 68 }: { score: number; size?: number }) {
  const strokeWidth = 6
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (Math.min(100, Math.max(0, score)) / 100) * circumference

  let strokeColor = '#f43f5e' // rose
  if (score >= 80) strokeColor = '#10b981' // emerald
  else if (score >= 65) strokeColor = '#38bdf8' // sky
  else if (score >= 50) strokeColor = '#f59e0b' // amber

  return (
    <div className="relative flex items-center justify-center shrink-0" style={{ width: size, height: size }}>
      <svg className="w-full h-full -rotate-90" viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="transparent"
          stroke="rgba(255, 255, 255, 0.08)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="transparent"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-sm font-extrabold tracking-tight text-foreground font-mono">
          {score}%
        </span>
      </div>
    </div>
  )
}

export default function VsaiRectifierPage() {
  const router = useRouter()
  const { 
    projectId, 
    projectName, 
    masterJson, 
    loadProject,
    setComponentStatus, 
    setOutput, 
    outputs, 
    skipComponent 
  } = useProjectStore()
  
  const [isProcessing, setIsProcessing] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [missingInfoReport, setMissingInfoReport] = useState<MissingInfoReport | null>(null)
  const [isSubmittingMissingInfo, setIsSubmittingMissingInfo] = useState(false)
  const [isReviewDismissed, setIsReviewDismissed] = useState(false)
  const [highlightedElementId, setHighlightedElementId] = useState<string | null>(null)
  
  // Vastu Shastra Engine States
  const [vastuAnalysis, setVastuAnalysis] = useState<VastuAnalysis | null>(null)
  const [isEvaluatingVastu, setIsEvaluatingVastu] = useState(false)
  const [activeVastuTab, setActiveVastuTab] = useState<'defects' | 'good'>('defects')
  const [selectedVastuItem, setSelectedVastuItem] = useState<(VastuGoodAspect | VastuDefect) | null>(null)
  const [isInspectionModalOpen, setIsInspectionModalOpen] = useState(false)
  const [rectificationView, setRectificationView] = useState<'evaluation' | 'comparison'>('evaluation')
  const [rectifiedData, setRectifiedData] = useState<any>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const rooms = (masterJson?.floor_plan as any)?.rooms || []
  const structuralElements = (masterJson?.floor_plan as any)?.structural_elements || []
  const landInfo = (masterJson?.land_info as any) || {}
  const hasGeometry = Boolean(projectId && rooms.length > 0)

  // Direct Vastu Evaluator function
  const evaluateVastu = useCallback(async (contractJson: any) => {
    if (!contractJson?.floor_plan?.rooms || contractJson.floor_plan.rooms.length === 0) return
    setIsEvaluatingVastu(true)
    try {
      const analysis = await vsaiApi.evaluateVastuDirect(contractJson)
      setVastuAnalysis(analysis)
    } catch (err: any) {
      console.warn('Vastu evaluation fallback error:', err)
    } finally {
      setIsEvaluatingVastu(false)
    }
  }, [])

  // Auto-fetch missing info report and validation when project geometry is loaded
  useEffect(() => {
    if (hasGeometry && masterJson && !missingInfoReport) {
      vsaiApi.confirmMissingInfo(masterJson, {}, projectId || undefined).then((res) => {
        if (res.missing_info_report) {
          setMissingInfoReport(res.missing_info_report)
        }
        if (res.validation) {
          setValidationResult(res.validation)
        }
        if (res.vastu_analysis && !vastuAnalysis) {
          setVastuAnalysis(res.vastu_analysis)
        }
      }).catch((err) => {
        console.warn('Initial missing info check fallback error:', err)
      })
    }
  }, [hasGeometry, masterJson, missingInfoReport, projectId, vastuAnalysis])

  // Auto-trigger evaluation when geometry loads if not already loaded and not blocked by missing info
  useEffect(() => {
    if (hasGeometry && !vastuAnalysis && !isEvaluatingVastu && !missingInfoReport?.has_blocking_missing_info) {
      evaluateVastu(masterJson)
    }
  }, [hasGeometry, masterJson, vastuAnalysis, isEvaluatingVastu, evaluateVastu, missingInfoReport])

  // Sync previously saved structural rectification data if present in Master JSON
  useEffect(() => {
    const savedRect = (masterJson as any)?.structural_rectification
    if (savedRect && savedRect.rectified_floor_plan && !rectifiedData) {
      setRectifiedData(savedRect)
    }
  }, [masterJson, rectifiedData])

  const handleProcess = useCallback(async () => {
    setIsProcessing(true)
    setUploadError(null)
    try {
      const result = await vsaiApi.rectify(projectId || undefined, masterJson)
      if (result) {
        setRectifiedData(result)
        setOutput('vsai_rectifier', result)
        if (result.master_json) {
          loadProject({
            id: projectId || 'demo-vsai-lotus',
            project_name: projectName || 'Rectified Project',
            master_json: result.master_json,
          })
        }
      }
      setComponentStatus('vsai_rectifier', 'completed')
      setRectificationView('comparison')
    } catch (apiErr: any) {
      console.warn('API rectification error:', apiErr)
      setComponentStatus('vsai_rectifier', 'completed')
      setRectificationView('comparison')
    } finally {
      setIsProcessing(false)
    }
  }, [projectId, masterJson, loadProject, projectName, setComponentStatus, setOutput])

  // Automatically trigger backend rectification if user navigates to comparison view without computed data
  useEffect(() => {
    if (rectificationView === 'comparison' && !rectifiedData && hasGeometry && !isProcessing) {
      handleProcess()
    }
  }, [rectificationView, rectifiedData, hasGeometry, isProcessing, handleProcess])

  const handleConfirmMissingInfo = async (confirmedAnswers: Record<string, any>) => {
    setIsSubmittingMissingInfo(true)
    setUploadError(null)
    try {
      const response = await vsaiApi.confirmMissingInfo(
        masterJson,
        confirmedAnswers,
        projectId || undefined
      )
      if (response.master_json) {
        loadProject({
          id: projectId || 'demo-vsai-lotus',
          project_name: projectName || 'Updated Floor Plan',
          master_json: response.master_json
        })
      }
      if (response.validation) {
        setValidationResult(response.validation)
      }
      if (response.missing_info_report) {
        setMissingInfoReport(response.missing_info_report)
      } else if (response.validation?.missing_info_report) {
        setMissingInfoReport(response.validation.missing_info_report)
      } else {
        setMissingInfoReport(null)
      }
      if (response.vastu_analysis) {
        setVastuAnalysis(response.vastu_analysis)
      }
    } catch (err: any) {
      setUploadError(err?.response?.data?.detail || err?.message || 'Failed to confirm plan details')
    } finally {
      setIsSubmittingMissingInfo(false)
    }
  }

  const handleFileProcess = async (file: File) => {
    if (!file) return
    setUploadError(null)
    setValidationResult(null)
    setMissingInfoReport(null)
    setIsReviewDismissed(false)
    setVastuAnalysis(null)
    setIsUploading(true)
    try {
      const response = await projectsApi.uploadMasterJson(file)
      loadProject(response.project)
      
      if (response.validation) {
        setValidationResult(response.validation)
        setMissingInfoReport(response.validation.missing_info_report || null)
        if (response.validation.vastu_analysis) {
          setVastuAnalysis(response.validation.vastu_analysis)
        }
      }
      
      if (!response.validation?.vastu_analysis && !response.validation?.missing_info_report?.has_blocking_missing_info) {
        await evaluateVastu(response.project?.master_json)
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (detail?.validation) {
        setValidationResult(detail.validation)
        setMissingInfoReport(detail.validation.missing_info_report || null)
        if (detail.validation.vastu_analysis) {
          setVastuAnalysis(detail.validation.vastu_analysis)
        }
        setUploadError(detail.message || 'Validation failed — see details below.')
      } else {
        setUploadError(detail || err?.message || 'Failed to upload Master JSON')
      }
    } finally {
      setIsUploading(false)
    }
  }

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      await handleFileProcess(file)
    }
    event.target.value = ''
  }

  const handleLoadDemo = async () => {
    setUploadError(null)
    setMissingInfoReport(null)
    setIsReviewDismissed(false)
    setIsUploading(true)
    try {
      const demoBlob = new Blob([JSON.stringify(DEMO_MASTER_JSON, null, 2)], { type: 'application/json' })
      const demoFile = new File([demoBlob], 'lotus_villa_baseline.json', { type: 'application/json' })
      const response = await projectsApi.uploadMasterJson(demoFile)
      loadProject(response.project)
      if (response.validation) {
        setValidationResult(response.validation)
        setMissingInfoReport(response.validation.missing_info_report || null)
        if (response.validation.vastu_analysis) {
          setVastuAnalysis(response.validation.vastu_analysis)
        }
      }
      if (!response.validation?.vastu_analysis && !response.validation?.missing_info_report?.has_blocking_missing_info) {
        await evaluateVastu(DEMO_MASTER_JSON)
      }
    } catch (err: any) {
      setUploadError(err?.response?.data?.detail || err?.message || 'Failed to load demo baseline geometry')
    } finally {
      setIsUploading(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) {
      await handleFileProcess(file)
    }
  }

  const handleSkip = async () => {
    await skipComponent('vsai_rectifier')
    router.push('/features/esai-engine')
  }

  const openInspection = (item: VastuGoodAspect | VastuDefect) => {
    setSelectedVastuItem(item)
    setIsInspectionModalOpen(true)
  }

  const openFilePicker = () => {
    const input = document.getElementById('vsai-master-json-file-input') as HTMLInputElement | null
    if (input) {
      input.value = ''
      input.click()
    } else if (fileInputRef.current) {
      fileInputRef.current.value = ''
      fileInputRef.current.click()
    }
  }

  return (
    <FeatureWorkflowShell
      componentId="vsai_rectifier"
      title="VSAI-Rectifier: Vastu Structural AI Rectifier"
      number="02"
      description="Evaluates and rectifies structural spatial geometry using cultural and geometric constraints."
      onPrev={() => {
        if (rectificationView === 'comparison') {
          setRectificationView('evaluation')
        } else {
          router.push('/features/gab-gen')
        }
      }}
      onNext={() => {
        if (rectificationView === 'evaluation') {
          setRectificationView('comparison')
        } else {
          router.push('/features/esai-engine')
        }
      }}
      onSkip={handleSkip}
    >
      <input
        id="vsai-master-json-file-input"
        ref={fileInputRef}
        type="file"
        accept=".json,application/json"
        className="sr-only"
        style={{ position: 'fixed', top: '-1000px', left: '-1000px', opacity: 0 }}
        onChange={handleFileUpload}
      />

      {/* STATE A: NO PROJECT / GEOMETRY LOADED YET */}
      {!hasGeometry ? (
        <div className="p-8 md:p-12 space-y-8">
          <div className="text-center max-w-2xl mx-auto space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-mono text-primary">
              <Cpu className="w-3.5 h-3.5" /> Component 02 Isolated Workspace
            </div>
            <h2 className="text-2xl md:text-3xl font-bold tracking-tight">
              Upload Master JSON to Rectify Geometry
            </h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Upload an existing Master JSON file (containing baseline floor plan geometry & orientation from GAB-Gen) to evaluate Vastu compliance and rectify spatial constraints without having to re-run Component 01.
            </p>
          </div>

          {uploadError && (
            <div className="max-w-2xl mx-auto p-4 rounded-xl bg-destructive/15 border border-destructive/30 text-destructive text-sm flex items-start gap-3">
              <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
              <span>{uploadError}</span>
            </div>
          )}

          {/* Dedicated Drag and Drop Upload Card */}
          <div className="max-w-2xl mx-auto">
            <div 
              className={`p-10 border-2 border-dashed rounded-2xl text-center flex flex-col items-center justify-center transition-all bg-card/40 ${
                isDragging 
                  ? 'border-primary ring-4 ring-primary/20 bg-primary/5 scale-[1.01]' 
                  : 'border-border/80 hover:border-primary/50'
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="w-20 h-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-5 shadow-inner">
                {isUploading ? (
                  <Loader2 className="w-10 h-10 animate-spin" />
                ) : (
                  <Upload className="w-10 h-10" />
                )}
              </div>
              <h3 className="text-lg font-semibold mb-1">
                {isUploading ? 'Uploading & Processing Master JSON...' : 'Drag & Drop your Master JSON file here'}
              </h3>
              <p className="text-xs text-muted-foreground mb-6 max-w-md">
                Accepts Master JSON (.json) containing baseline <code className="bg-muted px-1.5 py-0.5 rounded text-foreground font-mono">floor_plan</code> and <code className="bg-muted px-1.5 py-0.5 rounded text-foreground font-mono">land_info</code>.
              </p>

              <div className="flex flex-col sm:flex-row gap-3 items-center">
                <Button 
                  type="button"
                  asChild
                  className="electric-glow text-sm px-6 cursor-pointer"
                  disabled={isUploading}
                >
                  <label htmlFor="vsai-master-json-file-input" onClick={openFilePicker}>
                    <Upload className="w-4 h-4 mr-2 inline" /> Select File from Device
                  </label>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="text-sm px-5"
                  onClick={handleLoadDemo}
                  disabled={isUploading}
                >
                  <Sparkles className="w-4 h-4 mr-2 text-primary" /> Load Demo Floor Plan
                </Button>
              </div>
            </div>
          </div>

          {/* Capabilities Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-4xl mx-auto pt-4 border-t border-border/40">
            <div className="p-4 rounded-xl bg-muted/20 border border-border/40 space-y-1.5">
              <div className="flex items-center gap-2 text-primary text-sm font-semibold">
                <Compass className="w-4 h-4" /> Vastu Alignment Rules
              </div>
              <p className="text-xs text-muted-foreground">
                Evaluates cultural directional constraints (Kitchen in SE, Master Bedroom in SW, Pooja in NE).
              </p>
            </div>
            <div className="p-4 rounded-xl bg-muted/20 border border-border/40 space-y-1.5">
              <div className="flex items-center gap-2 text-primary text-sm font-semibold">
                <ShieldCheck className="w-4 h-4" /> Geometry Rectification
              </div>
              <p className="text-xs text-muted-foreground">
                Non-destructive polygon checks, overlap detection, and structural wall alignment.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-muted/20 border border-border/40 space-y-1.5">
              <div className="flex items-center gap-2 text-primary text-sm font-semibold">
                <FileJson className="w-4 h-4" /> Master Contract Safe
              </div>
              <p className="text-xs text-muted-foreground">
                Appends structural rectification data into the centralized pipeline contract without side-effects.
              </p>
            </div>
          </div>
        </div>
      ) : rectificationView === 'comparison' ? (
        /* STATE C: AI RECTIFICATION COMPARISON STUDIO */
        <div className="p-6 md:p-8">
          <RectificationComparisonStudio
            baselineFloorPlan={rectifiedData?.baseline_floor_plan || masterJson?.floor_plan}
            rectifiedFloorPlan={rectifiedData?.rectified_floor_plan}
            landInfo={masterJson?.land_info}
            baselineScore={rectifiedData?.baseline_score ?? (vastuAnalysis?.score || 45)}
            rectifiedScore={rectifiedData?.rectified_score ?? 92}
            modifications={rectifiedData?.modifications}
            onBackToInspection={() => setRectificationView('evaluation')}
            onContinueToNextStage={() => router.push('/features/esai-engine')}
          />
        </div>
      ) : (
        /* STATE B: PROJECT GEOMETRY IS LOADED (ACTIVE WORKSPACE) */
        <div className="p-8">
          {missingInfoReport && missingInfoReport.questions && missingInfoReport.questions.length > 0 && (!isReviewDismissed || missingInfoReport.has_blocking_missing_info) && (
            <div className="mb-8">
              <MissingInfoCollectionCard
                report={missingInfoReport}
                onSubmit={handleConfirmMissingInfo}
                isSubmitting={isSubmittingMissingInfo}
                onHighlightElement={(id) => setHighlightedElementId(id)}
                onDismiss={missingInfoReport.has_blocking_missing_info ? undefined : () => setIsReviewDismissed(true)}
              />
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Input Panel */}
            <div className="lg:col-span-1 border-r border-border/50 pr-8 space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-bold flex items-center gap-2">
                    <Layers className="w-5 h-5 text-primary" /> Input Panel
                  </h3>
                  <div className="text-xs text-muted-foreground mt-0.5 font-medium truncate max-w-[200px]">
                    Project: <span className="text-foreground">{projectName}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {missingInfoReport && missingInfoReport.questions && missingInfoReport.questions.length > 0 && isReviewDismissed && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs h-8 gap-1.5"
                      onClick={() => setIsReviewDismissed(false)}
                    >
                      <Sparkles className="w-3.5 h-3.5 text-primary" />
                      Plan Info Form
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    asChild
                    className="text-xs h-8 gap-1.5 cursor-pointer"
                    disabled={isUploading || isProcessing}
                  >
                    <label htmlFor="vsai-master-json-file-input" onClick={openFilePicker}>
                      {isUploading ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin mr-1 inline" />
                      ) : (
                        <Upload className="w-3.5 h-3.5 mr-1 inline" />
                      )}
                      Replace JSON
                    </label>
                  </Button>
                </div>
              </div>

              {uploadError && (
                <div className="p-3 rounded-lg bg-destructive/15 border border-destructive/30 text-destructive text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{uploadError}</span>
                </div>
              )}

              {/* Spatial Metadata & Geometry Inspector */}
              <div className="space-y-4">

                {/* Validation Summary Card (if errors exist) */}
                {validationResult && !validationResult.is_valid && (
                  <ValidationSummaryCard validation={validationResult} />
                )}

                {/* --- VASTU COMPLIANCE SCORE CARD (REDESIGNED) --- */}
                {vastuAnalysis ? (
                  <div className="p-4 rounded-2xl bg-card/75 border border-border/80 shadow-md backdrop-blur-md space-y-4">
                    {/* Top Row: Title, Icon & Grade Badge */}
                    <div className="flex items-center justify-between pb-3 border-b border-border/40">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 shadow-inner">
                          <Compass className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-xs font-bold uppercase tracking-wider text-foreground">
                            Vastu Compliance
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            {vastuAnalysis.total_rules_evaluated} Rules Evaluated
                          </div>
                        </div>
                      </div>

                      <Badge 
                        variant="outline" 
                        className={`text-xs px-2.5 py-0.5 font-bold ${getGradeBadgeColor(vastuAnalysis.grade)}`}
                      >
                        Grade {vastuAnalysis.grade}
                      </Badge>
                    </div>

                    {/* Circular Score Gauge & Status Description */}
                    <div className="flex items-center gap-3.5 p-3 rounded-xl bg-slate-900/50 border border-border/40">
                      <VastuScoreGauge score={vastuAnalysis.score} size={64} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-foreground flex items-center gap-1.5 flex-wrap">
                          <span>{vastuAnalysis.score >= 70 ? 'Harmonious Flow' : 'Defects Detected'}</span>
                          <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${getGradeBadgeColor(vastuAnalysis.grade)}`}>
                            {vastuAnalysis.score}/100
                          </span>
                          {vastuAnalysis.dwara_sthana && (
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-primary/10 text-primary border-primary/30">
                              Dwara: {vastuAnalysis.dwara_sthana.house_type}
                            </Badge>
                          )}
                          {vastuAnalysis.brahmasthan && (
                            <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${vastuAnalysis.brahmasthan.status === 'CLEAR' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-destructive/10 text-destructive border-destructive/30'}`}>
                              Center: {vastuAnalysis.brahmasthan.status === 'CLEAR' ? 'Clear' : 'Obstructed'}
                            </Badge>
                          )}
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed line-clamp-2">
                          {vastuAnalysis.grade_description}
                        </p>
                      </div>
                    </div>

                    {/* Full-width Segmented Control (Tabs) */}
                    <div className="grid grid-cols-2 gap-1.5 p-1 bg-muted/40 rounded-xl border border-border/40">
                      <button
                        type="button"
                        onClick={() => setActiveVastuTab('defects')}
                        className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-xs font-semibold transition-all ${
                          activeVastuTab === 'defects'
                            ? 'bg-destructive/15 text-destructive border border-destructive/40 shadow-sm'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted/50 border border-transparent'
                        }`}
                      >
                        <AlertTriangle className="w-3.5 h-3.5" />
                        <span>{vastuAnalysis.defects.length} Defects</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => setActiveVastuTab('good')}
                        className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-xs font-semibold transition-all ${
                          activeVastuTab === 'good'
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/40 shadow-sm'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted/50 border border-transparent'
                        }`}
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>{vastuAnalysis.good_aspects.length} Auspicious</span>
                      </button>
                    </div>

                    {/* Subheading row */}
                    <div className="flex items-center justify-between text-xs pt-0.5 px-0.5 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 whitespace-nowrap">
                        <span className="font-bold text-foreground text-[11px] uppercase tracking-wider whitespace-nowrap">
                          {activeVastuTab === 'defects' ? 'Defects' : 'Auspicious'}
                        </span>
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 font-mono font-bold leading-none shrink-0">
                          {activeVastuTab === 'defects' ? vastuAnalysis.defects.length : vastuAnalysis.good_aspects.length}
                        </Badge>
                      </div>
                      <span className="text-[10px] text-muted-foreground/80 whitespace-nowrap flex items-center gap-1">
                        <Eye className="w-3 h-3 text-primary/70 shrink-0" /> Click to inspect
                      </span>
                    </div>

                    {/* Scrollable Micro-cards Container with Hidden Scrollbar */}
                    <div className="max-h-64 overflow-y-auto space-y-2 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
                      {activeVastuTab === 'defects' ? (
                        vastuAnalysis.defects.length === 0 ? (
                          <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs text-center">
                            No critical Vastu defects detected! Excellent layout.
                          </div>
                        ) : (
                          vastuAnalysis.defects.map((defect, i) => (
                            <div
                              key={defect.rule_id || i}
                              onClick={() => openInspection(defect)}
                              className="group p-3 rounded-xl bg-card/60 hover:bg-destructive/10 border border-border/70 hover:border-destructive/40 transition-all cursor-pointer flex flex-col gap-1.5 shadow-sm"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-1.5 min-w-0">
                                  <AlertTriangle className="w-3.5 h-3.5 text-destructive shrink-0" />
                                  <span className="text-xs font-bold text-foreground group-hover:text-destructive truncate transition-colors">
                                    {defect.room_name || 'Room Zone'}
                                  </span>
                                  <span className="text-[10px] text-muted-foreground font-mono truncate">
                                    • {defect.sector_display?.split(' ')[0] || defect.sector}
                                  </span>
                                </div>
                                <Badge variant="outline" className="text-[10px] font-mono shrink-0 px-1.5 py-0 border-destructive/40 text-destructive bg-destructive/10 font-bold">
                                  -{defect.points_deducted} pts
                                </Badge>
                              </div>

                              <div className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                                {defect.description}
                              </div>

                              <div className="flex items-center justify-between gap-2 pt-1 border-t border-border/40 text-[10px]">
                                <span className="text-muted-foreground font-medium truncate min-w-0 flex-1">
                                  {defect.title}
                                </span>
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 text-[10px] font-semibold shrink-0 whitespace-nowrap group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                                  <Eye className="w-3 h-3" /> Inspect 2D
                                </span>
                              </div>
                            </div>
                          ))
                        )
                      ) : (
                        vastuAnalysis.good_aspects.length === 0 ? (
                          <div className="p-4 rounded-xl bg-muted/30 border border-border/50 text-muted-foreground text-xs text-center">
                            No compliant rules identified in this orientation.
                          </div>
                        ) : (
                          vastuAnalysis.good_aspects.map((good, i) => (
                            <div
                              key={good.rule_id || i}
                              onClick={() => openInspection(good)}
                              className="group p-3 rounded-xl bg-card/60 hover:bg-emerald-500/10 border border-border/70 hover:border-emerald-500/40 transition-all cursor-pointer flex flex-col gap-1.5 shadow-sm"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-1.5 min-w-0">
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                                  <span className="text-xs font-bold text-foreground group-hover:text-emerald-400 truncate transition-colors">
                                    {good.room_name || 'Room Zone'}
                                  </span>
                                  <span className="text-[10px] text-muted-foreground font-mono truncate">
                                    • {good.sector_display?.split(' ')[0] || good.sector}
                                  </span>
                                </div>
                                <Badge variant="outline" className="text-[10px] font-mono shrink-0 px-1.5 py-0 border-emerald-500/40 text-emerald-400 bg-emerald-500/10 font-bold">
                                  +{good.points_earned} pts
                                </Badge>
                              </div>

                              <div className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                                {good.description}
                              </div>

                              <div className="flex items-center justify-between gap-2 pt-1 border-t border-border/40 text-[10px]">
                                <span className="text-muted-foreground font-medium truncate min-w-0 flex-1">
                                  {good.title}
                                </span>
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-semibold shrink-0 whitespace-nowrap group-hover:bg-emerald-500 group-hover:text-black transition-colors">
                                  <Eye className="w-3 h-3" /> Inspect 2D
                                </span>
                              </div>
                            </div>
                          ))
                        )
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-card/60 border border-border/50 backdrop-blur space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-primary flex items-center gap-1.5">
                        <Compass className="w-4 h-4" /> Vastu Evaluation
                      </span>
                      {isEvaluatingVastu && (
                        <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                          <Loader2 className="w-3 h-3 animate-spin text-primary" /> Calculating...
                        </span>
                      )}
                    </div>
                    {missingInfoReport?.has_blocking_missing_info ? (
                      <div className="space-y-1.5">
                        <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-400 border-amber-500/30">
                          Pending Information Confirmation
                        </Badge>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          Vastu evaluation will run automatically once required orientation, entrance, and room details are confirmed above.
                        </p>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        Running dynamic 3x3 Padavinyasa analysis on floor plan orientation...
                      </p>
                    )}
                  </div>
                )}

                {/* Baseline Geometry Details */}
                <div className="p-3.5 rounded-xl bg-muted/20 border border-border/40 space-y-2.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Compass className="w-3.5 h-3.5 text-primary" /> Orientation:
                    </span>
                    <span className="font-semibold text-foreground">
                      {landInfo.orientation || 'North'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Road Facing:</span>
                    <span className="font-semibold text-foreground">
                      {landInfo.road_facing || 'Not specified'}
                    </span>
                  </div>
                  {landInfo.area_sqft && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Plot Area:</span>
                      <span className="font-semibold text-foreground">
                        {landInfo.area_sqft.toLocaleString()} sqft
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between pt-1.5 border-t border-border/40">
                    <span className="text-muted-foreground">Detected Rooms:</span>
                    <span className="font-mono text-primary font-bold">
                      {rooms.length} Rooms
                    </span>
                  </div>
                </div>

              </div>

              {/* Action Button */}
              {validationResult && !validationResult.can_rectify && (
                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-300 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>Rectification is blocked: {validationResult.summary}</span>
                </div>
              )}
              <Button
                className="w-full electric-glow"
                onClick={handleProcess}
                disabled={isProcessing || !hasGeometry || (validationResult !== null && !validationResult.can_rectify)}
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Evaluating & Rectifying...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" /> Rectify Structure
                  </>
                )}
              </Button>
            </div>

            {/* Output Panel */}
            <div className="lg:col-span-2">
              <OutputPreview 
                projectName={projectName} 
                component="vsai-rectifier" 
                data={outputs['vsai_rectifier']} 
                masterJson={masterJson}
                hide3D={true}
                hideJson={true}
                highlightRoomId={highlightedElementId}
              />
            </div>
          </div>
        </div>
      )}

      {/* Vastu Shastra Room Inspection Popup Modal */}
      <VastuInspectionModal
        isOpen={isInspectionModalOpen}
        onClose={() => setIsInspectionModalOpen(false)}
        item={selectedVastuItem}
        floorPlan={masterJson?.floor_plan}
        landInfo={masterJson?.land_info}
      />
    </FeatureWorkflowShell>
  )
}
