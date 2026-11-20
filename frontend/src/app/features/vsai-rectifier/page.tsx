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
  X,
  Download,
  Image as ImageIcon,
  Building2,
  Focus
} from 'lucide-react'

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
    resetProject,
    setComponentStatus, 
    setOutput, 
    skipComponent 
  } = useProjectStore()
  
  // 4-Step Workflow State
  const [currentStep, setCurrentStep] = useState<WorkflowStep>(1)
  const [activeUploadTab, setActiveUploadTab] = useState<'upload' | 'generated'>('upload')
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null)
  const [uploadedFileSize, setUploadedFileSize] = useState<string | null>(null)
  const [isFullscreenPlan, setIsFullscreenPlan] = useState<boolean>(false)
  const [uploadedImageSrc, setUploadedImageSrc] = useState<string | null>(null)
  const [planViewMode, setPlanViewMode] = useState<'cad' | 'image' | 'overlay'>('cad')
  const [segmentationMeta, setSegmentationMeta] = useState<any>(null)



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

  // Floor and Room Scope Dropdowns for previewing specific project spaces
  const [selectedFloorIndex, setSelectedFloorIndex] = useState<number | 'all'>('all')
  const [selectedRoomScope, setSelectedRoomScope] = useState<string>('all')
  const [isRoomIsolated, setIsRoomIsolated] = useState<boolean>(false)

  // Use active plan from store or user uploaded/selected plan
  const activePlan = useMemo(() => {
    if (masterJson?.floor_plan) {
      const fp = masterJson.floor_plan as any
      if ((fp.rooms && fp.rooms.length > 0) || (fp.floors && fp.floors.some((f: any) => f.rooms?.length > 0))) {
        return masterJson
      }
    }
    return null
  }, [masterJson])

  // Extract all available floors dynamically from activePlan
  const availableFloors: any[] = useMemo(() => {
    if (!activePlan?.floor_plan) return []
    const fp = activePlan.floor_plan as any
    if (Array.isArray(fp.floors) && fp.floors.length > 0) {
      return fp.floors.map((fl: any, idx: number) => ({
        index: typeof fl.floor_index === 'number' ? fl.floor_index : idx,
        id: fl.floor_id || `L${idx}`,
        name: fl.name || (idx === 0 ? 'Ground Floor (Level 0)' : `Floor ${idx + 1}`),
        rooms: (fl.rooms || []).map((r: any, rIdx: number) => ({
          ...r,
          id: r.room_id || r.id || `rm_${idx}_${rIdx}`,
          name: r.name || r.type || `Room ${rIdx + 1}`,
          type: r.type || r.name || 'room',
          floor_index: idx,
          polygon: r.polygon || [],
          area: typeof r.area === 'number' ? r.area : (r.area_sqm || 0),
        })),
        doors: fl.doors || [],
        windows: fl.windows || [],
        structural_elements: fl.structural_elements || [],
      }))
    }
    const flatRooms = fp.rooms || []
    if (flatRooms.length > 0) {
      return [{
        index: 0,
        id: 'L0',
        name: 'Ground Floor (Level 0)',
        rooms: flatRooms.map((r: any, rIdx: number) => ({
          ...r,
          id: r.room_id || r.id || `rm_0_${rIdx}`,
          name: r.name || r.type || `Room ${rIdx + 1}`,
          type: r.type || r.name || 'room',
          floor_index: 0,
          polygon: r.polygon || [],
          area: typeof r.area === 'number' ? r.area : (r.area_sqm || 0),
        })),
        doors: fp.doors || [],
        windows: fp.windows || [],
        structural_elements: fp.structural_elements || [],
      }]
    }
    return []
  }, [activePlan])

  // Extract available rooms for the current floor selection
  const availableRooms: any[] = useMemo(() => {
    if (availableFloors.length === 0) return []
    if (selectedFloorIndex === 'all') {
      return availableFloors.flatMap((f: any) => f.rooms)
    }
    const fl = availableFloors.find((f: any) => f.index === selectedFloorIndex)
    return fl ? fl.rooms : availableFloors.flatMap((fl: any) => fl.rooms)
  }, [availableFloors, selectedFloorIndex])

  // Filtered floor plan to pass to FloorPlan2DViewer
  const displayedFloorPlan = useMemo(() => {
    if (!activePlan?.floor_plan) return undefined
    const fp = activePlan.floor_plan as any
    if (selectedFloorIndex === 'all') {
      return {
        ...fp,
        rooms: availableFloors.flatMap((f: any) => f.rooms),
      }
    }
    const fl = availableFloors.find((f: any) => f.index === selectedFloorIndex)
    if (!fl) return fp
    return {
      ...fp,
      rooms: fl.rooms,
      doors: (fl.doors && fl.doors.length > 0) ? fl.doors : (fp.doors || []),
      windows: (fl.windows && fl.windows.length > 0) ? fl.windows : (fp.windows || []),
      structural_elements: (fl.structural_elements && fl.structural_elements.length > 0) ? fl.structural_elements : (fp.structural_elements || []),
    }
  }, [activePlan, selectedFloorIndex, availableFloors])

  // Active target room highlighted
  const activeHighlightedRoomId = useMemo(() => {
    if (selectedRoomScope !== 'all') {
      return selectedRoomScope
    }
    return highlightedElementId
  }, [selectedRoomScope, highlightedElementId])

  // Dynamically calculate actual outer dimensions from room geometry
  const realOuterDimensions = useMemo(() => {
    const rooms = displayedFloorPlan?.rooms || (activePlan?.floor_plan as any)?.rooms || []
    if (rooms.length === 0) return undefined
    let allPts: [number, number][] = []
    rooms.forEach((r: any) => {
      if (Array.isArray(r.polygon)) {
        r.polygon.forEach((p: any) => {
          if (Array.isArray(p) && p.length >= 2) allPts.push([p[0], p[1]])
          else if (p && typeof p === 'object' && 'x' in p && 'y' in p) allPts.push([p.x, p.y])
        })
      }
    })
    if (allPts.length === 0) return undefined
    const xs = allPts.map(p => p[0])
    const ys = allPts.map(p => p[1])
    const w = Math.max(...xs) - Math.min(...xs)
    const l = Math.max(...ys) - Math.min(...ys)
    const wFt = Math.round(w * 3.28084)
    const lFt = Math.round(l * 3.28084)
    return {
      top: `${w.toFixed(1)}m (${wFt}'-0")`,
      right: `${l.toFixed(1)}m (${lFt}'-0")`,
    }
  }, [displayedFloorPlan, activePlan])

  // Reusable Floor and Room Scope Selector Toolbar
  const renderSpaceSelectorToolbar = (compact = false) => {
    if (availableFloors.length === 0) return null
    return (
      <div className={`flex flex-wrap items-center justify-between gap-2.5 p-2 rounded-xl bg-slate-900/90 border border-slate-700/80 text-xs text-slate-200 mb-3 shadow-md ${compact ? 'py-1 px-2' : ''}`}>
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Floor Dropdown */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400 font-medium text-[11px] flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-blue-400" /> Floor:
            </span>
            <select
              value={selectedFloorIndex === 'all' ? 'all' : String(selectedFloorIndex)}
              onChange={(e) => {
                const val = e.target.value === 'all' ? 'all' : Number(e.target.value)
                setSelectedFloorIndex(val)
                setSelectedRoomScope('all')
                setHighlightedElementId(null)
                setIsRoomIsolated(false)
              }}
              className="bg-slate-800 text-white text-[11px] font-semibold rounded-lg px-2.5 py-1.5 border border-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
            >
              <option value="all">All Floors ({availableFloors.length})</option>
              {availableFloors.map((fl: any) => (
                <option key={fl.id} value={String(fl.index)}>
                  {fl.name} ({fl.rooms.length} spaces)
                </option>
              ))}
            </select>
          </div>

          {/* Room / Space Dropdown */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400 font-medium text-[11px] flex items-center gap-1">
              <Building2 className="w-3.5 h-3.5 text-indigo-400" /> Space:
            </span>
            <select
              value={selectedRoomScope}
              onChange={(e) => {
                const val = e.target.value
                setSelectedRoomScope(val)
                if (val !== 'all') {
                  setHighlightedElementId(val)
                } else {
                  setHighlightedElementId(null)
                  setIsRoomIsolated(false)
                }
              }}
              className="bg-slate-800 text-white text-[11px] font-semibold rounded-lg px-2.5 py-1.5 border border-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 max-w-[210px] truncate cursor-pointer"
            >
              <option value="all">All Spaces / Full Plan ({availableRooms.length})</option>
              {availableRooms.map((rm: any) => (
                <option key={rm.id} value={rm.id}>
                  {rm.name} {rm.area > 0 ? `(${rm.area.toFixed(1)} m²)` : ''}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Isolate / Focus Room Button */}
        {selectedRoomScope !== 'all' && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsRoomIsolated(!isRoomIsolated)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all border flex items-center gap-1 cursor-pointer ${
                isRoomIsolated
                  ? 'bg-indigo-600 text-white border-indigo-500 shadow-sm'
                  : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
              }`}
            >
              <Focus className="w-3 h-3" />
              {isRoomIsolated ? 'Isolated View' : 'Isolate Room'}
            </button>
            <button
              type="button"
              onClick={() => {
                setSelectedRoomScope('all')
                setHighlightedElementId(null)
                setIsRoomIsolated(false)
              }}
              className="text-[11px] text-muted-foreground hover:text-white underline cursor-pointer"
            >
              Clear
            </button>
          </div>
        )}
      </div>
    )
  }


  // Fetch project from API if store was not populated
  useEffect(() => {
    if (projectId && (!masterJson || !(masterJson.floor_plan as any)?.rooms?.length)) {
      projectsApi.getProject(projectId).then((p) => {
        if (p?.master_json) {
          loadProject({
            id: p.id,
            project_name: p.project_name,
            master_json: p.master_json,
          })
        }
      }).catch(console.warn)
    }
  }, [projectId, masterJson, loadProject])

  // Automatically switch tab to 'generated' if activePlan exists from Component 1
  useEffect(() => {
    if (masterJson?.floor_plan && (masterJson.floor_plan as any).rooms?.length > 0) {
      setActiveUploadTab('generated')
    }
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
    if (!masterJson) {
      setUploadError("No floor plan available to rectify. Please select or upload a plan first.")
      return
    }
    setIsProcessing(true)
    setUploadError(null)
    try {
      const result = await vsaiApi.rectify(projectId || undefined, masterJson)
      if (result) {
        setRectifiedData(result)
        setOutput('vsai_rectifier', result)
        if (result.master_json) {
          loadProject({
            id: projectId || result.master_json.project_id || 'proj-vsai',
            project_name: projectName || result.master_json.project_name || 'Rectified Project',
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
    if (!masterJson) return
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
          id: projectId || response.master_json.project_id || 'proj-vsai',
          project_name: projectName || response.master_json.project_name || 'Updated Floor Plan',
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

      // Seamlessly take the user back to Step 2 to inspect their updated Vastu score & results
      setCurrentStep(2)
    } catch (err: any) {
      setUploadError(err?.response?.data?.detail || err?.message || 'Failed to update plan and re-evaluate Vastu')
    } finally {
      setIsSubmittingMissingInfo(false)
    }
  }


  const handleResetPlan = useCallback(() => {
    resetProject()
    setUploadedFileName(null)
    setUploadedFileSize(null)
    setUploadedImageSrc(null)
    setSegmentationMeta(null)
    setValidationResult(null)
    setMissingInfoReport(null)
    setVastuAnalysis(null)
    setRectifiedData(null)
    setUploadError(null)
    setIsReviewDismissed(false)
    setPlanViewMode('cad')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [resetProject])

  const handleFileProcess = async (file: File) => {
    if (!file) return

    // Clear local UI state only. The project itself is kept so the uploaded plan is
    // written into THIS project's centralized Master JSON (not a throwaway demo project).
    setUploadError(null)
    setValidationResult(null)
    setMissingInfoReport(null)
    setIsReviewDismissed(false)
    setVastuAnalysis(null)
    setSegmentationMeta(null)
    setUploadedImageSrc(null)
    setPlanViewMode('cad')
    setIsUploading(true)

    setUploadedFileName(file.name)
    const sizeMb = file.size / (1024 * 1024)
    setUploadedFileSize(sizeMb >= 1 ? `${sizeMb.toFixed(2)} MB` : `${Math.round(file.size / 1024)} KB`)

    try {
      if (file.name.endsWith('.json') || file.type === 'application/json') {
        // Uploading a full Master JSON file creates its own project.
        resetProject()
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
        // Floor plan image (PNG, JPG, etc.) -> Process with CubiCasa5K AI segmentation
        const reader = new FileReader()
        reader.onload = (e) => {
          setUploadedImageSrc(e.target?.result as string)
        }
        reader.readAsDataURL(file)

        if (!projectId) {
          throw new Error('No active project. Please create or open a project before uploading a floor plan.')
        }
        // Project-scoped segmentation: result is persisted into this project's Master JSON
        const segResponse = await vsaiApi.segmentFloorPlan(file, undefined, projectId)
        if (segResponse.master_json) {
          loadProject({
            id: projectId,
            project_name: projectName || segResponse.master_json.project_name || file.name.replace(/\.[^/.]+$/, ""),
            master_json: segResponse.master_json,
          })
          setSegmentationMeta(segResponse.segmentation || segResponse.master_json.segmentation_meta || null)
          if (segResponse.validation) {
            setValidationResult(segResponse.validation)
            setMissingInfoReport(segResponse.validation.missing_info_report || null)
          }
          if (segResponse.vastu_analysis) {
            setVastuAnalysis(segResponse.vastu_analysis)
          }
        }
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
        setUploadError(detail || err?.message || 'Failed to upload and segment plan image')
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

  const handleUseExistingPlan = () => {
    if (masterJson) {
      setUploadedFileName(`${projectName || 'Project'}-master-plan.json`)
      setUploadedFileSize('Centralized Master JSON')
      setVastuAnalysis(null)
      setValidationResult(null)
      setUploadError(null)
    }
  }

  const handleAnalyzeWithVastu = async () => {
    if (!masterJson) {
      setUploadError('No floor plan found to analyze. Please generate a plan in Component 1 or upload a floor plan.')
      return
    }
    setIsEvaluatingVastu(true)
    await evaluateVastu(masterJson)
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
    setUploadError(null)
    const activeProjId = projectId || (masterJson as any)?.project_id
    if (!activePlan && (!masterJson?.floor_plan || !(masterJson.floor_plan as any).rooms?.length)) {
      setUploadError(
        'No floor plan found for this project. Component 1 (GAB-Gen) was skipped and no floor plan image was uploaded in Component 2. Please run Component 1 first, or upload a floor plan image here.'
      )
      return
    }

    try {
      if (activeProjId) {
        await skipComponent('vsai_rectifier')
      } else {
        setComponentStatus('vsai_rectifier', 'skipped')
      }
      router.push('/features/esai-engine')
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setUploadError(
        typeof detail === 'string'
          ? detail
          : 'Failed to skip Component 2. Please ensure a valid floor plan exists.'
      )
    }
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

  // --- DYNAMIC ANALYSIS RESULTS PIN MARKERS FROM VASTU DEFECTS & ROOMS ---
  const analysisMarkers: PlanMarker[] = useMemo(() => {
    if (!vastuAnalysis?.defects || vastuAnalysis.defects.length === 0) {
      return []
    }
    const rooms = (activePlan?.floor_plan as any)?.rooms || []
    return vastuAnalysis.defects.slice(0, 5).map((d, idx) => {
      // Find matching room by ID or name
      const matchedRoom = rooms.find((r: any) => 
        (d.room_id && r.id === d.room_id) ||
        (d.room_name && (r.name?.toLowerCase().includes(d.room_name.toLowerCase()) || r.type?.toLowerCase().includes(d.room_name.toLowerCase())))
      )
      return {
        id: `m-${idx + 1}`,
        label: `${idx + 1 < 10 ? '0' : ''}${idx + 1}`,
        roomId: matchedRoom?.id || d.room_id,
        type: d.severity === 'CRITICAL' ? 'correction' : 'attention',
        tooltip: `${d.room_name || 'Room'}: ${d.description || 'Vastu issue detected'}`
      }
    })
  }, [vastuAnalysis, activePlan])

  // --- VASTU ELEMENT STATUS ROW ITEMS (DYNAMICALLY EXTRACTED FROM ACTIVE ROOMS & DEFECTS) ---
  const elementStatuses = useMemo(() => {
    const defects = vastuAnalysis?.defects || []
    const goodAspects = vastuAnalysis?.good_aspects || []
    const rooms = (activePlan?.floor_plan as any)?.rooms || []

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

    // Discover rooms present in current active floor plan
    const findRoomId = (keyword: string) => {
      const rm = rooms.find((r: any) => 
        r.name?.toLowerCase().includes(keyword) || 
        r.type?.toLowerCase().includes(keyword)
      )
      return rm ? (rm.id || rm.room_id) : undefined
    }

    const mainDoorDefect = hasDefect('entrance') || hasDefect('door')
    const mainDoorStatus = mainDoorDefect ? 'Attention' : 'Good'
    const mainDoorDetails = vastuAnalysis?.dwara_sthana?.house_type 
      ? `${vastuAnalysis.dwara_sthana.house_type}` 
      : 'Aligned with Entrance'

    const kitchenDefect = hasDefect('kitchen')
    const kitchenStatus = kitchenDefect ? 'Correction' : (hasGood('kitchen') ? 'Good' : 'Good')
    const kitchenDetails = kitchenDefect?.sector_display?.split('(')[0] || (hasGood('kitchen') ? 'Well Positioned' : 'Auspicious Zone')

    const bedDefect = hasDefect('bedroom') || hasDefect('bed')
    const bedStatus = bedDefect ? 'Correction' : 'Good'
    const bedDetails = bedDefect ? (bedDefect.description?.slice(0, 22) + '...' || '1 Issue Found') : 'Well Positioned'

    const bathDefect = hasDefect('drain') || hasDefect('toilet') || hasDefect('bath')
    const bathStatus = bathDefect ? 'Attention' : 'Good'
    const bathDetails = bathDefect ? 'Check Placement' : 'Well Positioned'

    const poojaDefect = hasDefect('pooja') && !hasGood('pooja')
    const poojaStatus = poojaDefect ? 'Correction' : 'Good'
    const poojaDetails = poojaDefect ? 'Avoid Conflict Sector' : 'Well Positioned'

    return [
      { element: 'Main Door', status: mainDoorStatus, details: mainDoorDetails, roomId: findRoomId('living') || 'door-main' },
      { element: 'Windows', status: 'Good', details: 'Well Positioned', roomId: findRoomId('living') },
      { element: 'Bedroom', status: bedStatus, details: bedDetails, roomId: findRoomId('bed') },
      { element: 'Kitchen', status: kitchenStatus, details: kitchenDetails, roomId: findRoomId('kitchen') },
      { element: 'Bathroom', status: bathStatus, details: bathDetails, roomId: findRoomId('toilet') || findRoomId('bath') },
      { element: 'Pooja Room', status: poojaStatus, details: poojaDetails, roomId: findRoomId('pooja') },
      { element: 'Staircase', status: hasDefect('stair') ? 'Attention' : 'Good', details: hasDefect('stair') ? 'Check Placement' : 'Auspicious Zone', roomId: findRoomId('stair') || findRoomId('living') },
    ]
  }, [vastuAnalysis, activePlan])

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
            <div className="text-[11px] font-bold uppercase tracking-widest text-blue-500 flex items-center gap-1.5 mb-1.5">
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
                          ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30 ring-2 ring-blue-500/40'
                          : isCompleted
                          ? 'bg-blue-600 text-white shadow-md'
                          : 'bg-muted/40 text-muted-foreground border border-border/60'
                      }`}
                    >
                      {isCompleted ? <Check className="w-3.5 h-3.5" /> : s.id}
                    </div>
                    <span
                      className={`text-[11px] font-medium tracking-tight pb-0.5 whitespace-nowrap ${
                        isActive
                          ? 'text-foreground font-bold border-b-2 border-blue-500'
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
                  <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-500 shrink-0 shadow-inner">
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
                        ? 'text-blue-500 border-b-2 border-blue-500'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Upload Floor Plan
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveUploadTab('generated')
                      handleUseExistingPlan()
                    }}
                    className={`pb-2.5 font-semibold transition-all relative ${
                      activeUploadTab === 'generated'
                        ? 'text-blue-500 border-b-2 border-blue-500'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Use Existing Plan
                  </button>
                </div>

                {activeUploadTab === 'upload' ? (
                  <div
                    className={`p-8 border-2 border-dashed rounded-2xl text-center flex flex-col items-center justify-center transition-all bg-card/30 ${
                      isDragging 
                        ? 'border-blue-500 ring-4 ring-blue-500/20 bg-blue-500/5 scale-[1.01]' 
                        : 'border-border/70 hover:border-blue-500/50'
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
                      className="bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs px-6 py-2.5 rounded-lg shadow-md shadow-blue-500/20 transition-all mb-5 cursor-pointer"
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
                  <div className="space-y-4">
                    {activePlan ? (
                      <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/30 space-y-3">
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
                              <Sparkles className="w-5 h-5" />
                            </div>
                            <div>
                              <div className="text-sm font-bold text-foreground">
                                {projectName || activePlan.project_name || 'Project Blueprint'}
                              </div>
                              <div className="text-xs text-muted-foreground font-mono">
                                Component 01 (GAB-Gen) Centralized Master JSON
                              </div>
                            </div>
                          </div>
                          <Badge variant="outline" className="text-[10px] font-mono bg-blue-500/20 text-blue-400 border-blue-500/40">
                            Active Project Plan
                          </Badge>
                        </div>

                        <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-blue-500/20">
                          <div className="p-2 rounded-lg bg-card/60">
                            <span className="text-[10px] text-muted-foreground block">Rooms</span>
                            <span className="font-bold text-foreground">{(activePlan.floor_plan as any)?.rooms?.length || 0} Rooms</span>
                          </div>
                          <div className="p-2 rounded-lg bg-card/60">
                            <span className="text-[10px] text-muted-foreground block">Orientation</span>
                            <span className="font-bold text-foreground">{activePlan.land_info?.orientation || 'North'}</span>
                          </div>
                        </div>

                        <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 pt-1">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>Vectorized CAD geometry loaded from Component 1 and ready for Vastu analysis.</span>
                        </div>
                      </div>
                    ) : (
                      <div className="p-6 border border-border/70 rounded-xl bg-card/30 text-center space-y-3">
                        <div className="w-12 h-12 rounded-full bg-muted/40 border border-border/80 flex items-center justify-center text-muted-foreground mx-auto">
                          <Layers className="w-6 h-6" />
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-foreground">No Existing Plan in Current Project</div>
                          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                            Go to Component 1 (GAB-Gen) to generate a vectorized blueprint for this project, or upload an existing floor plan image on the left.
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => router.push('/features/gab-gen')}
                          className="text-xs mt-2"
                        >
                          Go to Component 1 (GAB-Gen)
                        </Button>
                      </div>
                    )}
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

            {/* RIGHT COLUMN: EMPTY STATE OR PLAN PREVIEW CARD */}
            {activePlan ? (
              <Card className="bg-card/40 border-border/70 rounded-2xl p-6 md:p-8 flex flex-col justify-between backdrop-blur shadow-xl">
                <div>
                  <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0 shadow-inner">
                        <CheckCircle2 className="w-5 h-5" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                          Plan Uploaded Successfully!
                          {segmentationMeta && (
                            <Badge variant="outline" className="text-[10px] bg-blue-500/10 border-blue-500/40 text-blue-400 px-2 py-0">
                              AI Detected ({segmentationMeta.rooms_detected} rooms)
                            </Badge>
                          )}
                        </h4>
                        <p className="text-xs text-muted-foreground font-mono mt-0.5">
                          {uploadedFileName || 'Custom Floor Plan'} {uploadedFileSize ? `• ${uploadedFileSize}` : ''}
                          {segmentationMeta?.average_confidence && (
                            <span className="ml-2 text-emerald-400 font-sans font-medium">
                              • Confidence {Math.round(segmentationMeta.average_confidence * 100)}%
                            </span>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">

                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          handleResetPlan()
                          openFilePicker()
                        }}
                        className="text-xs h-8 gap-1.5 border-border/80 text-muted-foreground hover:text-foreground hover:border-blue-500/50"
                        title="Upload another plan"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        Replace
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleResetPlan}
                        className="text-xs h-8 gap-1.5 border-red-500/30 text-red-400 hover:text-red-300 hover:bg-red-500/10 hover:border-red-500/50"
                        title="Clear plan and return to empty upload state"
                      >
                        <X className="w-3.5 h-3.5" />
                        Reset
                      </Button>
                    </div>
                  </div>


                  {/* View Mode Switcher if uploaded image exists */}
                  {uploadedImageSrc && (
                    <div className="flex items-center justify-between mb-2 px-1">
                      <span className="text-[11px] text-muted-foreground font-medium">Preview View:</span>
                      <div className="inline-flex rounded-lg bg-card/80 p-0.5 border border-border/60 text-xs">
                        <button
                          type="button"
                          onClick={() => setPlanViewMode('cad')}
                          className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                            planViewMode === 'cad'
                              ? 'bg-blue-600 text-white shadow-sm'
                              : 'text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          CAD Vector
                        </button>
                        <button
                          type="button"
                          onClick={() => setPlanViewMode('image')}
                          className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                            planViewMode === 'image'
                              ? 'bg-blue-600 text-white shadow-sm'
                              : 'text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          Original Image
                        </button>
                        <button
                          type="button"
                          onClick={() => setPlanViewMode('overlay')}
                          className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                            planViewMode === 'overlay'
                              ? 'bg-blue-600 text-white shadow-sm'
                              : 'text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          Overlay
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Floor and Room Scope Selector Toolbar */}
                  {renderSpaceSelectorToolbar()}

                  <div className="relative w-full h-[460px] sm:h-[480px] rounded-xl overflow-hidden border border-slate-300 bg-white mb-6 shadow-md flex flex-col">
                    {planViewMode === 'image' && uploadedImageSrc ? (
                      <div className="w-full h-full flex items-center justify-center bg-slate-50 p-4">
                        <img
                          src={uploadedImageSrc}
                          alt="Original floor plan"
                          className="max-h-full max-w-full object-contain rounded"
                        />
                      </div>
                    ) : planViewMode === 'overlay' && uploadedImageSrc ? (
                      <div className="relative w-full h-full">
                        <img
                          src={uploadedImageSrc}
                          alt="Original floor plan background"
                          className="absolute inset-0 w-full h-full object-contain opacity-35 filter grayscale"
                        />
                        <div className="relative z-10 w-full h-full">
                          <FloorPlan2DViewer
                            key={`overlay-${activePlan.project_id || uploadedFileName || 'active-plan'}-${selectedFloorIndex}-${selectedRoomScope}`}
                            floorPlan={displayedFloorPlan as any}
                            landInfo={activePlan.land_info as any}
                            cadStyle={true}
                            outerDimensions={realOuterDimensions}
                            hideLegend={true}
                            hideTopBar={true}
                            compassPosition="top-right"
                            highlightRoomId={activeHighlightedRoomId}
                            isolateRoom={isRoomIsolated}
                            dimOthers={Boolean(activeHighlightedRoomId)}
                          />
                        </div>
                      </div>
                    ) : (
                      <FloorPlan2DViewer
                        key={`cad-${activePlan.project_id || uploadedFileName || 'active-plan'}-${selectedFloorIndex}-${selectedRoomScope}`}
                        floorPlan={displayedFloorPlan as any}
                        landInfo={activePlan.land_info as any}
                        cadStyle={true}
                        outerDimensions={realOuterDimensions}
                        hideLegend={true}
                        hideTopBar={true}
                        compassPosition="top-right"
                        highlightRoomId={activeHighlightedRoomId}
                        isolateRoom={isRoomIsolated}
                        dimOthers={Boolean(activeHighlightedRoomId)}
                      />
                    )}
                  </div>
                </div>

                <div className="space-y-2 pt-2">
                  <Button
                    type="button"
                    onClick={handleAnalyzeWithVastu}
                    disabled={isEvaluatingVastu}
                    className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-sm py-4 h-auto rounded-xl shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2 cursor-pointer"
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
                    <Sparkles className="w-3 h-3 text-blue-500" />
                    Our AI will analyze your plan and check it against Vastu principles.
                  </p>
                </div>
              </Card>
            ) : (
              <Card className="bg-card/30 border-dashed border-2 border-border/60 rounded-2xl p-8 flex flex-col items-center justify-center text-center min-h-[560px] relative overflow-hidden backdrop-blur">
                {isUploading ? (
                  <div className="flex flex-col items-center justify-center p-6 text-center">
                    <div className="w-16 h-16 rounded-full bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-blue-500 mb-4 animate-pulse">
                      <Sparkles className="w-8 h-8 animate-spin" />
                    </div>
                    <h4 className="text-base font-bold text-foreground">Detecting rooms with CubiCasa AI...</h4>
                    <p className="text-xs text-muted-foreground mt-2 max-w-sm">
                      Extracting room boundaries, walls, doors, and dimensional vectors from your floor plan image.
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center max-w-sm">
                    <div className="w-16 h-16 rounded-2xl bg-muted/30 border border-border/80 flex items-center justify-center text-muted-foreground mb-4 shadow-inner">
                      <Layers className="w-8 h-8 text-muted-foreground/70" />
                    </div>
                    <h4 className="text-base font-bold text-foreground mb-1.5">
                      No Plan Uploaded Yet
                    </h4>
                    <p className="text-xs text-muted-foreground leading-relaxed mb-6">
                      Upload your architectural floor plan image (PNG, JPG) or Master JSON on the left to preview the CAD blueprint and run Vastu Shastra analysis.
                    </p>
                    <Button
                      type="button"
                      onClick={openFilePicker}
                      className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-5 py-2.5 rounded-lg shadow-md shadow-blue-500/20 cursor-pointer transition-all"
                    >
                      <Upload className="w-4 h-4 mr-2" />
                      Upload Plan Image
                    </Button>
                  </div>
                )}
              </Card>
            )}
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
                        <div className="w-7 h-7 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500 font-mono font-bold text-xs shadow-inner">
                          #
                        </div>
                        <h3 className="text-sm font-bold text-foreground">Analyzed Floor Plan</h3>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setIsFullscreenPlan(true)}
                        className="text-xs h-7 gap-1 border-border/60 text-muted-foreground hover:text-foreground hover:border-blue-500/40"
                      >
                        <Maximize2 className="w-3.5 h-3.5" />
                        View in Fullscreen
                      </Button>
                    </div>

                    {/* Floor and Room Scope Selector Toolbar */}
                    {renderSpaceSelectorToolbar()}

                    {/* CAD Canvas with Issue Markers */}
                    <div className="w-full h-[460px] sm:h-[480px] rounded-xl overflow-hidden border border-slate-300 bg-white mb-4 shadow-md flex flex-col">
                      <FloorPlan2DViewer
                        key={`analyzed-${activePlan?.project_id || 'active'}-${selectedFloorIndex}-${selectedRoomScope}`}
                        floorPlan={displayedFloorPlan as any}
                        landInfo={activePlan?.land_info as any}
                        cadStyle={true}
                        hideLegend={true}
                        hideTopBar={true}
                        compassPosition="top-left"
                        markers={analysisMarkers}
                        highlightRoomId={activeHighlightedRoomId}
                        isolateRoom={isRoomIsolated}
                        dimOthers={Boolean(activeHighlightedRoomId)}
                        onMarkerClick={(m) => {
                          if (m.roomId) {
                            setHighlightedElementId(m.roomId)
                            setSelectedRoomScope(m.roomId)
                          }
                        }}
                      />
                    </div>


                    {/* Bottom Status Legend */}
                    <div className="p-3 rounded-xl bg-card border border-border flex items-center justify-around text-xs select-none">
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
                      <div className="text-4xl md:text-5xl font-extrabold text-blue-500 tracking-tight mt-2 font-mono">
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
                size="lg"
                onClick={() => setCurrentStep(3)}
                className="flex-1 h-12 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2 cursor-pointer"
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
                  size="sm"
                  onClick={handleProcess}
                  disabled={isProcessing}
                  className="text-xs h-8 gap-1.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold cursor-pointer shadow-sm shadow-blue-500/20"
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
                      <Eye className="w-3 h-3 text-blue-400" /> Click to inspect on 2D map
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
                  <Sparkles className="w-5 h-5 text-blue-500" />
                  Corrected Plan & Export Studio
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Side-by-side architectural CAD comparison of original blueprint and AI-rectified floor plan.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  size="sm"
                  onClick={() => router.push('/features/esai-engine')}
                  className="text-xs h-8 gap-1.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold cursor-pointer shadow-sm shadow-blue-500/20"
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
              <div className="flex-1 p-6 overflow-hidden bg-slate-900 flex flex-col">
                <div className="w-full mb-3 shrink-0">
                  {renderSpaceSelectorToolbar(true)}
                </div>
                <div className="flex-1 w-full rounded-xl overflow-hidden bg-white shadow-inner flex items-center justify-center">
                  <FloorPlan2DViewer
                    key={`fullscreen-${activePlan?.project_id || 'active'}-${selectedFloorIndex}-${selectedRoomScope}`}
                    floorPlan={displayedFloorPlan as any}
                    landInfo={activePlan?.land_info as any}
                    cadStyle={true}
                    outerDimensions={realOuterDimensions}
                    markers={analysisMarkers}
                    highlightRoomId={activeHighlightedRoomId}
                    isolateRoom={isRoomIsolated}
                    dimOthers={Boolean(activeHighlightedRoomId)}
                    onMarkerClick={(m) => {
                      if (m.roomId) {
                        setHighlightedElementId(m.roomId)
                        setSelectedRoomScope(m.roomId)
                      }
                    }}
                  />
                </div>
              </div>

            </div>
          </div>
        )}
      </div>
    </FeatureWorkflowShell>
  )
}
