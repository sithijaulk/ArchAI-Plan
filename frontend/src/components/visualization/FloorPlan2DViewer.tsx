"use client"
import React, { useMemo, useState, useEffect } from 'react'
import { Badge } from '@/components/ui/badge'
import { Compass, Maximize2, Layers, CheckCircle2, Grid3X3 } from 'lucide-react'

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

interface FloorPlan2DViewerProps {
  floorPlan?: {
    rooms?: Room[];
    structural_elements?: StructuralElement[];
  };
  landInfo?: {
    orientation?: string;
    road_facing?: string;
    area_sqft?: number;
    boundary_points?: [number, number][];
  };
  rectificationResult?: any;
  highlightRoomId?: string | null;
  highlightColor?: string;
  dimOthers?: boolean;
  showVastuGridDefault?: boolean;
  hideLegend?: boolean;
  compactTopBar?: boolean;
}

const ROOM_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  living: { fill: 'rgba(56, 189, 248, 0.25)', stroke: '#38bdf8', text: '#7dd3fc' },
  kitchen: { fill: 'rgba(251, 146, 60, 0.25)', stroke: '#fb923c', text: '#fed7aa' },
  master_bedroom: { fill: 'rgba(168, 85, 247, 0.25)', stroke: '#a855f7', text: '#e9d5ff' },
  bedroom: { fill: 'rgba(147, 51, 234, 0.22)', stroke: '#9333ea', text: '#d8b4fe' },
  pooja: { fill: 'rgba(234, 179, 8, 0.28)', stroke: '#eab308', text: '#fef08a' },
  bathroom: { fill: 'rgba(20, 184, 166, 0.25)', stroke: '#14b8a6', text: '#99f6e4' },
  bath: { fill: 'rgba(20, 184, 166, 0.25)', stroke: '#14b8a6', text: '#99f6e4' },
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

function calculateArea(points: [number, number][]): number {
  if (!points || points.length < 3) return 0
  let area = 0
  for (let i = 0; i < points.length; i++) {
    const j = (i + 1) % points.length
    area += points[i][0] * points[j][1]
    area -= points[j][0] * points[i][1]
  }
  return Math.abs(area / 2)
}

export function FloorPlan2DViewer({
  floorPlan,
  landInfo,
  rectificationResult,
  highlightRoomId,
  highlightColor = '#ef4444',
  dimOthers = false,
  showVastuGridDefault = false,
  hideLegend = false,
  compactTopBar = false,
}: FloorPlan2DViewerProps) {
  const [hoveredRoom, setHoveredRoom] = useState<Room | null>(null)
  const [showVastuGrid, setShowVastuGrid] = useState<boolean>(showVastuGridDefault)

  useEffect(() => {
    if (showVastuGridDefault !== undefined) {
      setShowVastuGrid(showVastuGridDefault)
    }
  }, [showVastuGridDefault])

  const rooms = useMemo(() => floorPlan?.rooms || [], [floorPlan])
  const columns = useMemo(() => floorPlan?.structural_elements || [], [floorPlan])
  const boundary = useMemo(() => landInfo?.boundary_points || [], [landInfo])

  // Compute bounding box for auto-scaling
  const bounds = useMemo(() => {
    let allPoints: [number, number][] = []
    rooms.forEach(r => { if (Array.isArray(r.polygon)) allPoints.push(...r.polygon) })
    columns.forEach(c => { if (Array.isArray(c.polygon)) allPoints.push(...c.polygon) })
    if (boundary.length > 0) allPoints.push(...boundary)

    if (allPoints.length === 0) {
      return { 
        minX: 0, minY: 0, maxX: 100, maxY: 100, width: 100, height: 100,
        rawMinX: 0, rawMaxX: 100, rawMinY: 0, rawMaxY: 100, rawWidth: 100, rawHeight: 100,
        baseDim: 100
      }
    }

    const xs = allPoints.map(p => p[0])
    const ys = allPoints.map(p => p[1])
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)

    const rawW = Math.max(maxX - minX, 1)
    const rawH = Math.max(maxY - minY, 1)
    const baseDim = Math.max(rawW, rawH)

    const paddingX = rawW * 0.08
    const paddingY = rawH * 0.08

    return {
      minX: minX - paddingX,
      minY: minY - paddingY,
      maxX: maxX + paddingX,
      maxY: maxY + paddingY,
      width: rawW + paddingX * 2,
      height: rawH + paddingY * 2,
      rawMinX: minX,
      rawMaxX: maxX,
      rawMinY: minY,
      rawMaxY: maxY,
      rawWidth: rawW,
      rawHeight: rawH,
      baseDim,
    }
  }, [rooms, columns, boundary])

  // Only invert Y if the coordinate system explicitly declares y_axis as "up" or origin as "bottom_left"
  const isYAxisUp = (floorPlan as any)?.coordinate_system?.y_axis === 'up' || (floorPlan as any)?.coordinate_system?.origin === 'bottom_left'
  const toSvgY = (y: number) => {
    if (isYAxisUp) {
      return bounds.minY + bounds.height - (y - bounds.minY)
    }
    return y
  }

  const formatPoints = (points: [number, number][]) => {
    return points.map(p => `${p[0]},${toSvgY(p[1])}`).join(' ')
  }

  // 3x3 Vastu Padavinyasa grid lines calculation
  const vastuGridSectors = useMemo(() => {
    if (!bounds.rawWidth || !bounds.rawHeight) return null
    const x1 = bounds.rawMinX
    const x2 = bounds.rawMinX + bounds.rawWidth / 3
    const x3 = bounds.rawMinX + (2 * bounds.rawWidth) / 3
    const x4 = bounds.rawMaxX

    const y1 = bounds.rawMinY
    const y2 = bounds.rawMinY + bounds.rawHeight / 3
    const y3 = bounds.rawMinY + (2 * bounds.rawHeight) / 3
    const y4 = bounds.rawMaxY

    return { x1, x2, x3, x4, y1, y2, y3, y4 }
  }, [bounds])

  return (
    <div className="flex flex-col w-full h-full bg-slate-950/70 border border-border/60 rounded-2xl overflow-hidden backdrop-blur">
      {/* Top Status Bar */}
      <div className="flex items-center justify-between px-3.5 py-2 bg-card/60 border-b border-border/40 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          {!compactTopBar ? (
            <Badge variant="outline" className="gap-1.5 py-0.5 font-medium border-primary/30 text-primary shrink-0">
              <Layers className="w-3.5 h-3.5" /> 2D Vector Blueprint
            </Badge>
          ) : (
            <div className="flex items-center gap-1.5 text-primary font-semibold text-xs shrink-0">
              <Layers className="w-3.5 h-3.5" />
              <span>Blueprint</span>
            </div>
          )}
          <span className="text-muted-foreground text-[11px] whitespace-nowrap">
            {rooms.length} Rooms
            {columns.length > 0 && ` • ${columns.length} Cols`}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setShowVastuGrid(!showVastuGrid)}
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-colors border shrink-0 ${
              showVastuGrid
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 ring-1 ring-amber-500/30'
                : 'bg-muted/30 text-muted-foreground border-border/50 hover:text-foreground'
            }`}
          >
            <Grid3X3 className="w-3.5 h-3.5" />
            <span className="whitespace-nowrap">9×9 Grid</span>
          </button>

          <div className="flex items-center gap-1 text-muted-foreground text-[11px] shrink-0 whitespace-nowrap">
            <Compass className="w-3.5 h-3.5 text-primary shrink-0" />
            <span className="font-semibold text-foreground whitespace-nowrap">
              {landInfo?.orientation || 'North'}
            </span>
          </div>
        </div>
      </div>

      {/* Main SVG Blueprint Canvas */}
      <div className="relative w-full aspect-[4/3] min-h-[380px] max-h-[520px] p-4 flex items-center justify-center overflow-hidden">
        <svg
          viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
          className="w-full h-full select-none"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Grid Pattern */}
            <pattern
              id="blueprint-grid"
              width={bounds.width / 20}
              height={bounds.height / 20}
              patternUnits="userSpaceOnUse"
            >
              <path
                d={`M ${bounds.width / 20} 0 L 0 0 0 ${bounds.height / 20}`}
                fill="none"
                stroke="rgba(255, 255, 255, 0.05)"
                strokeWidth="0.5"
              />
            </pattern>
            {/* Column Glow Filter */}
            <filter id="column-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="0" stdDeviation="0.8" floodColor="#f43f5e" floodOpacity="0.8" />
            </filter>
            {/* Room Highlight Glow Filter */}
            <filter id="room-highlight-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="2.0" floodColor={highlightColor} floodOpacity="0.9" />
            </filter>
          </defs>

          {/* Grid Background */}
          <rect
            x={bounds.minX}
            y={bounds.minY}
            width={bounds.width}
            height={bounds.height}
            fill="url(#blueprint-grid)"
          />

          {/* 3x3 Vastu Padavinyasa Grid Overlay */}
          {showVastuGrid && vastuGridSectors && (
            <g className="vastu-grid-overlay pointer-events-none">
              {/* Brahmasthan central core fill */}
              <rect
                x={vastuGridSectors.x2}
                y={vastuGridSectors.y2}
                width={vastuGridSectors.x3 - vastuGridSectors.x2}
                height={vastuGridSectors.y3 - vastuGridSectors.y2}
                fill="rgba(234, 179, 8, 0.12)"
                stroke="rgba(234, 179, 8, 0.6)"
                strokeWidth={bounds.baseDim * 0.005}
                strokeDasharray={`${bounds.baseDim * 0.015},${bounds.baseDim * 0.01}`}
              />
              <text
                x={(vastuGridSectors.x2 + vastuGridSectors.x3) / 2}
                y={(vastuGridSectors.y2 + vastuGridSectors.y3) / 2}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="#fbbf24"
                fontSize={bounds.baseDim * 0.024}
                fontWeight="700"
                className="font-mono tracking-widest drop-shadow opacity-85"
              >
                BRAHMASTHAN
              </text>

              {/* Grid vertical lines */}
              <line
                x1={vastuGridSectors.x2}
                y1={vastuGridSectors.y1}
                x2={vastuGridSectors.x2}
                y2={vastuGridSectors.y4}
                stroke="rgba(234, 179, 8, 0.4)"
                strokeWidth={bounds.baseDim * 0.003}
                strokeDasharray={`${bounds.baseDim * 0.01},${bounds.baseDim * 0.01}`}
              />
              <line
                x1={vastuGridSectors.x3}
                y1={vastuGridSectors.y1}
                x2={vastuGridSectors.x3}
                y2={vastuGridSectors.y4}
                stroke="rgba(234, 179, 8, 0.4)"
                strokeWidth={bounds.baseDim * 0.003}
                strokeDasharray={`${bounds.baseDim * 0.01},${bounds.baseDim * 0.01}`}
              />

              {/* Grid horizontal lines */}
              <line
                x1={vastuGridSectors.x1}
                y1={vastuGridSectors.y2}
                x2={vastuGridSectors.x4}
                y2={vastuGridSectors.y2}
                stroke="rgba(234, 179, 8, 0.4)"
                strokeWidth={bounds.baseDim * 0.003}
                strokeDasharray={`${bounds.baseDim * 0.01},${bounds.baseDim * 0.01}`}
              />
              <line
                x1={vastuGridSectors.x1}
                y1={vastuGridSectors.y3}
                x2={vastuGridSectors.x4}
                y2={vastuGridSectors.y3}
                stroke="rgba(234, 179, 8, 0.4)"
                strokeWidth={bounds.baseDim * 0.003}
                strokeDasharray={`${bounds.baseDim * 0.01},${bounds.baseDim * 0.01}`}
              />
            </g>
          )}

          {/* Land / Plot Boundary (if defined) */}
          {boundary.length >= 3 && (
            <polygon
              points={formatPoints(boundary)}
              fill="rgba(99, 102, 241, 0.04)"
              stroke="rgba(99, 102, 241, 0.5)"
              strokeWidth={bounds.baseDim * 0.004}
              strokeDasharray={`${bounds.baseDim * 0.01},${bounds.baseDim * 0.01}`}
            />
          )}

          {/* Rooms Polygons */}
          {rooms.map((room, idx) => {
            const isHovered = hoveredRoom?.id === room.id
            const hlLower = (highlightRoomId || '').toLowerCase().trim()
            const rIdLower = (room.id || '').toLowerCase().trim()
            const rNameLower = (room.name || '').toLowerCase().trim()
            const rTypeLower = (room.type || '').toLowerCase().trim()
            
            const isTargetHighlight = Boolean(
              highlightRoomId && (
                rIdLower === hlLower ||
                (rNameLower && (rNameLower.includes(hlLower) || hlLower.includes(rNameLower))) ||
                (rTypeLower && (rTypeLower.includes(hlLower) || hlLower.includes(rTypeLower)))
              )
            )
            const color = getRoomColor(room.type, room.name)
            const bbox = getPolygonBBox(room.polygon)
            const area = calculateArea(room.polygon)

            // Calculate room-fitted font size so labels never overflow small rooms
            const rW = Math.max(bbox.width, bounds.baseDim * 0.05)
            const rH = Math.max(bbox.height, bounds.baseDim * 0.05)
            const charCount = Math.max((room.name || room.type || '').length, 4)

            const maxFontByW = (rW * 0.88) / (charCount * 0.55)
            const maxFontByH = rH * 0.24
            const idealFont = Math.min(bounds.baseDim * 0.026, maxFontByW, maxFontByH)
            const fontSize = Math.max(idealFont, bounds.baseDim * 0.009)

            const strokeWidth = isTargetHighlight 
              ? bounds.baseDim * 0.012 
              : (isHovered ? bounds.baseDim * 0.007 : bounds.baseDim * 0.004)

            const cx = bbox.cx
            const cy = toSvgY(bbox.cy)
            const nameY = area > 0 ? cy - fontSize * 0.55 : cy
            const areaY = cy + fontSize * 0.75
            const areaFontSize = fontSize * 0.8

            // Determine display units
            const units = (floorPlan as any)?.units?.toLowerCase() || ''
            let areaDisplay = ''
            if (units === 'm' || units === 'meters' || units === 'meter') {
              areaDisplay = `${area.toFixed(1)} m²`
            } else if (units === 'mm' || units === 'millimeters') {
              const m2 = area / 1_000_000
              areaDisplay = m2 >= 0.1 ? `${m2.toFixed(1)} m²` : `${Math.round(area)} mm²`
            } else if (units === 'ft' || units === 'feet') {
              areaDisplay = `${Math.round(area)} sqft`
            } else {
              if (area > 5000) {
                areaDisplay = `${(area / 1_000_000).toFixed(1)} m²`
              } else if (area < 500) {
                areaDisplay = `${area.toFixed(1)} m²`
              } else {
                areaDisplay = `${Math.round(area)} sqft`
              }
            }

            // Dim others when inspecting a specific room
            const opacity = dimOthers && highlightRoomId && !isTargetHighlight ? 0.22 : 1.0

            return (
              <g 
                key={room.id || idx}
                onMouseEnter={() => setHoveredRoom(room)}
                onMouseLeave={() => setHoveredRoom(null)}
                className="cursor-pointer transition-all duration-200"
                style={{ opacity, transition: 'opacity 0.25s ease-in-out' }}
              >
                {/* Room Geometry */}
                <polygon
                  points={formatPoints(room.polygon)}
                  fill={
                    isTargetHighlight
                      ? `${highlightColor}33`
                      : (isHovered ? color.fill.replace('0.25', '0.45').replace('0.22', '0.42') : color.fill)
                  }
                  stroke={isTargetHighlight ? highlightColor : color.stroke}
                  strokeWidth={strokeWidth}
                  filter={isTargetHighlight ? 'url(#room-highlight-glow)' : undefined}
                  className="transition-all"
                />

                {/* Room Name Label */}
                <text
                  x={cx}
                  y={nameY}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill={isTargetHighlight ? highlightColor : color.text}
                  fontSize={fontSize}
                  fontWeight={isTargetHighlight ? '800' : '600'}
                  className="pointer-events-none drop-shadow select-none"
                >
                  {room.name || room.type || `Room ${idx + 1}`}
                </text>

                {/* Area Tag */}
                {area > 0 && (
                  <text
                    x={cx}
                    y={areaY}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="rgba(255, 255, 255, 0.75)"
                    fontSize={areaFontSize}
                    fontFamily="monospace"
                    className="pointer-events-none select-none"
                  >
                    {areaDisplay}
                  </text>
                )}
              </g>
            )
          })}

          {/* Structural Columns */}
          {columns.map((col, idx) => (
            <polygon
              key={col.id || idx}
              points={formatPoints(col.polygon)}
              fill="#f43f5e"
              stroke="#fb7185"
              strokeWidth={bounds.baseDim * 0.004}
              filter="url(#column-glow)"
            />
          ))}

          {/* Interactive Tooltip in Canvas */}
          {hoveredRoom && (
            <g transform={`translate(${bounds.minX + bounds.baseDim * 0.03}, ${bounds.minY + bounds.height - bounds.baseDim * 0.08})`}>
              <rect
                width={Math.min(bounds.width * 0.5, bounds.baseDim * 0.45)}
                height={bounds.baseDim * 0.055}
                rx={bounds.baseDim * 0.008}
                fill="rgba(15, 23, 42, 0.92)"
                stroke="rgba(56, 189, 248, 0.5)"
                strokeWidth={bounds.baseDim * 0.003}
              />
              <text
                x={bounds.baseDim * 0.015}
                y={bounds.baseDim * 0.035}
                fill="#38bdf8"
                fontSize={bounds.baseDim * 0.02}
                fontFamily="monospace"
                fontWeight="bold"
              >
                {hoveredRoom.name || hoveredRoom.id} • {hoveredRoom.polygon?.length || 0} vertices
              </text>
            </g>
          )}
        </svg>

        {/* Compass Rose Widget in Top-Right */}
        <div className="absolute top-4 right-4 p-2.5 rounded-xl bg-slate-900/90 border border-border/50 backdrop-blur shadow-lg flex flex-col items-center select-none">
          <div className="text-[10px] font-bold text-red-500 font-mono tracking-tighter">▲ N</div>
          <div className="w-5 h-5 relative flex items-center justify-center my-0.5">
            <div className="w-0.5 h-full bg-border" />
            <div className="h-0.5 w-full bg-border absolute" />
            <div className="w-2.5 h-2.5 rounded-full border border-primary/50 absolute" />
          </div>
          <div className="text-[9px] font-mono text-muted-foreground">{landInfo?.orientation || 'NORTH'}</div>
        </div>
      </div>

      {/* Legend & Room Pills */}
      {!hideLegend && (
        <div className="p-3 bg-card/60 border-t border-border/40 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-semibold text-muted-foreground mr-1">Rooms:</span>
          {rooms.map((room, idx) => {
            const color = getRoomColor(room.type, room.name)
            const isTargetHighlight = highlightRoomId && (room.id === highlightRoomId || room.name?.toLowerCase().includes(highlightRoomId.toLowerCase()))
            return (
              <div
                key={room.id || idx}
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border transition-colors cursor-pointer ${
                  isTargetHighlight
                    ? 'ring-2 ring-red-500 border-red-500 bg-red-500/20'
                    : (hoveredRoom?.id === room.id ? 'border-primary ring-2 ring-primary/20' : 'border-border/50')
                }`}
                style={{ backgroundColor: isTargetHighlight ? undefined : color.fill }}
                onMouseEnter={() => setHoveredRoom(room)}
                onMouseLeave={() => setHoveredRoom(null)}
              >
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: isTargetHighlight ? highlightColor : color.stroke }} />
                <span style={{ color: isTargetHighlight ? '#fff' : color.text }}>{room.name || room.type}</span>
              </div>
            )
          })}

          {columns.length > 0 && (
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border border-red-500/30 bg-red-500/10 text-red-400 ml-auto">
              <span className="w-2 h-2 rounded-full bg-red-500" />
              <span>Columns ({columns.length})</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
