"use client"
import React, { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Compass, Sparkles, Layers, ArrowRight, CheckCircle2, AlertTriangle, Eye, RotateCcw } from 'lucide-react'

interface Room {
  id: string;
  name?: string;
  type?: string;
  polygon: [number, number][];
}

interface StructuralElement {
  id: string;
  type?: string;
  polygon: [number, number][];
}

export interface RoomModification {
  roomId: string;
  roomName: string;
  previousSector: string;
  newSector: string;
  reason: string;
  pointsGained: number;
  previousCenter?: [number, number];
  newCenter?: [number, number];
}

import { CADFloorPlanRenderer } from './CADFloorPlanRenderer'

interface FloorPlanDiffViewerProps {
  baselineFloorPlan?: {
    rooms?: Room[];
    structural_elements?: StructuralElement[];
  };
  rectifiedFloorPlan?: {
    rooms?: Room[];
    structural_elements?: StructuralElement[];
  };
  landInfo?: {
    orientation?: string;
    road_facing?: string;
    area_sqft?: number;
    boundary_points?: [number, number][];
  };
  modifications?: RoomModification[];
  selectedRoomId?: string | null;
  baselineScore?: number;
  rectifiedScore?: number;
  onSelectRoom?: (roomId: string) => void;
}

const ROOM_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  living: { fill: 'rgba(56, 189, 248, 0.25)', stroke: '#38bdf8', text: '#7dd3fc' },
  kitchen: { fill: 'rgba(251, 146, 60, 0.25)', stroke: '#fb923c', text: '#fed7aa' },
  master_bedroom: { fill: 'rgba(168, 85, 247, 0.25)', stroke: '#a855f7', text: '#e9d5ff' },
  bedroom: { fill: 'rgba(147, 51, 234, 0.22)', stroke: '#9333ea', text: '#d8b4fe' },
  pooja: { fill: 'rgba(234, 179, 8, 0.28)', stroke: '#eab308', text: '#fef08a' },
  bathroom: { fill: 'rgba(20, 184, 166, 0.25)', stroke: '#14b8a6', text: '#99f6e4' },
  dining: { fill: 'rgba(244, 63, 94, 0.22)', stroke: '#f43f5e', text: '#fecdd3' },
  default: { fill: 'rgba(99, 102, 241, 0.22)', stroke: '#6366f1', text: '#c7d2fe' },
}

function getRoomColor(type?: string, name?: string) {
  const key = (type || name || '').toLowerCase().replace(/[\s-_]/g, '_')
  for (const k in ROOM_COLORS) {
    if (key.includes(k)) return ROOM_COLORS[k]
  }
  return ROOM_COLORS.default
}

function getPolygonBBox(points: [number, number][]) {
  if (!points || points.length === 0) {
    return { minX: 0, minY: 0, maxX: 0, maxY: 0, width: 0, height: 0, cx: 0, cy: 0 }
  }
  const xs = points.map(p => p[0])
  const ys = points.map(p => p[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  return {
    minX,
    minY,
    maxX,
    maxY,
    width: Math.max(maxX - minX, 0.001),
    height: Math.max(maxY - minY, 0.001),
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
  }
}

function getPolygonCenter(points: [number, number][]): [number, number] {
  if (!points || points.length === 0) return [0, 0]
  const sum = points.reduce((acc, p) => [acc[0] + p[0], acc[1] + p[1]], [0, 0])
  return [sum[0] / points.length, sum[1] / points.length]
}

export function FloorPlanDiffViewer({
  baselineFloorPlan,
  rectifiedFloorPlan,
  landInfo,
  modifications = [],
  selectedRoomId,
  baselineScore,
  rectifiedScore,
  onSelectRoom,
}: FloorPlanDiffViewerProps) {
  // View mode: 'cad' (Architectural Blueprint) | 'after' | 'before' | 'overlay'
  const [viewMode, setViewMode] = useState<'cad' | 'after' | 'before' | 'overlay'>('cad')
  const [cadPlanType, setCadPlanType] = useState<'rectified' | 'baseline'>('rectified')
  const [highlightPulsing, setHighlightPulsing] = useState<boolean>(true)
  const [hoveredRoomId, setHoveredRoomId] = useState<string | null>(null)

  const activePlan = viewMode === 'before' ? baselineFloorPlan : rectifiedFloorPlan
  const rooms = useMemo(() => activePlan?.rooms || [], [activePlan])
  const columns = useMemo(() => activePlan?.structural_elements || [], [activePlan])
  const baselineRooms = useMemo(() => baselineFloorPlan?.rooms || [], [baselineFloorPlan])
  const rectifiedRooms = useMemo(() => rectifiedFloorPlan?.rooms || [], [rectifiedFloorPlan])
  const boundary = useMemo(() => landInfo?.boundary_points || [], [landInfo])

  const modifiedRoomIds = useMemo(() => {
    return new Set(modifications.map(m => m.roomId.toLowerCase()))
  }, [modifications])

  // Compute unified bounding box across both plans
  const bounds = useMemo(() => {
    let allPoints: [number, number][] = []
    baselineRooms.forEach(r => { if (Array.isArray(r.polygon)) allPoints.push(...r.polygon) })
    rectifiedRooms.forEach(r => { if (Array.isArray(r.polygon)) allPoints.push(...r.polygon) })
    if (boundary.length > 0) allPoints.push(...boundary)

    if (allPoints.length === 0) {
      return { 
        minX: 0, minY: 0, maxX: 100, maxY: 100, width: 100, height: 100,
        rawMinX: 0, rawMaxX: 100, rawMinY: 0, rawMaxY: 100, rawWidth: 100, rawHeight: 100,
        baseDim: 100
      }
    }

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    allPoints.forEach(([x, y]) => {
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
    })

    const rawW = Math.max(maxX - minX, 1)
    const rawH = Math.max(maxY - minY, 1)
    const baseDim = Math.max(rawW, rawH)

    const pad = baseDim * 0.08
    return {
      minX: minX - pad,
      minY: minY - pad,
      maxX: maxX + pad,
      maxY: maxY + pad,
      width: rawW + pad * 2,
      height: rawH + pad * 2,
      rawMinX: minX,
      rawMaxX: maxX,
      rawMinY: minY,
      rawMaxY: maxY,
      rawWidth: rawW,
      rawHeight: rawH,
      baseDim,
    }
  }, [baselineRooms, rectifiedRooms, boundary])

  const isYAxisUp = (activePlan as any)?.coordinate_system?.y_axis === 'up' || (activePlan as any)?.coordinate_system?.origin === 'bottom_left'
  const toSvgY = (y: number) => {
    if (isYAxisUp) {
      return bounds.minY + bounds.height - (y - bounds.minY)
    }
    return y
  }

  const formatPoints = (polygon: [number, number][]) => {
    if (!Array.isArray(polygon)) return ''
    return polygon.map(([x, y]) => `${x},${toSvgY(y)}`).join(' ')
  }

  return (
    <div className="flex flex-col w-full h-full bg-slate-950/80 border border-border/70 rounded-2xl overflow-hidden backdrop-blur shadow-2xl">
      {/* Dynamic CSS for Pulsating Glow Animation */}
      <style jsx global>{`
        @keyframes vastuPulsateGlow {
          0%, 100% {
            filter: drop-shadow(0 0 6px #10b981) drop-shadow(0 0 14px rgba(16, 185, 129, 0.7));
            opacity: 0.95;
          }
          50% {
            filter: drop-shadow(0 0 20px #34d399) drop-shadow(0 0 35px rgba(52, 211, 153, 0.9));
            opacity: 0.7;
          }
        }
        .vastu-pulsing-room {
          animation: vastuPulsateGlow 1.8s ease-in-out infinite;
        }
      `}</style>

      {/* Top Interactive Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-card/75 border-b border-border/50 text-xs">
        
        {/* View Mode Toggle: CAD Blueprint / After / Before / Overlay */}
        <div className="flex items-center gap-1.5 p-1 bg-slate-900/90 rounded-xl border border-border/50">
          <button
            type="button"
            onClick={() => setViewMode('cad')}
            className={`px-3 py-1 rounded-lg font-semibold text-xs transition-all flex items-center gap-1.5 ${
              viewMode === 'cad'
                ? 'bg-primary/25 text-primary border border-primary/50 shadow-sm'
                : 'text-muted-foreground hover:text-foreground border border-transparent'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            VUE EN PLAN (CAD)
          </button>

          {viewMode === 'cad' && (
            <div className="flex items-center gap-1 bg-slate-950/80 p-0.5 rounded-md border border-border/40 ml-1">
              <button
                type="button"
                onClick={() => setCadPlanType('rectified')}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  cadPlanType === 'rectified'
                    ? 'bg-emerald-500/25 text-emerald-300 border border-emerald-500/40 shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Rectified
              </button>
              <button
                type="button"
                onClick={() => setCadPlanType('baseline')}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  cadPlanType === 'baseline'
                    ? 'bg-amber-500/25 text-amber-300 border border-amber-500/40 shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Baseline
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={() => setViewMode('after')}
            className={`px-3 py-1 rounded-lg font-semibold text-xs transition-all flex items-center gap-1.5 ${
              viewMode === 'after'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                : 'text-muted-foreground hover:text-foreground border border-transparent'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            AI Rectified (After)
          </button>

          <button
            type="button"
            onClick={() => setViewMode('before')}
            className={`px-3 py-1 rounded-lg font-semibold text-xs transition-all ${
              viewMode === 'before'
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm'
                : 'text-muted-foreground hover:text-foreground border border-transparent'
            }`}
          >
            Baseline (Before)
          </button>

          <button
            type="button"
            onClick={() => setViewMode('overlay')}
            className={`px-3 py-1 rounded-lg font-semibold text-xs transition-all ${
              viewMode === 'overlay'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow-sm'
                : 'text-muted-foreground hover:text-foreground border border-transparent'
            }`}
          >
            Overlay Diff
          </button>
        </div>

        {/* Highlight Pulsing Glow Button & Orientation */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setHighlightPulsing(!highlightPulsing)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              highlightPulsing
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 ring-1 ring-emerald-500/30 shadow-md shadow-emerald-500/10'
                : 'bg-muted/30 text-muted-foreground border-border/50 hover:text-foreground'
            }`}
          >
            <Sparkles className={`w-3.5 h-3.5 ${highlightPulsing ? 'animate-spin' : ''}`} />
            <span>Highlight Changes</span>
          </button>

          <div className="flex items-center gap-1 text-muted-foreground text-xs whitespace-nowrap pl-2 border-l border-border/50">
            <Compass className="w-3.5 h-3.5 text-primary" />
            <span className="font-semibold text-foreground">{landInfo?.orientation || 'North'}</span>
          </div>
        </div>
      </div>

      {viewMode === 'cad' ? (
        <CADFloorPlanRenderer
          rooms={(cadPlanType === 'baseline' ? baselineRooms : rectifiedRooms).map(r => ({
            id: r.id,
            name: r.name,
            type: r.type,
            polygon: r.polygon,
            isRectified: cadPlanType === 'baseline' ? false : modifiedRoomIds.has(r.id.toLowerCase()),
          }))}
          structuralElements={cadPlanType === 'baseline' ? (baselineFloorPlan?.structural_elements || []) : columns}
          landInfo={landInfo}
          title={cadPlanType === 'baseline' ? "VUE EN PLAN — BASELINE (ORIGINAL)" : "VUE EN PLAN — RECTIFIÉ (VASTU)"}
          score={cadPlanType === 'baseline' ? baselineScore : rectifiedScore}
        />
      ) : (
        /* Main Blueprint Canvas Area */
        <div className="relative w-full aspect-[4/3] min-h-[420px] max-h-[580px] p-4 flex items-center justify-center overflow-hidden">
        <svg
          viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
          className="w-full h-full select-none"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <pattern
              id="diff-grid"
              width={bounds.width / 24}
              height={bounds.height / 24}
              patternUnits="userSpaceOnUse"
            >
              <path
                d={`M ${bounds.width / 24} 0 L 0 0 0 ${bounds.height / 24}`}
                fill="none"
                stroke="rgba(255, 255, 255, 0.04)"
                strokeWidth="0.5"
              />
            </pattern>

            {/* Glowing filter for highlighted rooms */}
            <filter id="diff-glow" x="-25%" y="-25%" width="150%" height="150%">
              <feDropShadow dx="0" dy="0" stdDeviation="2.5" floodColor="#10b981" floodOpacity="0.85" />
            </filter>

            {/* Arrowhead marker for displacement vectors */}
            <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#10b981" />
            </marker>
          </defs>

          {/* Grid Background */}
          <rect
            x={bounds.minX}
            y={bounds.minY}
            width={bounds.width}
            height={bounds.height}
            fill="url(#diff-grid)"
          />

          {/* Land Boundary */}
          {boundary.length >= 3 && (
            <polygon
              points={formatPoints(boundary)}
              fill="rgba(99, 102, 241, 0.03)"
              stroke="rgba(99, 102, 241, 0.45)"
              strokeWidth="0.8"
              strokeDasharray="3,2"
            />
          )}

          {/* OVERLAY MODE: Ghost of previous Baseline plan (dashed rose) */}
          {viewMode === 'overlay' && baselineRooms.map((room, idx) => (
            <g key={`ghost-${room.id || idx}`} opacity="0.45">
              <polygon
                points={formatPoints(room.polygon)}
                fill="rgba(244, 63, 94, 0.12)"
                stroke="#f43f5e"
                strokeWidth="1.2"
                strokeDasharray="3,3"
              />
            </g>
          ))}

          {/* Render Active Plan Rooms */}
          {rooms.map((room, idx) => {
            const rId = room.id.toLowerCase()
            const isModified = modifiedRoomIds.has(rId) || modifiedRoomIds.has((room.name || '').toLowerCase())
            const isHovered = hoveredRoomId === room.id
            const isSelected = selectedRoomId === room.id || (selectedRoomId && room.name?.toLowerCase().includes(selectedRoomId.toLowerCase()))
            
            const color = getRoomColor(room.type, room.name)
            const bbox = getPolygonBBox(room.polygon)
            const shouldPulse = highlightPulsing && isModified && (viewMode === 'after' || viewMode === 'overlay')

            const rW = Math.max(bbox.width, bounds.baseDim * 0.05)
            const rH = Math.max(bbox.height, bounds.baseDim * 0.05)
            const charCount = Math.max((room.name || room.type || '').length, 4)

            const maxFontByW = (rW * 0.88) / (charCount * 0.55)
            const maxFontByH = rH * 0.22
            const idealFont = Math.min(bounds.baseDim * 0.026, maxFontByW, maxFontByH)
            const fontSize = Math.max(idealFont, bounds.baseDim * 0.009)

            const strokeWidth = isModified || isSelected 
              ? bounds.baseDim * 0.012 
              : (isHovered ? bounds.baseDim * 0.007 : bounds.baseDim * 0.004)

            const cx = bbox.cx
            const cy = toSvgY(bbox.cy)
            const tagText = isModified && (viewMode === 'after' || viewMode === 'overlay')
              ? '★ RECTIFIED'
              : (viewMode === 'before' && isModified ? '⚠ DEFECT' : '')
            const nameY = tagText ? cy - fontSize * 0.55 : cy
            const tagY = cy + fontSize * 0.75
            const tagFontSize = fontSize * 0.8

            return (
              <g
                key={room.id || idx}
                onMouseEnter={() => setHoveredRoomId(room.id)}
                onMouseLeave={() => setHoveredRoomId(null)}
                onClick={() => onSelectRoom?.(room.id)}
                className={`cursor-pointer transition-all ${shouldPulse ? 'vastu-pulsing-room' : ''}`}
              >
                {/* Room Geometry Polygon */}
                <polygon
                  points={formatPoints(room.polygon)}
                  fill={
                    isSelected
                      ? '#10b98133'
                      : (isModified && (viewMode === 'after' || viewMode === 'overlay')
                        ? 'rgba(16, 185, 129, 0.28)'
                        : color.fill)
                  }
                  stroke={
                    isSelected
                      ? '#10b981'
                      : (isModified && (viewMode === 'after' || viewMode === 'overlay')
                        ? '#10b981'
                        : color.stroke)
                  }
                  strokeWidth={strokeWidth}
                  filter={shouldPulse ? 'url(#diff-glow)' : undefined}
                />

                {/* Room Label */}
                <text
                  x={cx}
                  y={nameY}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#ffffff"
                  fontSize={fontSize}
                  fontWeight="700"
                  className="font-sans drop-shadow select-none"
                >
                  {room.name || room.type}
                </text>

                {/* Subtitle / Rectification Tag */}
                {tagText && (
                  <text
                    x={cx}
                    y={tagY}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={isModified ? '#34d399' : '#94a3b8'}
                    fontSize={tagFontSize}
                    fontWeight={isModified ? '700' : '500'}
                    className="font-mono tracking-tight select-none"
                  >
                    {tagText}
                  </text>
                )}
              </g>
            )
          })}

          {/* OVERLAY MODE: Draw Animated Displacement Vectors (Arrows from old center to new center) */}
          {viewMode === 'overlay' && modifications.map((mod, i) => {
            if (!mod.previousCenter || !mod.newCenter) return null
            const [x1, y1] = mod.previousCenter
            const [x2, y2] = mod.newCenter
            return (
              <g key={`arrow-${i}`}>
                <line
                  x1={x1}
                  y1={toSvgY(y1)}
                  x2={x2}
                  y2={toSvgY(y2)}
                  stroke="#10b981"
                  strokeWidth={bounds.baseDim * 0.007}
                  strokeDasharray={`${bounds.baseDim * 0.015},${bounds.baseDim * 0.01}`}
                  markerEnd="url(#arrow)"
                />
              </g>
            )
          })}
        </svg>

        {/* State Indicator Floating Badge */}
        <div className="absolute top-4 left-4 flex items-center gap-2">
          {viewMode === 'before' && (
            <Badge className="bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold px-2.5 py-1">
              Baseline Geometry ({baselineScore ?? 42}% Score)
            </Badge>
          )}
          {viewMode === 'after' && (
            <Badge className="bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold px-2.5 py-1">
              AI Rectified Geometry ({rectifiedScore ?? 88}% Score)
            </Badge>
          )}
          {viewMode === 'overlay' && (
            <Badge className="bg-sky-500/20 text-sky-300 border border-sky-500/40 font-semibold px-2.5 py-1">
              Red Dashed = Before | Solid Green = After
            </Badge>
          )}
        </div>
      </div>
      )}
    </div>
  )
}
