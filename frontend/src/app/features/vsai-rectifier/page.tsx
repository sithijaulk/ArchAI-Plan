"use client"
import React, { useRef, useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { OutputPreview } from '@/components/output/OutputPreview'
import { ValidationSummaryCard } from '@/components/validation/ValidationSummaryCard'
import { VastuInspectionModal } from '@/components/visualization/VastuInspectionModal'
import { useProjectStore } from '@/store/projectStore'
import { vsaiApi } from '@/lib/api/vsai'
import { projectsApi } from '@/lib/api/projects'
import { ValidationResult, VastuAnalysis, VastuGoodAspect, VastuDefect } from '@/types/project'
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
  
  // Vastu Shastra Engine States
  const [vastuAnalysis, setVastuAnalysis] = useState<VastuAnalysis | null>(null)
  const [isEvaluatingVastu, setIsEvaluatingVastu] = useState(false)
  const [activeVastuTab, setActiveVastuTab] = useState<'defects' | 'good'>('defects')
  const [selectedVastuItem, setSelectedVastuItem] = useState<(VastuGoodAspect | VastuDefect) | null>(null)
  const [isInspectionModalOpen, setIsInspectionModalOpen] = useState(false)

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

  // Auto-trigger evaluation when geometry loads if not already loaded
  useEffect(() => {
    if (hasGeometry && !vastuAnalysis && !isEvaluatingVastu) {
      evaluateVastu(masterJson)
    }
  }, [hasGeometry, masterJson, vastuAnalysis, isEvaluatingVastu, evaluateVastu])

  const handleProcess = async () => {
    if (!projectId) return
    setIsProcessing(true)
    setUploadError(null)
    try {
      const result = await vsaiApi.run(projectId)
      setOutput('vsai_rectifier', result)
      setComponentStatus('vsai_rectifier', 'completed')
      
      // Re-evaluate vastu after rectification
      if (result?.master_json) {
        await evaluateVastu(result.master_json)
      } else {
        await evaluateVastu(masterJson)
      }
    } catch (e: any) {
      setComponentStatus('vsai_rectifier', 'failed')
      setUploadError(e?.response?.data?.detail || e?.message || 'Processing failed')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleFileProcess = async (file: File) => {
    if (!file) return
    setUploadError(null)
    setValidationResult(null)
    setVastuAnalysis(null)
    setIsUploading(true)
    try {
      const response = await projectsApi.uploadMasterJson(file)
      loadProject(response.project)
      
      if (response.validation) {
        setValidationResult(response.validation)
        if (response.validation.vastu_analysis) {
          setVastuAnalysis(response.validation.vastu_analysis)
        }
      }
      
      if (!response.validation?.vastu_analysis) {
        await evaluateVastu(response.project?.master_json)
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (detail?.validation) {
        setValidationResult(detail.validation)
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
    setIsUploading(true)
    try {
      const demoBlob = new Blob([JSON.stringify(DEMO_MASTER_JSON, null, 2)], { type: 'application/json' })
      const demoFile = new File([demoBlob], 'lotus_villa_baseline.json', { type: 'application/json' })
      const response = await projectsApi.uploadMasterJson(demoFile)
      loadProject(response.project)
      if (response.validation?.vastu_analysis) {
        setVastuAnalysis(response.validation.vastu_analysis)
      } else {
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
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
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
                  className="electric-glow text-sm px-6"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                >
                  <Upload className="w-4 h-4 mr-2" /> Select File from Device
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
      ) : (
        /* STATE B: PROJECT GEOMETRY IS LOADED (ACTIVE WORKSPACE) */
        <div className="p-8">
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
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs h-8 gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading || isProcessing}
                >
                  {isUploading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Upload className="w-3.5 h-3.5" />
                  )}
                  Replace JSON
                </Button>
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

                {/* --- VASTU COMPLIANCE SCORE CARD --- */}
                {vastuAnalysis ? (
                  <div className="p-4 rounded-xl bg-card/80 border border-border/80 shadow-sm backdrop-blur space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                          <Compass className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                            Vastu Compliance Score
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

                    {/* Numerical Score Display */}
                    <div className="flex items-end justify-between px-2 py-1 bg-muted/20 rounded-lg border border-border/40">
                      <div>
                        <div className={`text-3xl font-extrabold tracking-tight ${getScoreColor(vastuAnalysis.score)}`}>
                          {vastuAnalysis.score}%
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">
                          {vastuAnalysis.grade_description}
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setActiveVastuTab('defects')}
                          className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all border ${
                            activeVastuTab === 'defects'
                              ? 'bg-destructive/20 border-destructive/50 text-destructive shadow-sm'
                              : 'bg-muted/30 border-transparent text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>{vastuAnalysis.defects.length} Defects</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => setActiveVastuTab('good')}
                          className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all border ${
                            activeVastuTab === 'good'
                              ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400 shadow-sm'
                              : 'bg-muted/30 border-transparent text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>{vastuAnalysis.good_aspects.length} Good</span>
                        </button>
                      </div>
                    </div>

                    {/* Vastu Rules Interactive Inspector List */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span className="font-semibold text-foreground uppercase tracking-wider text-[10px]">
                          {activeVastuTab === 'defects' 
                            ? `Defects & Non-Compliant Areas (${vastuAnalysis.defects.length})` 
                            : `Auspicious Alignments (${vastuAnalysis.good_aspects.length})`
                          }
                        </span>
                        <span className="text-[10px] text-muted-foreground">Click item to inspect in blueprint</span>
                      </div>

                      <div className="max-h-56 overflow-y-auto space-y-2 pr-1">
                        {activeVastuTab === 'defects' ? (
                          vastuAnalysis.defects.length === 0 ? (
                            <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs text-center">
                              No critical Vastu defects detected! Excellent layout.
                            </div>
                          ) : (
                            vastuAnalysis.defects.map((defect, i) => (
                              <div
                                key={defect.rule_id || i}
                                onClick={() => openInspection(defect)}
                                className="group p-3 rounded-xl bg-destructive/10 hover:bg-destructive/15 border border-destructive/30 hover:border-destructive/60 transition-all cursor-pointer flex flex-col gap-1.5 shadow-sm"
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex items-center gap-1.5">
                                    <AlertTriangle className="w-3.5 h-3.5 text-destructive shrink-0 mt-0.5" />
                                    <span className="text-xs font-bold text-destructive group-hover:underline">
                                      {defect.title}
                                    </span>
                                  </div>
                                  <Badge variant="outline" className="text-[9px] uppercase px-1.5 py-0 border-destructive/40 text-destructive bg-destructive/10">
                                    -{defect.points_deducted} pts
                                  </Badge>
                                </div>
                                <div className="text-[11px] text-muted-foreground line-clamp-2">
                                  {defect.description}
                                </div>
                                <div className="flex items-center justify-between pt-1 border-t border-destructive/20 text-[10px]">
                                  <span className="text-foreground/80 font-mono">
                                    {defect.room_name || 'Room'} • {defect.sector_display || defect.sector}
                                  </span>
                                  <span className="text-destructive font-semibold flex items-center gap-1 opacity-90 group-hover:opacity-100">
                                    <Eye className="w-3 h-3" /> Inspect in 2D
                                  </span>
                                </div>
                              </div>
                            ))
                          )
                        ) : (
                          vastuAnalysis.good_aspects.length === 0 ? (
                            <div className="p-4 rounded-lg bg-muted/30 border border-border/50 text-muted-foreground text-xs text-center">
                              No compliant rules identified in this orientation.
                            </div>
                          ) : (
                            vastuAnalysis.good_aspects.map((good, i) => (
                              <div
                                key={good.rule_id || i}
                                onClick={() => openInspection(good)}
                                className="group p-3 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/15 border border-emerald-500/30 hover:border-emerald-500/60 transition-all cursor-pointer flex flex-col gap-1.5 shadow-sm"
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex items-center gap-1.5">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                                    <span className="text-xs font-bold text-emerald-400 group-hover:underline">
                                      {good.title}
                                    </span>
                                  </div>
                                  <Badge variant="outline" className="text-[9px] uppercase px-1.5 py-0 border-emerald-500/40 text-emerald-400 bg-emerald-500/10">
                                    +{good.points_earned} pts
                                  </Badge>
                                </div>
                                <div className="text-[11px] text-muted-foreground line-clamp-2">
                                  {good.description}
                                </div>
                                <div className="flex items-center justify-between pt-1 border-t border-emerald-500/20 text-[10px]">
                                  <span className="text-foreground/80 font-mono">
                                    {good.room_name || 'Room'} • {good.sector_display || good.sector}
                                  </span>
                                  <span className="text-emerald-400 font-semibold flex items-center gap-1 opacity-90 group-hover:opacity-100">
                                    <Eye className="w-3 h-3" /> Inspect in 2D
                                  </span>
                                </div>
                              </div>
                            ))
                          )
                        )}
                      </div>
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
                    <p className="text-xs text-muted-foreground">
                      Running dynamic 3x3 Padavinyasa analysis on floor plan orientation...
                    </p>
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
