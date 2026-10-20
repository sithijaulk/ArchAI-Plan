"use client"
import React, { useState } from 'react'
import { FloorPlanDiffViewer, RoomModification } from './FloorPlanDiffViewer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  Sparkles, 
  ArrowRight, 
  CheckCircle2, 
  TrendingUp, 
  ShieldCheck, 
  RotateCcw,
  Compass,
  Layers,
  ArrowUpRight,
  Eye
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
  const activeModifications = modifications || []
  const scoreDelta = Math.max(0, rectifiedScore - baselineScore)
  const effectiveRectifiedPlan = rectifiedFloorPlan || baselineFloorPlan

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
              Review AI-rectified room geometry with real-time pulsating difference highlights.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={onBackToInspection}
            className="text-xs h-9 gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Back to Inspection
          </Button>
          <Button
            size="sm"
            onClick={onContinueToNextStage}
            className="electric-glow text-xs h-9 gap-1.5 px-4 font-semibold"
          >
            Continue to ESAI Engine <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Main Studio Grid: Left Controls (1 col) + Right Diff Blueprint (2 cols) */}
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

        {/* Right Side: FloorPlanDiffViewer */}
        <div className="lg:col-span-7">
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
        </div>

      </div>
    </div>
  )
}
