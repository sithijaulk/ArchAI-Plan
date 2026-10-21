"use client"
import React, { useMemo, useState } from 'react'
import { FloorPlan2DViewer } from './FloorPlan2DViewer'
import { FloorPlanDiffViewer, RoomModification } from './FloorPlanDiffViewer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  Sparkles, 
  ArrowRight, 
  CheckCircle2, 
  TrendingUp, 
  ShieldCheck, 
  Layers, 
  Download,
  SplitSquareVertical,
  Check,
  ImageIcon,
  Loader2
} from 'lucide-react'

interface RectificationComparisonStudioProps {
  baselineFloorPlan?: any;
  rectifiedFloorPlan?: any;
  landInfo?: any;
  baselineScore?: number;
  rectifiedScore?: number;
  modifications?: RoomModification[];
  isComputing?: boolean;
  onBackToInspection: () => void;
  onContinueToNextStage: () => void;
}

export function RectificationComparisonStudio({
  baselineFloorPlan,
  rectifiedFloorPlan,
  landInfo,
  baselineScore = 0,
  rectifiedScore = 0,
  modifications = [],
  isComputing = false,
  onBackToInspection,
  onContinueToNextStage,
}: RectificationComparisonStudioProps) {
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)
  const [activeViewMode, setActiveViewMode] = useState<'cad' | 'diff'>('cad')
  const [cadPlanSelection, setCadPlanSelection] = useState<'rectified' | 'baseline'>('rectified')
  const [isExportingJpg, setIsExportingJpg] = useState(false)

  const activeModifications = modifications || []
  const scoreDelta = Math.max(0, rectifiedScore - baselineScore)
  const effectiveRectifiedPlan = rectifiedFloorPlan || baselineFloorPlan

  const modifiedRoomIds = useMemo(() => {
    return activeModifications.map(m => m.roomId)
  }, [activeModifications])

  const planDimensions = useMemo(() => {
    const plan = effectiveRectifiedPlan || baselineFloorPlan
    const w = plan?.dimensions?.width || 42
    const h = plan?.dimensions?.height || 36
    return { top: `${Math.round(w)}'-0"`, right: `${Math.round(h)}'-0"` }
  }, [effectiveRectifiedPlan, baselineFloorPlan])

  const handleDownloadCadJson = () => {
    const dataToDownload = {
      project_type: "ArchAI-Rectified-Floor-Plan",
      rectified_score: rectifiedScore,
      baseline_score: baselineScore,
      land_info: landInfo,
      floor_plan: effectiveRectifiedPlan,
      modifications: activeModifications,
      timestamp: new Date().toISOString(),
    }
    const blob = new Blob([JSON.stringify(dataToDownload, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `rectified_architectural_cad_plan_${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleDownloadJpg = () => {
    setIsExportingJpg(true)
    try {
      // Look for active architectural plan SVG
      const svgElement = (
        document.getElementById('architectural-plan-svg') ||
        document.getElementById('architectural-diff-svg') ||
        document.querySelector('.min-h-\\[480px\\] svg') ||
        document.querySelector('svg')
      ) as SVGSVGElement | null

      if (!svgElement) {
        console.error('No architectural plan SVG found to export')
        setIsExportingJpg(false)
        return
      }

      // Clone SVG to isolate export from active DOM
      const clonedSvg = svgElement.cloneNode(true) as SVGSVGElement
      clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')

      // Inject clean font styling
      const styleElem = document.createElementNS('http://www.w3.org/2000/svg', 'style')
      styleElem.textContent = `
        text { font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
      `
      clonedSvg.insertBefore(styleElem, clonedSvg.firstChild)

      // Calculate high-resolution export dimensions (2800px width for CAD print fidelity)
      const viewBoxAttr = clonedSvg.getAttribute('viewBox') || ''
      let aspect = 0.75
      if (viewBoxAttr) {
        const parts = viewBoxAttr.split(/[\s,]+/).map(Number)
        if (parts.length >= 4 && parts[2] > 0 && parts[3] > 0) {
          aspect = parts[3] / parts[2]
        }
      } else {
        const bbox = svgElement.getBoundingClientRect()
        if (bbox.width > 0 && bbox.height > 0) {
          aspect = bbox.height / bbox.width
        }
      }

      const exportWidth = 2800
      const exportHeight = Math.max(1400, Math.round(exportWidth * aspect))
      clonedSvg.setAttribute('width', String(exportWidth))
      clonedSvg.setAttribute('height', String(exportHeight))

      // Serialize SVG
      const serializer = new XMLSerializer()
      const svgString = serializer.serializeToString(clonedSvg)
      const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
      const URLObj = window.URL || window.webkitURL || window
      const svgUrl = URLObj.createObjectURL(svgBlob)

      const img = new Image()
      img.onload = () => {
        try {
          const canvas = document.createElement('canvas')
          canvas.width = exportWidth
          canvas.height = exportHeight
          const ctx = canvas.getContext('2d')
          if (!ctx) {
            URLObj.revokeObjectURL(svgUrl)
            setIsExportingJpg(false)
            return
          }

          // 1. Paint pure white architectural drafting paper background
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(0, 0, exportWidth, exportHeight)

          // 2. Draw SVG image onto canvas
          ctx.drawImage(img, 0, 0, exportWidth, exportHeight)

          // 3. Trigger direct download as high-quality JPG via Data URL
          // Using Data URL ensures Chrome does not fall back to UUID blob identifiers
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
          const filename = cadPlanSelection === 'baseline'
            ? `ArchAI_Baseline_Plan_${timestamp}.jpg`
            : activeViewMode === 'diff'
            ? `ArchAI_Spatial_Diff_Plan_${timestamp}.jpg`
            : `ArchAI_Rectified_Plan_${timestamp}.jpg`

          const dataUrl = canvas.toDataURL('image/jpeg', 0.95)
          const link = document.createElement('a')
          link.href = dataUrl
          link.download = filename
          link.setAttribute('download', filename)
          link.style.display = 'none'
          document.body.appendChild(link)
          link.click()

          setTimeout(() => {
            if (link.parentNode) {
              document.body.removeChild(link)
            }
            URLObj.revokeObjectURL(svgUrl)
            setIsExportingJpg(false)
          }, 400)
        } catch (err) {
          console.error('Canvas export error:', err)
          URLObj.revokeObjectURL(svgUrl)
          setIsExportingJpg(false)
        }
      }

      img.onerror = (err) => {
        console.error('Image load error for SVG JPG export:', err)
        URLObj.revokeObjectURL(svgUrl)
        setIsExportingJpg(false)
      }

      img.src = svgUrl
    } catch (err) {
      console.error('handleDownloadJpg error:', err)
      setIsExportingJpg(false)
    }
  }

  return (
    <div className="w-full space-y-6">
      
      {/* Studio Header Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 rounded-2xl bg-gradient-to-r from-card/80 via-emerald-950/20 to-card/80 border border-emerald-500/30 backdrop-blur shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shadow-inner">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-foreground">
                AI Spatial Rectification Studio
              </h2>
              <Badge className="bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold">
                STAGE 2 COMPLETED
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Review authentic architectural CAD floor plan with doors, windows, dimensions, and Vastu-rectified zones.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={handleDownloadJpg}
            disabled={isExportingJpg}
            className="h-9 px-3.5 gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold cursor-pointer shadow-sm shadow-blue-500/20"
          >
            {isExportingJpg ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <ImageIcon className="w-3.5 h-3.5" />
            )}
            Download Plan (JPG)
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleDownloadCadJson}
            className="h-9 px-3 gap-1.5 border-border/80 text-xs font-semibold hover:bg-muted/50 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-primary" />
            Download CAD (JSON)
          </Button>
        </div>
      </div>

      {/* Main Studio Grid: Left Controls (5 cols) + Right Blueprint Studio (7 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Side: Score Delta & Modifications List */}
        <div className="lg:col-span-5 space-y-4">
          
          {/* Vastu Score Delta Card */}
          <div className="p-4 rounded-2xl bg-card/80 border border-border/80 shadow-md backdrop-blur space-y-3.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-emerald-400" /> Vastu Compliance Delta
              </span>
              <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/40 font-mono font-bold text-xs">
                +{scoreDelta}% GAIN
              </Badge>
            </div>

            {/* Before vs After Score Comparison Bar */}
            <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-slate-900/60 border border-border/40">
              <div className="space-y-0.5">
                <span className="text-[10px] font-semibold text-rose-400 uppercase tracking-wider">
                  Baseline (Before)
                </span>
                <div className="text-2xl font-extrabold text-foreground font-mono">
                  {baselineScore}%
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {baselineScore >= 80 ? 'Grade A' : baselineScore >= 65 ? 'Grade B' : baselineScore >= 50 ? 'Grade C' : 'Grade D'} • Evaluated
                </div>
              </div>

              <div className="space-y-0.5 pl-3 border-l border-border/40">
                <span className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                  Rectified (After) <CheckCircle2 className="w-3 h-3" />
                </span>
                <div className="text-2xl font-extrabold text-emerald-400 font-mono">
                  {rectifiedScore}%
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {rectifiedScore >= 90 ? 'Grade A+' : rectifiedScore >= 80 ? 'Grade A' : 'Grade B'} • Harmonious
                </div>
              </div>
            </div>

            {/* Progress visual bar */}
            <div className="space-y-1">
              <div className="h-2 w-full bg-slate-900 rounded-full overflow-hidden flex border border-border/40">
                <div style={{ width: `${baselineScore}%` }} className="h-full bg-rose-500/70" />
                <div style={{ width: `${scoreDelta}%` }} className="h-full bg-emerald-500 animate-pulse" />
              </div>
              <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                <span>0%</span>
                <span className="text-emerald-400 font-bold">Goal: 90%+ Vastu Harmonious</span>
                <span>100%</span>
              </div>
            </div>
          </div>

          {/* Applied AI Rectifications List */}
          <div className="p-4 rounded-2xl bg-card/80 border border-border/80 shadow-md backdrop-blur space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-primary" /> Applied Modifications ({activeModifications.length})
              </span>
              <span className="text-[10px] text-muted-foreground">Click item to isolate</span>
            </div>

            {activeModifications.length === 0 ? (
              <div className="p-5 rounded-xl bg-slate-900/40 border border-border/40 text-center space-y-2">
                <CheckCircle2 className="w-6 h-6 text-emerald-400 mx-auto" />
                <div className="text-xs font-semibold text-foreground">
                  Optimal Spatial Alignment
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  No structural room shifts required. The floor plan sectors are aligned with Vastu constraints.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {activeModifications.map((mod) => {
                  const isSelected = selectedRoomId === mod.roomId
                  return (
                    <div
                      key={mod.roomId}
                      onClick={() => setSelectedRoomId(isSelected ? null : mod.roomId)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer flex flex-col gap-1.5 shadow-sm ${
                        isSelected
                          ? 'bg-emerald-500/15 border-emerald-500 ring-2 ring-emerald-500/20'
                          : 'bg-slate-900/40 hover:bg-muted/30 border-border/60 hover:border-emerald-500/40'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                          <span className="text-xs font-bold text-foreground truncate">
                            {mod.roomName}
                          </span>
                        </div>
                        <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[10px] font-mono shrink-0">
                          +{mod.pointsGained} pts
                        </Badge>
                      </div>

                      {/* Sector Transformation Pill */}
                      <div className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground bg-slate-950/40 px-2 py-1 rounded-lg border border-border/30">
                        <span className="text-rose-400/90 truncate">{mod.previousSector}</span>
                        <ArrowRight className="w-3 h-3 text-emerald-400 shrink-0" />
                        <span className="text-emerald-300 font-semibold truncate">{mod.newSector}</span>
                      </div>

                      <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                        {mod.reason}
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Side: Dual-Mode Architectural Blueprint Canvas */}
        <div className="lg:col-span-7 flex flex-col space-y-3">
          
          {/* View Mode & Comparison Toggle Bar (Clean Architectural Style) */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 p-2 rounded-xl bg-white border border-slate-200 shadow-xs text-xs">
            {/* Left: Mode Selection (CAD vs Diff) */}
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200">
              <button
                type="button"
                onClick={() => setActiveViewMode('cad')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold text-xs transition-all cursor-pointer ${
                  activeViewMode === 'cad'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Architectural CAD Blueprint</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveViewMode('diff')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold text-xs transition-all cursor-pointer ${
                  activeViewMode === 'diff'
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <SplitSquareVertical className="w-3.5 h-3.5" />
                <span>Spatial Diff Overlay</span>
              </button>
            </div>

            {/* Right: Sub-selection for CAD View (Rectified vs Baseline) + Export JPG */}
            <div className="flex items-center gap-2">
              {activeViewMode === 'cad' && (
                <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200">
                  <button
                    type="button"
                    onClick={() => setCadPlanSelection('rectified')}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                      cadPlanSelection === 'rectified'
                        ? 'bg-emerald-600 text-white font-bold shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <Check className="w-3 h-3" />
                    <span>Rectified ({rectifiedScore}%)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setCadPlanSelection('baseline')}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                      cadPlanSelection === 'baseline'
                        ? 'bg-rose-600 text-white font-bold shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <span>Baseline ({baselineScore}%)</span>
                  </button>
                </div>
              )}

              <button
                type="button"
                onClick={handleDownloadJpg}
                disabled={isExportingJpg}
                title="Download Architectural Plan as High-Res JPG"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs transition-colors cursor-pointer shadow-xs disabled:opacity-50"
              >
                {isExportingJpg ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <ImageIcon className="w-3.5 h-3.5" />
                )}
                <span>Export JPG</span>
              </button>
            </div>
          </div>

          {/* Active Canvas Rendering (Pure White Drawing Sheet) */}
          <div className="w-full min-h-[480px] rounded-2xl overflow-hidden border border-slate-300 bg-white shadow-lg flex flex-col">
            {activeViewMode === 'cad' ? (
              <div className="w-full flex-1">
                <FloorPlan2DViewer
                  floorPlan={cadPlanSelection === 'rectified' ? effectiveRectifiedPlan : baselineFloorPlan}
                  landInfo={landInfo}
                  cadStyle={true}
                  outerDimensions={planDimensions}
                  rectifiedRoomIds={cadPlanSelection === 'rectified' ? modifiedRoomIds : []}
                  highlightRoomId={selectedRoomId}
                  hideLegend={true}
                  onMarkerClick={(m) => {
                    if (m.roomId) setSelectedRoomId(selectedRoomId === m.roomId ? null : m.roomId)
                  }}
                />
              </div>
            ) : (
              <FloorPlanDiffViewer
                baselineFloorPlan={baselineFloorPlan}
                rectifiedFloorPlan={effectiveRectifiedPlan}
                landInfo={landInfo}
                modifications={activeModifications}
                selectedRoomId={selectedRoomId}
                baselineScore={baselineScore}
                rectifiedScore={rectifiedScore}
                onSelectRoom={(rId) => setSelectedRoomId(selectedRoomId === rId ? null : rId)}
              />
            )}
          </div>

        </div>

      </div>
    </div>
  )
}
