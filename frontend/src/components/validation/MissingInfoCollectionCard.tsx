"use client"
import React, { useState, useEffect } from 'react'
import { MissingInfoReport, MissingInfoQuestion } from '@/types/project'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  AlertTriangle, 
  HelpCircle, 
  CheckCircle2, 
  ArrowRight, 
  Compass, 
  DoorOpen, 
  Home, 
  Layers,
  Sparkles,
  Info
} from 'lucide-react'

interface MissingInfoCollectionCardProps {
  report: MissingInfoReport;
  onSubmit: (confirmedAnswers: Record<string, any>) => Promise<void>;
  isSubmitting?: boolean;
  onHighlightElement?: (elementId: string | null) => void;
  onDismiss?: () => void;
}

export function MissingInfoCollectionCard({
  report,
  onSubmit,
  isSubmitting = false,
  onHighlightElement,
  onDismiss,
}: MissingInfoCollectionCardProps) {
  const [answers, setAnswers] = useState<Record<string, any>>({})

  // Initialize answers from current_value or suggested_value
  useEffect(() => {
    if (!report?.questions) return
    const initial: Record<string, any> = {}
    report.questions.forEach((q) => {
      initial[q.id] = q.current_value !== null && q.current_value !== undefined && q.current_value !== ""
        ? q.current_value
        : q.suggested_value
    })
    setAnswers(initial)
  }, [report])

  if (!report || !report.questions || report.questions.length === 0) {
    return null
  }

  const handleValueChange = (questionId: string, value: any) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: value,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onSubmit(answers)
  }

  const requiredCount = report.questions.filter((q) => q.is_required).length
  const conflictCount = report.questions.filter((q) => q.has_conflict).length

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'orientation':
        return <Compass className="w-4 h-4 text-sky-400" />
      case 'main_entrance':
      case 'door_direction':
        return <DoorOpen className="w-4 h-4 text-emerald-400" />
      case 'room_type':
        return <Home className="w-4 h-4 text-amber-400" />
      case 'geometry_conflict':
        return <AlertTriangle className="w-4 h-4 text-rose-400" />
      default:
        return <Layers className="w-4 h-4 text-indigo-400" />
    }
  }

  return (
    <div className="w-full bg-gradient-to-b from-slate-900/90 to-card/90 border border-primary/40 rounded-2xl p-5 md:p-6 shadow-xl backdrop-blur-md transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border/50">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-xl bg-primary/10 border border-primary/30 text-primary mt-0.5">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-bold text-foreground">
                Plan Information Review Required
              </h3>
              {requiredCount > 0 && (
                <Badge variant="outline" className="text-[10px] font-semibold border-amber-500/40 text-amber-400 bg-amber-500/10">
                  {requiredCount} Required
                </Badge>
              )}
              {conflictCount > 0 && (
                <Badge variant="outline" className="text-[10px] font-semibold border-rose-500/40 text-rose-400 bg-rose-500/10">
                  {conflictCount} Conflict{conflictCount > 1 ? 's' : ''}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              VSAI detected missing, ambiguous, or conflicting items in this floor plan. Please confirm or provide details below before running the 4-Group Vastu analysis.
            </p>
          </div>
        </div>

        {onDismiss && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDismiss}
            className="text-muted-foreground hover:text-foreground text-xs self-start"
          >
            Dismiss
          </Button>
        )}
      </div>

      {/* Dynamic Form */}
      <form onSubmit={handleSubmit} className="mt-5 space-y-5">
        {report.questions.map((q: MissingInfoQuestion) => {
          const val = answers[q.id] !== undefined ? answers[q.id] : (q.current_value || q.suggested_value || '')
          return (
            <div
              key={q.id}
              onMouseEnter={() => q.target_element_id && onHighlightElement?.(q.target_element_id)}
              onMouseLeave={() => onHighlightElement?.(null)}
              className={`p-4 rounded-xl border transition-all ${
                q.has_conflict
                  ? 'bg-rose-950/20 border-rose-500/40 hover:border-rose-500/60'
                  : 'bg-card/40 border-border/60 hover:border-border'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  {getCategoryIcon(q.category)}
                  <span className="text-xs font-bold text-foreground">
                    {q.title}
                  </span>
                </div>
                {q.is_required ? (
                  <Badge variant="outline" className="text-[9px] uppercase tracking-wider px-1.5 py-0 border-amber-500/40 text-amber-400 bg-amber-500/10 font-bold">
                    Required
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[9px] uppercase tracking-wider px-1.5 py-0 border-border/50 text-muted-foreground">
                    Optional
                  </Badge>
                )}
              </div>

              <p className="text-[11px] text-muted-foreground leading-relaxed mb-3">
                {q.description}
              </p>

              {/* Conflict Callout */}
              {q.has_conflict && q.suggested_value && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center gap-2 text-[11px] text-rose-300">
                  <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                  <span>
                    Conflict detected. Suggested resolution based on geometry: <strong className="font-semibold text-rose-200">{q.suggested_value}</strong>
                  </span>
                </div>
              )}

              {/* Input Control */}
              {q.input_type === 'radio' && q.options && q.options.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                  {q.options.map((opt) => (
                    <label
                      key={opt.value}
                      className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-xs cursor-pointer transition-all ${
                        val === opt.value
                          ? 'bg-primary/15 border-primary text-foreground font-semibold shadow-sm'
                          : 'bg-muted/20 border-border/50 text-muted-foreground hover:text-foreground hover:bg-muted/40'
                      }`}
                    >
                      <input
                        type="radio"
                        name={q.id}
                        value={opt.value}
                        checked={val === opt.value}
                        onChange={(e) => handleValueChange(q.id, e.target.value)}
                        className="text-primary focus:ring-primary h-3.5 w-3.5"
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              ) : q.options && q.options.length > 0 ? (
                <select
                  value={val}
                  onChange={(e) => handleValueChange(q.id, e.target.value)}
                  className="w-full h-9 px-3 rounded-lg bg-slate-900 border border-border/70 text-foreground text-xs focus:ring-1 focus:ring-primary focus:border-primary outline-none transition-colors"
                >
                  <option value="" disabled>
                    -- Select {q.title} --
                  </option>
                  {q.options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={val}
                  onChange={(e) => handleValueChange(q.id, e.target.value)}
                  placeholder={`Enter ${q.title}...`}
                  className="w-full h-9 px-3 rounded-lg bg-slate-900 border border-border/70 text-foreground text-xs focus:ring-1 focus:ring-primary focus:border-primary outline-none transition-colors"
                />
              )}
            </div>
          )
        })}

        {/* Submit Actions */}
        <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Info className="w-3.5 h-3.5 text-primary shrink-0" />
            <span>Changing orientation or main entrance will trigger a fresh Vastu recalculation.</span>
          </div>

          <Button
            type="submit"
            disabled={isSubmitting}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-xs shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2 shrink-0 cursor-pointer"
          >
            {isSubmitting ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Recalculating Vastu Analysis...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                <span>Apply Changes & Re-analyze Vastu</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  )
}

