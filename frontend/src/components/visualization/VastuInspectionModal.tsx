"use client"
import React, { useEffect } from 'react'
import { FloorPlan2DViewer } from './FloorPlan2DViewer'
import { VastuGoodAspect, VastuDefect } from '@/types/project'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  X, 
  CheckCircle2, 
  AlertTriangle, 
  Compass, 
  Sparkles, 
  Lightbulb, 
  Home, 
  ShieldCheck, 
  Layers
} from 'lucide-react'

interface VastuInspectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  item: (VastuGoodAspect | VastuDefect) | null;
  floorPlan?: any;
  landInfo?: any;
}

export function VastuInspectionModal({
  isOpen,
  onClose,
  item,
  floorPlan,
  landInfo,
}: VastuInspectionModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  if (!isOpen || !item) return null

  const isDefect = 'severity' in item
  const defect = isDefect ? (item as VastuDefect) : null
  const good = !isDefect ? (item as VastuGoodAspect) : null

  const highlightColor = isDefect 
    ? (defect?.severity === 'CRITICAL' ? '#ef4444' : '#f59e0b') 
    : '#10b981'

  const targetRoomIdentifier = item.room_id || item.room_name || null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      {/* Backdrop click dismiss */}
      <div className="fixed inset-0" onClick={onClose} />

      {/* Modal Card */}
      <div className="relative z-10 w-full max-w-5xl max-h-[92vh] flex flex-col bg-card/95 border border-border/80 rounded-2xl shadow-2xl overflow-hidden backdrop-blur-xl">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/60 bg-muted/20">
          <div className="flex items-center gap-3">
            <div 
              className={`w-9 h-9 rounded-xl flex items-center justify-center ${
                isDefect 
                  ? 'bg-destructive/15 text-destructive border border-destructive/30' 
                  : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
              }`}
            >
              {isDefect ? <AlertTriangle className="w-5 h-5" /> : <CheckCircle2 className="w-5 h-5" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base sm:text-lg font-bold text-foreground">
                  {item.title}
                </h3>
                <Badge 
                  variant="outline" 
                  className={`text-[10px] uppercase font-semibold ${
                    isDefect 
                      ? 'border-destructive/40 text-destructive bg-destructive/10' 
                      : 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
                  }`}
                >
                  {isDefect ? `${defect?.severity || 'DEFECT'}` : 'AUSPICIOUS COMPLIANT'}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Vastu Shastra Spatial Compliance Inspection
              </p>
            </div>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="w-8 h-8 p-0 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Content Body: Split View */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Left Canvas: Blueprint with glowing highlighted room */}
          <div className="lg:col-span-7 flex flex-col space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <Layers className="w-3.5 h-3.5 text-primary" /> Highlighted Room in Blueprint
              </span>
              <span className="text-[11px] font-mono">
                Room: <span className="text-primary font-semibold">{item.room_name || 'Spatial Zone'}</span>
              </span>
            </div>

            <div className="flex-1 min-h-[350px] w-full border border-border/50 rounded-xl overflow-hidden shadow-inner bg-slate-950/60">
              <FloorPlan2DViewer
                floorPlan={floorPlan}
                landInfo={landInfo}
                highlightRoomId={targetRoomIdentifier}
                highlightColor={highlightColor}
                dimOthers={true}
                showVastuGridDefault={true}
              />
            </div>
            <div className="text-[11px] text-muted-foreground text-center">
              The targeted room is isolated and glowing. 9x9 Vastu Padavinyasa grid & Brahmasthan overlay enabled.
            </div>
          </div>

          {/* Right Column: Vastu Analysis, Sector Details & Remedy */}
          <div className="lg:col-span-5 flex flex-col justify-between space-y-4">
            <div className="space-y-4">
              
              {/* Room & Direction Summary Card */}
              <div className="p-4 rounded-xl bg-muted/30 border border-border/50 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-[11px] uppercase tracking-wider text-muted-foreground flex items-center gap-1 mb-1 font-semibold">
                      <Home className="w-3 h-3 text-primary" /> Evaluated Space
                    </span>
                    <span className="text-sm font-bold text-foreground">
                      {item.room_name || 'Plot Sector'}
                    </span>
                  </div>

                  <div>
                    <span className="text-[11px] uppercase tracking-wider text-muted-foreground flex items-center gap-1 mb-1 font-semibold">
                      <Compass className="w-3 h-3 text-primary" /> Directional Sector
                    </span>
                    <span className="text-sm font-bold text-primary">
                      {item.sector_display || item.sector || 'Center (Brahmasthan)'}
                    </span>
                  </div>
                </div>

                <div className="pt-2 border-t border-border/40 flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Vastu Rule ID:</span>
                  <code className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono text-foreground">
                    {item.rule_id}
                  </code>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Score Impact:</span>
                  <span className={`font-bold ${isDefect ? 'text-destructive' : 'text-emerald-400'}`}>
                    {isDefect ? `-${defect?.points_deducted} Points` : `+${good?.points_earned} Points`}
                  </span>
                </div>
              </div>

              {/* Description Card */}
              <div className="p-4 rounded-xl bg-card border border-border/60 space-y-2">
                <h4 className="text-xs uppercase font-semibold tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-primary" /> Vastu Evaluation Analysis
                </h4>
                <p className="text-sm text-foreground/90 leading-relaxed">
                  {item.description}
                </p>
              </div>

              {/* Remedy Card (for Defects) */}
              {isDefect && defect?.remedy && (
                <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200/95 space-y-2">
                  <h4 className="text-xs uppercase font-bold tracking-wider text-amber-300 flex items-center gap-1.5">
                    <Lightbulb className="w-4 h-4 text-amber-400" /> Recommended Vastu Remedy
                  </h4>
                  <p className="text-xs sm:text-sm text-amber-100/90 leading-relaxed font-sans">
                    {defect.remedy}
                  </p>
                </div>
              )}

              {/* Auspicious Blessing Card (for Good Aspects) */}
              {!isDefect && (
                <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 space-y-2">
                  <h4 className="text-xs uppercase font-bold tracking-wider text-emerald-300 flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4 text-emerald-400" /> Harmonious Energy & Benefits
                  </h4>
                  <p className="text-xs sm:text-sm text-emerald-100/90 leading-relaxed">
                    This spatial placement strictly honors the traditional Vedic orientation principles, optimizing energy flow, ventilation, and family prosperity.
                  </p>
                </div>
              )}
            </div>

            {/* Modal Bottom Actions */}
            <div className="pt-4 border-t border-border/40 flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={onClose}
                className="text-xs px-5"
              >
                Close Inspection
              </Button>
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
