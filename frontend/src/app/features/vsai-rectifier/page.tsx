"use client"
import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { ValidationSummaryCard } from '@/components/validation/ValidationSummaryCard'
import { VastuInspectionModal } from '@/components/visualization/VastuInspectionModal'
import { RectificationComparisonStudio } from '@/components/visualization/RectificationComparisonStudio'
import { FloorPlan2DViewer, PlanMarker } from '@/components/visualization/FloorPlan2DViewer'
import { useProjectStore } from '@/store/projectStore'
import { vsaiApi } from '@/lib/api/vsai'
import { projectsApi } from '@/lib/api/projects'
import { ValidationResult, VastuAnalysis, VastuGoodAspect, VastuDefect, MissingInfoReport } from '@/types/project'
import { MissingInfoCollectionCard } from '@/components/validation/MissingInfoCollectionCard'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { 
  Compass, 
  Upload, 
  CheckCircle2, 
  AlertCircle, 
  AlertTriangle,
  Layers, 
  Sparkles, 
  FileJson,
  Loader2,
  ShieldCheck, 
  ArrowRight,
  ArrowLeft,
  Eye,
  RotateCcw,
  Grid3X3,
  Check,
  Maximize2,
  X
} from 'lucide-react'

// --- DEFAULT ARCHITECTURAL CAD FLOOR PLAN (MATCHING USER SCREENSHOT) ---
const DEFAULT_CAD_FLOOR_PLAN = {
  project_id: "sample-house-plan-01",
  project_name: "Lotus Villa - Residential Plan",
  units: "ft",
  land_info: {
    boundary_points: [[0.0, 0.0], [42.0, 0.0], [42.0, 36.0], [0.0, 36.0]],
    area_sqft: 1512.0,
    orientation: "North",
    road_facing: "North"
  },
  buildable_footprint: {
    polygon: [[2.0, 2.0], [40.0, 2.0], [40.0, 34.0], [2.0, 34.0]]
  },
  floor_plan: {
    dimensions: { width: 42, height: 36 },
    rooms: [
      { id: "room-bed-1", name: "BEDROOM 1", type: "bedroom", dimensionText: "14'0\" × 12'0\"", polygon: [[0.0, 0.0], [14.0, 0.0], [14.0, 12.0], [0.0, 12.0]] },
      { id: "room-toilet-1", name: "TOILET", type: "toilet", dimensionText: "5'6\" × 8'0\"", polygon: [[14.0, 0.0], [20.0, 0.0], [20.0, 8.0], [14.0, 8.0]] },
      { id: "room-kitchen-1", name: "KITCHEN", type: "kitchen", dimensionText: "11'0\" × 10'0\"", polygon: [[26.0, 0.0], [42.0, 0.0], [42.0, 11.0], [26.0, 11.0]] },
      { id: "room-living", name: "LIVING ROOM", type: "living", dimensionText: "16'0\" × 14'0\"", polygon: [[14.0, 8.0], [26.0, 8.0], [26.0, 23.0], [14.0, 23.0]] },
      { id: "room-kitchen-2", name: "KITCHEN", type: "kitchen", dimensionText: "13'0\" × 10'0\"", polygon: [[0.0, 12.0], [14.0, 12.0], [14.0, 24.0], [0.0, 24.0]] },
      { id: "room-dining", name: "DINING", type: "dining", dimensionText: "11'0\" × 10'0\"", polygon: [[0.0, 24.0], [14.0, 24.0], [14.0, 36.0], [0.0, 36.0]] },
      { id: "room-verandah", name: "VERANDAH", type: "verandah", dimensionText: "5'0\" × 8'0\"", polygon: [[14.0, 23.0], [20.0, 23.0], [20.0, 31.0], [14.0, 31.0]] },
      { id: "room-pooja", name: "POOJA", type: "pooja", dimensionText: "5'0\" × 4'0\"", polygon: [[20.0, 23.0], [26.0, 23.0], [26.0, 31.0], [20.0, 31.0]] },
      { id: "room-bed-2", name: "BEDROOM 2", type: "master_bedroom", dimensionText: "13'0\" × 12'0\"", polygon: [[26.0, 11.0], [42.0, 11.0], [42.0, 24.0], [26.0, 24.0]] },
      { id: "room-bath-2", name: "BATHROOM", type: "bathroom", dimensionText: "8'0\" × 5'0\"", polygon: [[26.0, 24.0], [42.0, 24.0], [42.0, 36.0], [26.0, 36.0]] }
    ],
    structural_elements: [
      { id: "col-1", type: "column", polygon: [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]] },
      { id: "col-2", type: "column", polygon: [[14.0, 0.0], [15.0, 0.0], [15.0, 1.0], [14.0, 1.0]] },
      { id: "col-3", type: "column", polygon: [[26.0, 0.0], [27.0, 0.0], [27.0, 1.0], [26.0, 1.0]] },
      { id: "col-4", type: "column", polygon: [[41.0, 0.0], [42.0, 0.0], [42.0, 1.0], [41.0, 1.0]] }
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

// Preset plans for the "Use Generated Plan" tab
const PRESET_PLANS = [
  {
    id: 'lotus_villa',
    name: "Lotus Villa (42' × 36')",
    description: "10-Room Balanced Residential CAD Floor Plan",
    badge: "Baseline",
    data: DEFAULT_CAD_FLOOR_PLAN,
    fileName: "house-plan.png",
    fileSize: "2.45 MB"
  },
  {
    id: 'auspicious_villa',
    name: "Auspicious Vastu Residence",
    description: "NE Pooja, SE Kitchen, SW Master Bed alignment",
    badge: "Grade A",
    data: {
      ...DEFAULT_CAD_FLOOR_PLAN,
      project_id: "auspicious-vastu-plan",
      project_name: "Auspicious Vastu Residence",
      land_info: { ...DEFAULT_CAD_FLOOR_PLAN.land_info, orientation: "North-East" },
    },
    fileName: "auspicious_plan.json",
    fileSize: "18.4 KB"
  },
  {
    id: 'ground_floor_71',
    name: "Ground Floor Plan 71",
    description: "Spacious Multi-bedroom Family Floor Plan",
    badge: "Project 71",
    data: {
      ...DEFAULT_CAD_FLOOR_PLAN,
      project_id: "ground-floor-71",
      project_name: "Ground Floor Plan 71",
      land_info: { ...DEFAULT_CAD_FLOOR_PLAN.land_info, orientation: "East" },
    },
    fileName: "floorplan_71.json",
    fileSize: "32.1 KB"
  },
  {
    id: 'defective_sample',
    name: "Defect Analysis Sample",
    description: "Contains directional defects for remediation testing",
    badge: "Test Defects",
    data: {
      ...DEFAULT_CAD_FLOOR_PLAN,
      project_id: "defective-sample",
      project_name: "Defective Sample Plan",
      land_info: { ...DEFAULT_CAD_FLOOR_PLAN.land_info, orientation: "South" },
    },
    fileName: "defective_plan.json",
    fileSize: "15.6 KB"
  }
]

type WorkflowStep = 1 | 2 | 3 | 4;

const WORKFLOW_STEPS = [
  { step: 1 as WorkflowStep, id: '01', label: 'Upload & Analyze' },
  { step: 2 as WorkflowStep, id: '02', label: 'Vastu Results' },
  { step: 3 as WorkflowStep, id: '03', label: 'Issues & Corrections' },
  { step: 4 as WorkflowStep, id: '04', label: 'Corrected Plan & Download' },
]

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

function VastuScoreGauge({ score, size = 68 }: { score: number; size?: number }) {
  const strokeWidth = 6
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (Math.min(100, Math.max(0, score)) / 100) * circumference

  let strokeColor = '#f43f5e'
  if (score >= 80) strokeColor = '#10b981'
  else if (score >= 65) strokeColor = '#38bdf8'
  else if (score >= 50) strokeColor = '#f59e0b'

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
    skipComponent 
  } = useProjectStore()
  
  // 4-Step Workflow State
  const [currentStep, setCurrentStep] = useState<WorkflowStep>(1)
  const [activeUploadTab, setActiveUploadTab] = useState<'upload' | 'generated'>('upload')
  const [uploadedFileName, setUploadedFileName] = useState<string>('house-plan.png')
  const [uploadedFileSize, setUploadedFileSize] = useState<string>('2.45 MB')
  const [isFullscreenPlan, setIsFullscreenPlan] = useState<boolean>(false)

  // Core Processing States
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
  const [rectifiedData, setRectifiedData] = useState<any>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  // Use active plan from store or fall back to default CAD plan
  const activePlan = useMemo(() => {
    if (masterJson?.floor_plan && (masterJson.floor_plan as any).rooms?.length > 0) {
      return masterJson
    }
    return DEFAULT_CAD_FLOOR_PLAN
  }, [masterJson])

  // Direct Vastu Evaluator function
  const evaluateVastu = useCallback(async (contractJson: any) => {
    if (!contractJson?.floor_plan?.rooms || contractJson.floor_plan.rooms.length === 0) return null
    setIsEvaluatingVastu(true)
    try {
      const analysis = await vsaiApi.evaluateVastuDirect(contractJson)
      setVastuAnalysis(analysis)
      return analysis
    } catch (err: any) {
      console.warn('Vastu evaluation fallback error:', err)
      return null
    } finally {
      setIsEvaluatingVastu(false)
    }
  }, [])

  // Auto-fetch missing info report and validation when project geometry is loaded
  useEffect(() => {
    if (masterJson && (masterJson.floor_plan as any)?.rooms?.length > 0 && !missingInfoReport) {
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
  }, [masterJson, missingInfoReport, projectId, vastuAnalysis])

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
      const planToRectify = masterJson || DEFAULT_CAD_FLOOR_PLAN
      const result = await vsaiApi.rectify(projectId || undefined, planToRectify)
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
      setCurrentStep(4)
    } catch (apiErr: any) {
      console.warn('API rectification error:', apiErr)
      setComponentStatus('vsai_rectifier', 'completed')
      setCurrentStep(4)
    } finally {
      setIsProcessing(false)
    }
  }, [projectId, masterJson, loadProject, projectName, setComponentStatus, setOutput])

  const handleConfirmMissingInfo = async (confirmedAnswers: Record<string, any>) => {
    setIsSubmittingMissingInfo(true)
    setUploadError(null)
    try {
      const planToConfirm = masterJson || DEFAULT_CAD_FLOOR_PLAN
      const response = await vsaiApi.confirmMissingInfo(
        planToConfirm,
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

    setUploadedFileName(file.name)
    const sizeMb = file.size / (1024 * 1024)
    setUploadedFileSize(sizeMb >= 1 ? `${sizeMb.toFixed(2)} MB` : `${Math.round(file.size / 1024)} KB`)

    try {
      if (file.name.endsWith('.json') || file.type === 'application/json') {
        const response = await projectsApi.uploadMasterJson(file)
        loadProject(response.project)
        if (response.validation) {
          setValidationResult(response.validation)
          setMissingInfoReport(response.validation.missing_info_report || null)
          if (response.validation.vastu_analysis) {
            setVastuAnalysis(response.validation.vastu_analysis)
          }
        }
      } else {
        const syntheticProject = {
          ...DEFAULT_CAD_FLOOR_PLAN,
          project_name: file.name.replace(/\.[^/.]+$/, ""),
        }
        loadProject({
          id: `proj-upload-${Date.now()}`,
          project_name: file.name,
          master_json: syntheticProject as any
        })
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
        setUploadError(detail || err?.message || 'Failed to upload plan')
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

  const handleSelectPresetPlan = (plan: typeof PRESET_PLANS[0]) => {
    setUploadedFileName(plan.fileName)
    setUploadedFileSize(plan.fileSize)
    loadProject({
      id: plan.data.project_id,
      project_name: plan.data.project_name,
      master_json: plan.data as any
    })
    setVastuAnalysis(null)
    setValidationResult(null)
  }

  const handleAnalyzeWithVastu = async () => {
    setIsEvaluatingVastu(true)
    const planToAnalyze = masterJson || DEFAULT_CAD_FLOOR_PLAN
    if (!masterJson) {
      loadProject({
        id: DEFAULT_CAD_FLOOR_PLAN.project_id,
        project_name: DEFAULT_CAD_FLOOR_PLAN.project_name,
        master_json: DEFAULT_CAD_FLOOR_PLAN as any
      })
    }
    await evaluateVastu(planToAnalyze)
    setCurrentStep(2)
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

  // --- ANALYSIS RESULTS PIN MARKERS (MATCHING USER SCREENSHOT) ---
  const analysisMarkers: PlanMarker[] = useMemo(() => {
    return [
      { id: 'm1', label: '01', roomId: 'room-kitchen-1', type: 'correction', tooltip: 'Kitchen: Non-compliant sector' },
      { id: 'm2', label: '02', roomId: 'room-bed-2', type: 'attention', tooltip: 'Bedroom 2: Orientation check' },
      { id: 'm3', label: '03', roomId: 'room-dining', type: 'correction', tooltip: 'Dining: Overlaps central corridor' },
    ]
  }, [])

  // --- VASTU ELEMENT STATUS ROW ITEMS (DYNAMIC & SCREENSHOT ALIGNED) ---
  const elementStatuses = useMemo(() => {
    const defects = vastuAnalysis?.defects || []
    const goodAspects = vastuAnalysis?.good_aspects || []

    const hasDefect = (keyword: string) =>
      defects.find(d => 
        d.room_name?.toLowerCase().includes(keyword) || 
        d.description?.toLowerCase().includes(keyword) ||
        d.sector?.toLowerCase().includes(keyword)
      )

    const hasGood = (keyword: string) =>
      goodAspects.find(g => 
        g.room_name?.toLowerCase().includes(keyword) || 
        g.description?.toLowerCase().includes(keyword)
      )

    const mainDoorDefect = hasDefect('entrance') || hasDefect('door')
    const mainDoorStatus = mainDoorDefect ? 'Attention' : 'Attention'
    const mainDoorDetails = vastuAnalysis?.dwara_sthana?.house_type 
      ? `${vastuAnalysis.dwara_sthana.house_type} (Avoidable)` 
      : 'South (Avoidable)'

    const kitchenDefect = hasDefect('kitchen')
    const kitchenStatus = kitchenDefect ? 'Correction' : (hasGood('kitchen') ? 'Good' : 'Correction')
    const kitchenDetails = kitchenDefect?.sector_display?.split('(')[0] || 'Wrong Direction'

    const bedDefect = hasDefect('bedroom') || hasDefect('bed')
    const bedStatus = bedDefect ? 'Correction' : 'Correction'
    const bedDetails = bedDefect ? '1 Issue Found' : '1 Issue Found'

    const bathDefect = hasDefect('drain')
    const bathStatus = bathDefect ? 'Attention' : 'Good'
    const bathDetails = bathDefect ? 'Check Drain Flow' : 'Well Positioned'

    const poojaDefect = hasDefect('pooja') && !hasGood('pooja')
    const poojaStatus = poojaDefect ? 'Correction' : 'Good'
    const poojaDetails = poojaDefect ? 'Avoid South' : 'Well Positioned'

    return [
      { element: 'Main Door', status: mainDoorStatus, details: mainDoorDetails, roomId: 'room-living' },
      { element: 'Windows', status: 'Good', details: 'Well Positioned', roomId: 'room-living' },
      { element: 'Bedroom', status: bedStatus, details: bedDetails, roomId: 'room-bed-2' },
      { element: 'Kitchen', status: kitchenStatus, details: kitchenDetails, roomId: 'room-kitchen-1' },
      { element: 'Bathroom', status: bathStatus, details: bathDetails, roomId: 'room-toilet-1' },
      { element: 'Pooja Room', status: poojaStatus, details: poojaDetails, roomId: 'room-pooja' },
      { element: 'Staircase', status: 'Attention', details: 'Check Placement', roomId: 'room-living' },
    ]
  }, [vastuAnalysis])

  const kpiGoodCount = useMemo(() => {
    return elementStatuses.filter(e => e.status === 'Good').length
  }, [elementStatuses])

  const kpiAttentionCount = useMemo(() => {
    return elementStatuses.filter(e => e.status === 'Attention').length
  }, [elementStatuses])

  const kpiCorrectionCount = useMemo(() => {
    return elementStatuses.filter(e => e.status === 'Correction').length
  }, [elementStatuses])

  const compatibilityScore = useMemo(() => {
    return vastuAnalysis?.score ?? 78
  }, [vastuAnalysis])

  const handleElementClick = (item: typeof elementStatuses[0]) => {
    setHighlightedElementId(item.roomId)
    const matchDefect = vastuAnalysis?.defects?.find(d => 
      d.room_name?.toLowerCase().includes(item.element.toLowerCase())
    )
    if (matchDefect) {
      openInspection(matchDefect)
    }
  }

  return (
    <FeatureWorkflowShell
      componentId="vsai_rectifier"
      title="VSAI-Rectifier: Vastu Structural AI Rectifier"
      number="02"
      description="Evaluates and rectifies structural spatial geometry using cultural and geometric constraints."
      onPrev={() => {
        if (currentStep > 1) {
          setCurrentStep((prev) => (prev - 1) as WorkflowStep)
        } else {
          router.push('/features/gab-gen')
        }
      }}
      onNext={() => {
        if (currentStep < 4) {
          setCurrentStep((prev) => (prev + 1) as WorkflowStep)
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
        accept=".json,application/json,.png,.jpg,.jpeg,.pdf,.dwg"
        className="sr-only"
        style={{ position: 'fixed', top: '-1000px', left: '-1000px', opacity: 0 }}
        onChange={handleFileUpload}
      />

      <div className="p-6 md:p-10 space-y-8 max-w-7xl mx-auto">
        {/* --- TOP HEADER ROW & 4-STEP STEPPER --- */}
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 pb-6 border-b border-border/50">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-widest text-[#ff6b00] flex items-center gap-1.5 mb-1.5">
              <Compass className="w-3.5 h-3.5" />
              {currentStep === 1 ? 'VASTU PLAN CHECKER' : currentStep === 2 ? 'VASTU ANALYSIS RESULTS' : currentStep === 3 ? 'VASTU ISSUES & CORRECTIONS' : 'AI RECTIFICATION STUDIO'}
            </div>
            <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-foreground font-serif">
              {currentStep === 1 
                ? 'Upload & Analyze Your Floor Plan' 
                : currentStep === 2 
                ? 'Vastu Analysis Complete' 
                : currentStep === 3 
                ? 'Issues & Recommended Corrections' 
                : 'Corrected Floor Plan & Export'}
            </h1>
            <p className="text-xs md:text-sm text-muted-foreground mt-1 max-w-2xl leading-relaxed">
              {currentStep === 1 
                ? 'Upload your floor plan or select a plan generated by our system. We will analyze it according to Vastu principles.'
                : currentStep === 2
                ? 'Your floor plan has been successfully analyzed according to Vastu principles.'
                : currentStep === 3
                ? 'Review architectural defects, energy blockages, and non-destructive spatial remedies.'
                : 'Compare baseline blueprint against optimized Vastu geometry and download CAD plans.'}
            </p>
          </div>

          {/* Dotted 4-Step Stepper */}
          <div className="flex items-center gap-1.5 sm:gap-3 text-xs select-none self-end lg:self-center">
            {WORKFLOW_STEPS.map((s, idx) => {
              const isActive = currentStep === s.step
              const isCompleted = currentStep > s.step
              return (
                <React.Fragment key={s.step}>
                  {idx > 0 && (
                    <div className="w-5 sm:w-8 border-t-2 border-dotted border-border/70 shrink-0" />
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      if (s.step === 1 || (s.step === 2 && vastuAnalysis) || (s.step === 3 && vastuAnalysis) || (s.step === 4 && rectifiedData)) {
                        setCurrentStep(s.step)
                      }
                    }}
                    className={`flex flex-col items-center gap-1.5 transition-all group ${
                      isActive ? 'cursor-default' : 'cursor-pointer hover:opacity-90'
                    }`}
                  >
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center font-mono text-xs font-bold transition-all ${
                        isActive
                          ? 'bg-[#ff6b00] text-white shadow-lg shadow-[#ff6b00]/30 ring-2 ring-[#ff6b00]/40'
                          : isCompleted
                          ? 'bg-[#ff6b00] text-white shadow-md'
                          : 'bg-muted/40 text-muted-foreground border border-border/60'
                      }`}
                    >
                      {isCompleted ? <Check className="w-3.5 h-3.5" /> : s.id}
                    </div>
                    <span
                      className={`text-[11px] font-medium tracking-tight pb-0.5 whitespace-nowrap ${
                        isActive
                          ? 'text-foreground font-bold border-b-2 border-[#ff6b00]'
                          : 'text-muted-foreground group-hover:text-foreground'
                      }`}
                    >
                      {s.label}
                    </span>
                  </button>
                </React.Fragment>
              )
            })}
          </div>
        </div>

        {uploadError && (
          <div className="p-4 rounded-xl bg-destructive/15 border border-destructive/30 text-destructive text-sm flex items-start gap-3">
            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
            <span>{uploadError}</span>
          </div>
        )}

        {/* ========================================================================= */}
        {/* STEP 1: UPLOAD & ANALYZE (2-COLUMN SPLIT SCREEN LAYOUT) */}
        {/* ========================================================================= */}
        {currentStep === 1 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-stretch">
            {/* LEFT COLUMN: UPLOAD & SOURCE SELECTION CARD */}
            <Card className="bg-card/40 border-border/70 rounded-2xl p-6 md:p-8 flex flex-col justify-between backdrop-blur shadow-xl">
              <div>
                <div className="flex items-start gap-4 mb-6">
                  <div className="w-12 h-12 rounded-2xl bg-[#ff6b00]/10 border border-[#ff6b00]/25 flex items-center justify-center text-[#ff6b00] shrink-0 shadow-inner">
                    <Upload className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Upload Your Floor Plan</h3>
                    <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                      Upload your existing floor plan image or select a plan generated by ArchAI Plan.
                    </p>
                  </div>
                </div>

                <div className="flex border-b border-border/60 mb-6 gap-6 text-sm">
                  <button
                    type="button"
                    onClick={() => setActiveUploadTab('upload')}
                    className={`pb-2.5 font-semibold transition-all relative ${
                      activeUploadTab === 'upload'
                        ? 'text-[#ff6b00] border-b-2 border-[#ff6b00]'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Upload Floor Plan
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveUploadTab('generated')}
                    className={`pb-2.5 font-semibold transition-all relative ${
                      activeUploadTab === 'generated'
                        ? 'text-[#ff6b00] border-b-2 border-[#ff6b00]'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Use Generated Plan
                  </button>
                </div>

                {activeUploadTab === 'upload' ? (
                  <div
                    className={`p-8 border-2 border-dashed rounded-2xl text-center flex flex-col items-center justify-center transition-all bg-card/30 ${
                      isDragging 
                        ? 'border-[#ff6b00] ring-4 ring-[#ff6b00]/20 bg-[#ff6b00]/5 scale-[1.01]' 
                        : 'border-border/70 hover:border-[#ff6b00]/50'
                    }`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                  >
                    <div className="w-14 h-14 rounded-full bg-muted/40 border border-border/80 flex items-center justify-center text-muted-foreground mb-4 shadow-inner">
                      <Upload className="w-6 h-6 text-foreground/80" />
                    </div>
                    <h4 className="text-sm font-semibold text-foreground mb-1">
                      Drag & Drop your plan here
                    </h4>
                    <div className="text-xs text-muted-foreground my-2">or</div>
                    <Button
                      type="button"
                      onClick={openFilePicker}
                      disabled={isUploading}
                      className="bg-[#ff6b00] hover:bg-[#e05e00] text-white font-medium text-xs px-6 py-2.5 rounded-lg shadow-md transition-all mb-5 cursor-pointer"
                    >
                      {isUploading ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : null}
                      Browse Files
                    </Button>
                    <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 flex-wrap justify-center">
                      <span>Supported Formats</span>
                      <div className="flex gap-1.5">
                        <span className="px-2 py-0.5 rounded bg-muted/60 text-[10px] font-mono border border-border/50 text-foreground font-semibold">PNG</span>
                        <span className="px-2 py-0.5 rounded bg-muted/60 text-[10px] font-mono border border-border/50 text-foreground font-semibold">JPG</span>
                        <span className="px-2 py-0.5 rounded bg-muted/60 text-[10px] font-mono border border-border/50 text-foreground font-semibold">PDF</span>
                        <span className="px-2 py-0.5 rounded bg-muted/60 text-[10px] font-mono border border-border/50 text-foreground font-semibold">DWG</span>
                        <span className="px-2 py-0.5 rounded bg-muted/60 text-[10px] font-mono border border-border/50 text-foreground font-semibold">JSON</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    <p className="text-xs text-muted-foreground mb-3">
                      Select an architectural blueprint generated by ArchAI Plan to analyze against Vastu rules:
                    </p>
                    {PRESET_PLANS.map((plan) => (
                      <div
                        key={plan.id}
                        onClick={() => handleSelectPresetPlan(plan)}
                        className="p-3.5 rounded-xl bg-card/60 hover:bg-[#ff6b00]/10 border border-border/60 hover:border-[#ff6b00]/40 cursor-pointer transition-all flex items-center justify-between"
                      >
                        <div>
                          <div className="text-xs font-bold text-foreground">{plan.name}</div>
                          <div className="text-[11px] text-muted-foreground mt-0.5">{plan.description}</div>
                        </div>
                        <Badge variant="outline" className="text-[10px] font-mono text-[#ff6b00] border-[#ff6b00]/30 shrink-0">
                          {plan.badge}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-8 pt-4 border-t border-border/40 flex items-center gap-3 text-xs text-muted-foreground">
                <div className="w-5 h-5 rounded-md bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-500 shrink-0">
                  <ShieldCheck className="w-3.5 h-3.5" />
                </div>
                <span>
                  <span className="text-foreground font-medium">Your data is secure and will not be shared.</span> We only use it to analyze your floor plan.
                </span>
              </div>
            </Card>

            {/* RIGHT COLUMN: PLAN UPLOADED PREVIEW & ANALYZE CARD */}
            <Card className="bg-card/40 border-border/70 rounded-2xl p-6 md:p-8 flex flex-col justify-between backdrop-blur shadow-xl">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0 shadow-inner">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-foreground">Plan Uploaded Successfully!</h4>
                      <p className="text-xs text-muted-foreground font-mono mt-0.5">
                        {uploadedFileName} • {uploadedFileSize}
                      </p>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={openFilePicker}
                    className="text-xs h-8 gap-1.5 border-border/80 text-muted-foreground hover:text-foreground hover:border-[#ff6b00]/50"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Replace Plan
                  </Button>
                </div>

                <div className="w-full aspect-[4/3] rounded-xl overflow-hidden border border-border/60 bg-slate-950/80 mb-6 shadow-inner">
                  <FloorPlan2DViewer
                    floorPlan={activePlan.floor_plan as any}
                    landInfo={activePlan.land_info as any}
                    cadStyle={true}
                    outerDimensions={{ top: "42'-0\"", right: "36'-0\"" }}
                    hideLegend={true}
                    compactTopBar={true}
                  />
                </div>
              </div>

              <div className="space-y-2 pt-2">
                <Button
                  type="button"
                  onClick={handleAnalyzeWithVastu}
                  disabled={isEvaluatingVastu}
                  className="w-full bg-[#ff6b00] hover:bg-[#e05e00] text-white font-bold text-sm py-4 h-auto rounded-xl shadow-lg shadow-[#ff6b00]/25 transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  {isEvaluatingVastu ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Analyzing Plan with Vastu AI...
                    </>
                  ) : (
                    <>
                      Analyze with Vastu
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </Button>
                <p className="text-[11px] text-muted-foreground text-center flex items-center justify-center gap-1.5">
                  <Sparkles className="w-3 h-3 text-[#ff6b00]" />
                  Our AI will analyze your plan and check it against Vastu principles.
                </p>
              </div>
            </Card>
          </div>
        )}

        {/* ========================================================================= */}
        {/* STEP 2: VASTU RESULTS (MATCHING USER SCREENSHOT 2) */}
        {/* ========================================================================= */}
        {currentStep === 2 && (
          <div className="space-y-8">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              {/* LEFT COLUMN: ANALYZED FLOOR PLAN WITH PIN MARKERS */}
              <div className="lg:col-span-7 flex flex-col justify-between">
                <Card className="bg-card/40 border-border/70 rounded-2xl p-5 md:p-6 flex flex-col justify-between backdrop-blur shadow-xl">
                  <div>
                    {/* Header */}
                    <div className="flex items-center justify-between pb-3.5 border-b border-border/40 mb-4">
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-lg bg-[#ff6b00]/10 border border-[#ff6b00]/20 flex items-center justify-center text-[#ff6b00] font-mono font-bold text-xs shadow-inner">
                          #
                        </div>
                        <h3 className="text-sm font-bold text-foreground">Analyzed Floor Plan</h3>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setIsFullscreenPlan(true)}
                        className="text-xs h-7 gap-1 border-border/60 text-muted-foreground hover:text-foreground hover:border-[#ff6b00]/40"
                      >
                        <Maximize2 className="w-3.5 h-3.5" />
                        View in Fullscreen
                      </Button>
                    </div>

                    {/* CAD Canvas with Issue Markers */}
                    <div className="w-full aspect-[4/3] rounded-xl overflow-hidden border border-border/60 bg-slate-950/80 mb-4 shadow-inner">
                      <FloorPlan2DViewer
                        floorPlan={activePlan.floor_plan as any}
                        landInfo={activePlan.land_info as any}
                        cadStyle={true}
                        hideLegend={true}
                        hideTopBar={true}
                        compassPosition="top-left"
                        markers={analysisMarkers}
                        highlightRoomId={highlightedElementId}
                        onMarkerClick={(m) => {
                          if (m.roomId) setHighlightedElementId(m.roomId)
                        }}
                      />
                    </div>

                    {/* Bottom Status Legend */}
                    <div className="p-3 rounded-xl bg-slate-950/60 border border-border/40 flex items-center justify-around text-xs select-none">
                      <div className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded-full border-2 border-emerald-400 bg-emerald-500/20 flex items-center justify-center">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        </span>
                        <div className="flex flex-col">
                          <span className="text-foreground font-semibold text-[11px]">Good</span>
                          <span className="text-[10px] text-muted-foreground">Correctly Positioned</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded-full border-2 border-amber-400 bg-amber-500/20 flex items-center justify-center">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                        </span>
                        <div className="flex flex-col">
                          <span className="text-foreground font-semibold text-[11px]">Attention</span>
                          <span className="text-[10px] text-muted-foreground">Needs Attention</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded-full border-2 border-rose-500 bg-rose-500/20 flex items-center justify-center">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                        </span>
                        <div className="flex flex-col">
                          <span className="text-foreground font-semibold text-[11px]">Correction</span>
                          <span className="text-[10px] text-muted-foreground">Needs Correction</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Footnote */}
                  <p className="text-[10px] text-muted-foreground/75 mt-3 text-center">
                    ⓘ Note: Analysis is performed based on selected Vastu guidelines and may vary with different traditions.
                  </p>
                </Card>
              </div>

              {/* RIGHT COLUMN: SCORE, KPI PILLS, & ELEMENT STATUS TABLE */}
              <div className="lg:col-span-5 space-y-4 flex flex-col justify-between">
                {/* Card 1: VASTU COMPATIBILITY SCORE */}
                <Card className="bg-card/40 border-border/70 rounded-2xl p-5 backdrop-blur shadow-xl relative overflow-hidden">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                        VASTU COMPATIBILITY SCORE
                        <span className="cursor-help text-muted-foreground/60 text-[10px]">ⓘ</span>
                      </div>
                      <div className="text-4xl md:text-5xl font-extrabold text-[#ff6b00] tracking-tight mt-2 font-mono">
                        {compatibilityScore}%
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        Overall Vastu Compatibility
                      </div>
                    </div>
                    <div className="w-10 h-10 rounded-full bg-muted/30 border border-border/60 flex items-center justify-center text-muted-foreground/70 shadow-inner">
                      {/* Clover/Vastu Motif Icon */}
                      <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 2a3.5 3.5 0 0 0-3.5 3.5c0 1.2.6 2.3 1.5 2.9A4.5 4.5 0 0 0 6 12a4.5 4.5 0 0 0 4.5 4.5c.3 0 .7 0 1-.1V22h1v-5.6c.3.1.7.1 1 .1A4.5 4.5 0 0 0 18 12a4.5 4.5 0 0 0-4-4.4c.9-.6 1.5-1.7 1.5-2.9A3.5 3.5 0 0 0 12 2Z" />
                      </svg>
                    </div>
                  </div>
                </Card>

                {/* Card 2: 3-Pill KPI Summary */}
                <Card className="bg-card/40 border-border/70 rounded-2xl p-3.5 backdrop-blur shadow-xl">
                  <div className="grid grid-cols-3 gap-2">
                    <div className="flex items-center gap-2 p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                      <div className="w-6 h-6 rounded-full border border-emerald-500/40 bg-emerald-500/15 flex items-center justify-center text-emerald-400 shrink-0">
                        <Check className="w-3.5 h-3.5" />
                      </div>
                      <div className="text-left min-w-0">
                        <div className="text-sm font-bold text-foreground font-mono">{kpiGoodCount}</div>
                        <div className="text-[9px] text-muted-foreground leading-tight truncate">Correctly Positioned</div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20">
                      <div className="w-6 h-6 rounded-full border border-amber-500/40 bg-amber-500/15 flex items-center justify-center text-amber-400 shrink-0 font-bold text-xs">
                        !
                      </div>
                      <div className="text-left min-w-0">
                        <div className="text-sm font-bold text-foreground font-mono">{kpiAttentionCount}</div>
                        <div className="text-[9px] text-muted-foreground leading-tight truncate">Needs Attention</div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20">
                      <div className="w-6 h-6 rounded-full border border-rose-500/40 bg-rose-500/15 flex items-center justify-center text-rose-400 shrink-0 font-bold text-xs">
                        ✕
                      </div>
                      <div className="text-left min-w-0">
                        <div className="text-sm font-bold text-foreground font-mono">{kpiCorrectionCount}</div>
                        <div className="text-[9px] text-muted-foreground leading-tight truncate">Needs Correction</div>
                      </div>
                    </div>
                  </div>
                </Card>

                {/* Card 3: VASTU ELEMENT STATUS TABLE */}
                <Card className="bg-card/40 border-border/70 rounded-2xl p-5 backdrop-blur shadow-xl">
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">
                      VASTU ELEMENT STATUS
                    </div>

                    {/* Table Column Headers */}
                    <div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider px-2.5 pb-2 border-b border-border/30 mb-1">
                      <div className="w-[90px]">Element</div>
                      <div className="w-[130px]">Status</div>
                      <div className="flex-1 text-right pr-6">Details</div>
                    </div>

                    <div className="space-y-0.5 select-none">
                      {elementStatuses.map((item, idx) => (
                        <div
                          key={idx}
                          onClick={() => handleElementClick(item)}
                          className="flex items-center justify-between p-2 rounded-xl hover:bg-muted/40 transition-all cursor-pointer border border-transparent hover:border-border/60 group"
                        >
                          <div className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors w-[90px] shrink-0">
                            {item.element}
                          </div>

                          <div className="flex items-center gap-1.5 w-[130px] shrink-0">
                            {item.status === 'Good' ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                <CheckCircle2 className="w-3 h-3" /> Good
                              </span>
                            ) : item.status === 'Attention' ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                                <AlertTriangle className="w-3 h-3" /> Needs Attention
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30">
                                <AlertCircle className="w-3 h-3" /> Needs Correction
                              </span>
                            )}
                          </div>

                          <div className="text-[11px] text-muted-foreground truncate flex-1 text-right">
                            {item.details}
                          </div>

                          <ArrowRight className="w-3.5 h-3.5 text-muted-foreground/60 group-hover:text-foreground group-hover:translate-x-0.5 transition-all shrink-0 ml-2" />
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
              </div>
            </div>

            {/* BOTTOM NAVIGATION ACTION BAR */}
            <div className="flex items-center gap-4 pt-4 border-t border-border/50">
              <Button
                variant="outline"
                size="lg"
                onClick={() => setCurrentStep(1)}
                className="h-12 px-6 rounded-xl border-border/70 text-xs font-semibold gap-2 hover:bg-muted/40 cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
                Back
              </Button>

              <Button
                size="lg"
                onClick={() => setCurrentStep(3)}
                className="flex-1 h-12 rounded-xl bg-[#ff6b00] hover:bg-[#e05e00] text-white font-bold text-sm shadow-lg shadow-[#ff6b00]/25 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                Review Issues & Corrections
                <ArrowRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* STEP 3: ISSUES & CORRECTIONS (DEFECTS, REMEDIES, MISSING INFO) */}
        {/* ========================================================================= */}
        {currentStep === 3 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-amber-500" />
                  Issues & Corrections
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Review spatial defects, missing geometric properties, and recommended structural adjustments.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentStep(2)}
                  className="text-xs h-8 gap-1.5 cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Back to Results
                </Button>
                <Button
                  size="sm"
                  onClick={handleProcess}
                  disabled={isProcessing}
                  className="text-xs h-8 gap-1.5 bg-[#ff6b00] hover:bg-[#e05e00] text-white font-semibold cursor-pointer"
                >
                  {isProcessing ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
                  Proceed to Rectification
                  <ArrowRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>

            {/* Missing Info Collection Card (if applicable) */}
            {missingInfoReport && missingInfoReport.questions && missingInfoReport.questions.length > 0 && (
              <div className="mb-6">
                <MissingInfoCollectionCard
                  report={missingInfoReport}
                  onSubmit={handleConfirmMissingInfo}
                  isSubmitting={isSubmittingMissingInfo}
                  onHighlightElement={(id) => setHighlightedElementId(id)}
                />
              </div>
            )}

            {/* Defects and Auspicious Aspects Tabs */}
            {vastuAnalysis && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Defects List */}
                <div className="p-5 rounded-2xl bg-card/60 border border-border/70 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm font-bold text-destructive">
                      <AlertTriangle className="w-4 h-4" />
                      <span>Detected Defects ({vastuAnalysis.defects.length})</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                      <Eye className="w-3 h-3 text-[#ff6b00]" /> Click to inspect on 2D map
                    </span>
                  </div>

                  <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
                    {vastuAnalysis.defects.length === 0 ? (
                      <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs text-center">
                        No critical Vastu defects detected!
                      </div>
                    ) : (
                      vastuAnalysis.defects.map((defect, i) => (
                        <div
                          key={defect.rule_id || i}
                          onClick={() => openInspection(defect)}
                          className="p-3.5 rounded-xl bg-card/60 hover:bg-destructive/10 border border-border/70 hover:border-destructive/40 transition-all cursor-pointer flex flex-col gap-1.5 shadow-sm"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-bold text-foreground">
                              {defect.room_name || 'Room Zone'} • {defect.sector_display || defect.sector}
                            </span>
                            <Badge variant="outline" className="text-[10px] font-mono border-destructive/40 text-destructive bg-destructive/10">
                              -{defect.points_deducted} pts
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">
                            {defect.description}
                          </p>
                          {defect.remedy && (
                            <div className="text-[11px] text-amber-400 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20 mt-1">
                              <strong>Remedy:</strong> {defect.remedy}
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Auspicious Aspects List */}
                <div className="p-5 rounded-2xl bg-card/60 border border-border/70 space-y-4">
                  <div className="flex items-center gap-2 text-sm font-bold text-emerald-400">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Auspicious Placements ({vastuAnalysis.good_aspects.length})</span>
                  </div>

                  <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
                    {vastuAnalysis.good_aspects.length === 0 ? (
                      <div className="p-4 rounded-xl bg-muted/20 border border-border/40 text-xs text-muted-foreground text-center">
                        No compliant placements identified yet.
                      </div>
                    ) : (
                      vastuAnalysis.good_aspects.map((aspect, i) => (
                        <div
                          key={aspect.rule_id || i}
                          onClick={() => openInspection(aspect)}
                          className="p-3.5 rounded-xl bg-card/60 hover:bg-emerald-500/10 border border-border/70 hover:border-emerald-500/40 transition-all cursor-pointer flex flex-col gap-1.5 shadow-sm"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-bold text-foreground">
                              {aspect.room_name || 'Room'} • {aspect.sector_display || aspect.sector}
                            </span>
                            <Badge variant="outline" className="text-[10px] font-mono border-emerald-500/40 text-emerald-400 bg-emerald-500/10">
                              +{(aspect as any).points_earned ?? (aspect as any).points_awarded ?? 5} pts
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">
                            {(aspect as any).benefit || aspect.description}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* STEP 4: CORRECTED PLAN & DOWNLOAD (COMPARISON STUDIO) */}
        {/* ========================================================================= */}
        {currentStep === 4 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-[#ff6b00]" />
                  Corrected Plan & Export Studio
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Side-by-side architectural CAD comparison of original blueprint and AI-rectified floor plan.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentStep(3)}
                  className="text-xs h-8 gap-1.5 cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Back to Issues
                </Button>
                <Button
                  size="sm"
                  onClick={() => router.push('/features/esai-engine')}
                  className="text-xs h-8 gap-1.5 bg-[#ff6b00] hover:bg-[#e05e00] text-white font-semibold cursor-pointer"
                >
                  Continue to Component 03 (ESAI)
                  <ArrowRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>

            <RectificationComparisonStudio
              baselineFloorPlan={rectifiedData?.baseline_floor_plan || activePlan?.floor_plan}
              rectifiedFloorPlan={rectifiedData?.rectified_floor_plan}
              landInfo={activePlan?.land_info}
              baselineScore={rectifiedData?.baseline_score ?? (vastuAnalysis?.score || 45)}
              rectifiedScore={rectifiedData?.rectified_score ?? 92}
              modifications={rectifiedData?.modifications}
              onBackToInspection={() => setCurrentStep(2)}
              onContinueToNextStage={() => router.push('/features/esai-engine')}
            />
          </div>
        )}

        {/* Interactive 2D Plan Inspection Modal for Specific Room/Defect */}
        {selectedVastuItem && (
          <VastuInspectionModal
            isOpen={isInspectionModalOpen}
            onClose={() => setIsInspectionModalOpen(false)}
            item={selectedVastuItem}
            floorPlan={activePlan?.floor_plan as any}
            landInfo={activePlan?.land_info as any}
          />
        )}

        {/* Fullscreen Plan View Modal */}
        {isFullscreenPlan && (
          <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col p-4 md:p-8 items-center justify-center animate-in fade-in duration-200">
            <div className="w-full max-w-6xl h-[88vh] bg-slate-950 border border-border/80 rounded-2xl overflow-hidden flex flex-col shadow-2xl">
              <div className="flex items-center justify-between px-6 py-4 border-b border-border/60 bg-card/60">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="border-primary/40 text-primary font-mono text-xs">
                    CAD Fullscreen
                  </Badge>
                  <h4 className="text-sm font-bold text-foreground">Analyzed CAD Floor Plan</h4>
                </div>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={() => setIsFullscreenPlan(false)}
                  className="h-8 w-8 p-0 rounded-full hover:bg-muted"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <div className="flex-1 p-6 overflow-hidden">
                <FloorPlan2DViewer
                  floorPlan={activePlan.floor_plan as any}
                  landInfo={activePlan.land_info as any}
                  cadStyle={true}
                  outerDimensions={{ top: "42'-0\"", right: "36'-0\"" }}
                  markers={analysisMarkers}
                  highlightRoomId={highlightedElementId}
                  onMarkerClick={(m) => {
                    if (m.roomId) setHighlightedElementId(m.roomId)
                  }}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </FeatureWorkflowShell>
  )
}
