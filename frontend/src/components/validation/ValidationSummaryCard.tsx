"use client"
import React, { useState } from 'react'
import { ValidationResult } from '@/types/project'
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronUp,
  Grid3X3,
  Compass,
  DoorOpen,
  LayoutGrid,
  Layers,
  Home,
  MapPin,
} from 'lucide-react'

interface ValidationSummaryCardProps {
  validation: ValidationResult
}

const STATUS_CONFIG = {
  VALID: {
    label: 'Valid',
    icon: CheckCircle2,
    badgeClass: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
    headerClass: 'border-emerald-500/30 bg-emerald-500/5',
    iconClass: 'text-emerald-400',
  },
  VALID_WITH_WARNINGS: {
    label: 'Valid with Warnings',
    icon: AlertTriangle,
    badgeClass: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
    headerClass: 'border-amber-500/30 bg-amber-500/5',
    iconClass: 'text-amber-400',
  },
  INVALID: {
    label: 'Invalid',
    icon: XCircle,
    badgeClass: 'bg-red-500/20 text-red-300 border border-red-500/30',
    headerClass: 'border-red-500/30 bg-red-500/5',
    iconClass: 'text-red-400',
  },
  INSUFFICIENT_DATA: {
    label: 'Insufficient Data',
    icon: Info,
    badgeClass: 'bg-orange-500/20 text-orange-300 border border-orange-500/30',
    headerClass: 'border-orange-500/30 bg-orange-500/5',
    iconClass: 'text-orange-400',
  },
}

const VASTU_CHECKS = [
  {
    key: 'padavinyasa_9x9' as const,
    label: '9×9 Padavinyasa Grid',
    description: 'Grid origin, orientation & sector alignment',
    icon: Grid3X3,
  },
  {
    key: 'brahmasthan' as const,
    label: 'Brahmasthan Center',
    description: 'Central 3×3 zone evaluation',
    icon: LayoutGrid,
  },
  {
    key: 'entrance_32_pada' as const,
    label: '32-Pada Entrance Rule',
    description: 'Entrance sector alignment',
    icon: DoorOpen,
  },
  {
    key: 'directional_room_placement' as const,
    label: 'Directional Room Placement',
    description: 'Cardinal/ordinal quadrant assignment',
    icon: Compass,
  },
]

export function ValidationSummaryCard({ validation }: ValidationSummaryCardProps) {
  const [showErrors, setShowErrors] = useState(true)
  const [showWarnings, setShowWarnings] = useState(false)

  const cfg = STATUS_CONFIG[validation.status] || STATUS_CONFIG.INVALID
  const StatusIcon = cfg.icon
  const { spatial_summary, element_counts, vastu_readiness } = validation

  return (
    <div
      className="rounded-xl border bg-[#0e1119] overflow-hidden text-sm"
      style={{ borderColor: 'rgba(99,102,241,0.2)' }}
    >
      {/* ── Header ── */}
      <div className={`flex items-start gap-3 px-4 py-3 border-b ${cfg.headerClass}`}>
        <StatusIcon className={`mt-0.5 w-5 h-5 flex-shrink-0 ${cfg.iconClass}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-white">JSON Validation</span>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cfg.badgeClass}`}>
              {cfg.label}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-slate-400 leading-snug">{validation.summary}</p>
        </div>
      </div>

      {/* ── Element Counts ── */}
      <div className="grid grid-cols-3 gap-px bg-[rgb(99,102,241,0.08)] border-b border-[rgba(99,102,241,0.15)]">
        {[
          { label: 'Rooms', value: element_counts.rooms, icon: Home },
          { label: 'Struct. Elems', value: element_counts.structural_elements, icon: Layers },
          { label: 'Walls', value: element_counts.walls, icon: LayoutGrid },
          { label: 'Doors', value: element_counts.doors, icon: DoorOpen },
          { label: 'Windows', value: element_counts.windows, icon: Grid3X3 },
          { label: 'Orientation', value: spatial_summary.orientation, icon: Compass, isText: true },
        ].map(({ label, value, icon: Icon, isText }) => (
          <div key={label} className="flex flex-col items-center justify-center gap-1 bg-[#0e1119] py-2 px-1">
            <Icon className="w-3.5 h-3.5 text-indigo-400" />
            <span className={`font-semibold ${isText ? 'text-xs text-slate-200 text-center leading-tight' : 'text-base text-white'}`}>
              {value ?? '—'}
            </span>
            <span className="text-[10px] text-slate-500 text-center leading-tight">{label}</span>
          </div>
        ))}
      </div>

      {/* ── Bounding Box ── */}
      {spatial_summary.bounding_box && (
        <div className="px-4 py-2 border-b border-[rgba(99,102,241,0.12)] flex items-center gap-2 text-xs text-slate-400">
          <MapPin className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
          <span>
            Bounding box&nbsp;
            <strong className="text-slate-200">
              {spatial_summary.bounding_box.width.toFixed(1)} × {spatial_summary.bounding_box.height.toFixed(1)}
            </strong>
            {spatial_summary.area_sqft && (
              <> &nbsp;·&nbsp; {spatial_summary.area_sqft.toLocaleString()} sqft</>
            )}
          </span>
        </div>
      )}

      {/* ── Vastu Readiness ── */}
      <div className="px-4 py-3 border-b border-[rgba(99,102,241,0.12)]">
        <div className="flex items-center gap-2 mb-2">
          <Compass className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Vastu Readiness</span>
          <span
            className={`ml-auto px-2 py-0.5 rounded-full text-[10px] font-medium ${
              vastu_readiness.status === 'READY'
                ? 'bg-emerald-500/20 text-emerald-300'
                : vastu_readiness.status === 'PARTIALLY_READY'
                ? 'bg-amber-500/20 text-amber-300'
                : 'bg-red-500/20 text-red-300'
            }`}
          >
            {vastu_readiness.status.replace('_', ' ')}
          </span>
        </div>
        <div className="space-y-1.5">
          {VASTU_CHECKS.map(({ key, label, description, icon: Icon }) => {
            const check = vastu_readiness[key]
            return (
              <div key={key} className="flex items-start gap-2 p-2 rounded-lg bg-[#131722]">
                {check.ready ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <Icon className="w-3 h-3 text-indigo-400" />
                    <span className={`font-medium text-xs ${check.ready ? 'text-slate-200' : 'text-slate-400'}`}>
                      {label}
                    </span>
                  </div>
                  {!check.ready && check.reason && (
                    <p className="mt-0.5 text-[11px] text-slate-500 leading-snug">{check.reason}</p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Errors ── */}
      {validation.errors.length > 0 && (
        <div className="border-b border-[rgba(99,102,241,0.12)]">
          <button
            className="w-full flex items-center gap-2 px-4 py-2 text-xs text-red-400 hover:bg-red-500/5 transition-colors"
            onClick={() => setShowErrors((v) => !v)}
          >
            <XCircle className="w-3.5 h-3.5" />
            <span className="font-semibold">{validation.errors.length} Error{validation.errors.length > 1 ? 's' : ''}</span>
            <span className="ml-auto">{showErrors ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}</span>
          </button>
          {showErrors && (
            <ul className="px-4 pb-3 space-y-1.5">
              {validation.errors.map((err, i) => (
                <li key={i} className="flex gap-2 text-[11px] text-red-300 leading-snug">
                  <span className="text-red-500 mt-0.5 flex-shrink-0">▸</span>
                  <span>{err}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── Warnings ── */}
      {validation.warnings.length > 0 && (
        <div>
          <button
            className="w-full flex items-center gap-2 px-4 py-2 text-xs text-amber-400 hover:bg-amber-500/5 transition-colors"
            onClick={() => setShowWarnings((v) => !v)}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            <span className="font-semibold">{validation.warnings.length} Warning{validation.warnings.length > 1 ? 's' : ''}</span>
            <span className="ml-auto">{showWarnings ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}</span>
          </button>
          {showWarnings && (
            <ul className="px-4 pb-3 space-y-1.5">
              {validation.warnings.map((w, i) => (
                <li key={i} className="flex gap-2 text-[11px] text-amber-300 leading-snug">
                  <span className="text-amber-500 mt-0.5 flex-shrink-0">▸</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
