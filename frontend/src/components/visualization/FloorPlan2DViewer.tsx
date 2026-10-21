"use client"
import React, { useMemo, useState, useEffect } from 'react'
import { Badge } from '@/components/ui/badge'
import { Compass, Maximize2, Layers, CheckCircle2, Grid3X3 } from 'lucide-react'

interface Room {
  id: string;
  name?: string;
  type?: string;
  polygon: [number, number][];
  dimensionText?: string;
  dimensions?: { width?: number; height?: number };
}

interface StructuralElement {
  id: string;
  type?: string;
  polygon: [number, number][];
}

export interface DoorElement {
  id: string;
  name?: string;
  type?: string;
  center?: [number, number];
  position?: [number, number];
  width?: number;
  is_main_entrance?: boolean;
  orientation?: string;
}

export interface WindowElement {
  id: string;
  name?: string;
  center?: [number, number];
  position?: [number, number];
  width?: number;
  orientation?: string;
}

export interface PlanMarker {
  id: string;
  label: string; // e.g. "01", "02", "03"
  roomId?: string;
  x?: number;
  y?: number;
  type?: 'correction' | 'attention' | 'good';
  tooltip?: string;
}

interface FloorPlan2DViewerProps {
  floorPlan?: {
    rooms?: Room[];
    structural_elements?: StructuralElement[];
    doors?: DoorElement[];
    windows?: WindowElement[];
    units?: string;
    dimensions?: { width?: number; height?: number };
    coordinate_system?: any;
  };
  landInfo?: {
    orientation?: string;
    road_facing?: string;
    area_sqft?: number;
    boundary_points?: [number, number][];
  };
  rectificationResult?: any;
  highlightRoomId?: string | null;
  rectifiedRoomIds?: string[];
  highlightColor?: string;
  dimOthers?: boolean;
  showVastuGridDefault?: boolean;
  hideLegend?: boolean;
  hideTopBar?: boolean;
  compassPosition?: 'top-left' | 'top-right';
  compactTopBar?: boolean;
  cadStyle?: boolean;
  outerDimensions?: { top?: string; right?: string };
  markers?: PlanMarker[];
  onMarkerClick?: (marker: PlanMarker) => void;
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
  rectifiedRoomIds = [],
  highlightColor = '#ef4444',
  dimOthers = false,
  showVastuGridDefault = false,
  hideLegend = false,
  hideTopBar = false,
  compassPosition = 'top-right',
  compactTopBar = false,
  cadStyle = false,
  outerDimensions,
  markers = [],
  onMarkerClick,
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
  const rawDoors = useMemo(() => ((floorPlan as any)?.doors as DoorElement[]) || [], [floorPlan])
  const rawWindows = useMemo(() => ((floorPlan as any)?.windows as WindowElement[]) || [], [floorPlan])

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

    const isCad = cadStyle || Boolean(outerDimensions)
    const padLeft = isCad ? rawW * 0.08 : rawW * 0.06
    const padRight = isCad ? rawW * 0.16 : rawW * 0.06
    const padTop = isCad ? rawH * 0.14 : rawH * 0.06
    const padBottom = isCad ? rawH * 0.08 : rawH * 0.06

    return {
      minX: minX - padLeft,
      minY: minY - padTop,
      maxX: maxX + padRight,
      maxY: maxY + padBottom,
      width: rawW + padLeft + padRight,
      height: rawH + padTop + padBottom,
      rawMinX: minX,
      rawMaxX: maxX,
      rawMinY: minY,
      rawMaxY: maxY,
      rawWidth: rawW,
      rawHeight: rawH,
      baseDim,
      padTop,
      padRight,
    }
  }, [rooms, columns, boundary, cadStyle, outerDimensions])

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

  // Nearest wall orientation finder
  const getNearestWallOrientation = (cx: number, cy: number, defaultOrient?: string) => {
    if (defaultOrient === 'horizontal' || defaultOrient === 'vertical') return defaultOrient
    let bestDist = Infinity
    let isHoriz = true
    rooms.forEach(r => {
      const poly = r.polygon
      if (!poly || poly.length < 2) return
      for (let i = 0; i < poly.length; i++) {
        const p1 = poly[i]
        const p2 = poly[(i + 1) % poly.length]
        const l2 = (p2[0] - p1[0]) * (p2[0] - p1[0]) + (p2[1] - p1[1]) * (p2[1] - p1[1])
        if (l2 === 0) continue
        let t = ((cx - p1[0]) * (p2[0] - p1[0]) + (cy - p1[1]) * (p2[1] - p1[1])) / l2
        t = Math.max(0, Math.min(1, t))
        const dist = Math.hypot(cx - (p1[0] + t * (p2[0] - p1[0])), cy - (p1[1] + t * (p2[1] - p1[1])))
        if (dist < bestDist) {
          bestDist = dist
          isHoriz = Math.abs(p2[0] - p1[0]) >= Math.abs(p2[1] - p1[1])
        }
      }
    })
    return isHoriz ? 'horizontal' : 'vertical'
  }

  // Derive doors if not explicitly provided
  const effectiveDoors = useMemo<DoorElement[]>(() => {
    if (rawDoors.length > 0) return rawDoors
    if (rooms.length === 0) return []

    const generated: DoorElement[] = []
    let doorIdx = 1

    // Detect shared edges between adjacent rooms
    for (let i = 0; i < rooms.length; i++) {
      for (let j = i + 1; j < rooms.length; j++) {
        const polyA = rooms[i].polygon
        const polyB = rooms[j].polygon
        if (!polyA || !polyB) continue

        for (let a = 0; a < polyA.length; a++) {
          const pa1 = polyA[a]
          const pa2 = polyA[(a + 1) % polyA.length]

          for (let b = 0; b < polyB.length; b++) {
            const pb1 = polyB[b]
            const pb2 = polyB[(b + 1) % polyB.length]

            // Check horizontal shared edge
            if (
              Math.abs(pa1[1] - pa2[1]) < 0.25 &&
              Math.abs(pb1[1] - pb2[1]) < 0.25 &&
              Math.abs(pa1[1] - pb1[1]) < 0.25
            ) {
              const overlapMin = Math.max(Math.min(pa1[0], pa2[0]), Math.min(pb1[0], pb2[0]))
              const overlapMax = Math.min(Math.max(pa1[0], pa2[0]), Math.max(pb1[0], pb2[0]))

              if (overlapMax - overlapMin >= 3.0) {
                const midX = (overlapMin + overlapMax) / 2
                generated.push({
                  id: `auto-door-${doorIdx++}`,
                  name: `Door`,
                  type: 'single_swing',
                  center: [midX, pa1[1]],
                  width: 3.0,
                  orientation: 'horizontal',
                })
              }
            }
            // Check vertical shared edge
            else if (
              Math.abs(pa1[0] - pa2[0]) < 0.25 &&
              Math.abs(pb1[0] - pb2[0]) < 0.25 &&
              Math.abs(pa1[0] - pb1[0]) < 0.25
            ) {
              const overlapMin = Math.max(Math.min(pa1[1], pa2[1]), Math.min(pb1[1], pb2[1]))
              const overlapMax = Math.min(Math.max(pa1[1], pa2[1]), Math.max(pb1[1], pb2[1]))

              if (overlapMax - overlapMin >= 3.0) {
                const midY = (overlapMin + overlapMax) / 2
                generated.push({
                  id: `auto-door-${doorIdx++}`,
                  name: `Door`,
                  type: 'single_swing',
                  center: [pa1[0], midY],
                  width: 3.0,
                  orientation: 'vertical',
                })
              }
            }
          }
        }
      }
    }

    // Add Main Entrance Door on front exterior wall if no main entrance
    if (!generated.some(d => d.is_main_entrance)) {
      const livingRoom = rooms.find(r => (r.type || r.name || '').toLowerCase().includes('verandah')) ||
                         rooms.find(r => (r.type || r.name || '').toLowerCase().includes('living')) ||
                         rooms[0]
      if (livingRoom) {
        const bbox = getPolygonBBox(livingRoom.polygon)
        generated.unshift({
          id: 'auto-door-main',
          name: 'MAIN ENTRANCE',
          type: 'single_swing',
          center: [bbox.cx, bbox.maxY],
          width: 3.5,
          is_main_entrance: true,
          orientation: 'horizontal',
        })
      }
    }

    return generated
  }, [rawDoors, rooms])

  // Derive windows if not explicitly provided
  const effectiveWindows = useMemo<WindowElement[]>(() => {
    if (rawWindows.length > 0) return rawWindows
    if (rooms.length === 0) return []

    const generated: WindowElement[] = []
    let winIdx = 1

    rooms.forEach(room => {
      const poly = room.polygon
      if (!poly || poly.length < 3) return

      for (let i = 0; i < poly.length; i++) {
        const p1 = poly[i]
        const p2 = poly[(i + 1) % poly.length]
        const len = Math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if (len < 5.0) continue

        const midX = (p1[0] + p2[0]) / 2
        const midY = (p1[1] + p2[1]) / 2

        const isNearBoundary = (
          Math.abs(midX - bounds.rawMinX) < 1.0 ||
          Math.abs(midX - bounds.rawMaxX) < 1.0 ||
          Math.abs(midY - bounds.rawMinY) < 1.0 ||
          Math.abs(midY - bounds.rawMaxY) < 1.0
        )

        if (isNearBoundary) {
          generated.push({
            id: `auto-win-${winIdx++}`,
            name: `${room.name || 'Room'} Window`,
            center: [midX, midY],
            width: Math.min(4.0, len * 0.5),
            orientation: Math.abs(p2[0] - p1[0]) >= Math.abs(p2[1] - p1[1]) ? 'horizontal' : 'vertical',
          })
        }
      }
    })

    return generated
  }, [rawWindows, rooms, bounds])

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
    <div className="flex flex-col w-full h-full bg-white border border-slate-300 rounded-2xl overflow-hidden shadow-lg">
      {/* Top Status Bar */}
      {!hideTopBar && (
        <div className="flex items-center justify-between px-3.5 py-2.5 bg-slate-50 border-b border-slate-200 text-xs">
          <div className="flex items-center gap-2 min-w-0">
            {!compactTopBar ? (
              <Badge variant="outline" className="gap-1.5 py-0.5 font-bold border-slate-300 text-slate-900 bg-white shadow-xs shrink-0">
                <Layers className="w-3.5 h-3.5 text-primary" /> Architectural CAD Plan
              </Badge>
            ) : (
              <div className="flex items-center gap-1.5 text-slate-900 font-bold text-xs shrink-0">
                <Layers className="w-3.5 h-3.5 text-primary" />
                <span>Architectural Plan</span>
              </div>
            )}
            <span className="text-slate-600 font-medium text-[11px] whitespace-nowrap">
              {rooms.length} Rooms
              {columns.length > 0 && ` • ${columns.length} Cols`}
              {effectiveDoors.length > 0 && ` • ${effectiveDoors.length} Doors`}
              {effectiveWindows.length > 0 && ` • ${effectiveWindows.length} Windows`}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setShowVastuGrid(!showVastuGrid)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors border shrink-0 cursor-pointer ${
                showVastuGrid
                  ? 'bg-amber-100 text-amber-900 border-amber-300 ring-1 ring-amber-300'
                  : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
              }`}
            >
              <Grid3X3 className="w-3.5 h-3.5 text-amber-600" />
              <span className="whitespace-nowrap">9×9 Vastu Grid</span>
            </button>

            <div className="flex items-center gap-1.5 px-2.5 py-1 bg-white border border-slate-300 rounded-md text-slate-800 text-[11px] shrink-0 whitespace-nowrap font-medium">
              <Compass className="w-3.5 h-3.5 text-primary shrink-0" />
              <span>Orientation: <strong>{landInfo?.orientation || 'North'}</strong></span>
            </div>
          </div>
        </div>
      )}

      {/* Main SVG Architectural Plan Canvas (White Drawing Sheet) */}
      <div className="relative w-full h-full flex-1 p-3 sm:p-6 flex items-center justify-center overflow-hidden min-h-[380px] bg-white">
        <svg
          id="architectural-plan-svg"
          xmlns="http://www.w3.org/2000/svg"
          viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
          className="w-full h-full select-none"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Architectural Drawing Sheet Grid (faint subtle drafting guidelines) */}
            <pattern
              id="drafting-grid"
              width={bounds.width / 24}
              height={bounds.height / 24}
              patternUnits="userSpaceOnUse"
            >
              <path
                d={`M ${bounds.width / 24} 0 L 0 0 0 ${bounds.height / 24}`}
                fill="none"
                stroke="rgba(0, 0, 0, 0.02)"
                strokeWidth="0.5"
              />
            </pattern>
            {/* Room Highlight Glow Filter */}
            <filter id="room-highlight-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="2.0" floodColor={highlightColor} floodOpacity="0.4" />
            </filter>
            {/* Rectified Room Glow Filter */}
            <filter id="rectified-room-glow" x="-25%" y="-25%" width="150%" height="150%">
              <feDropShadow dx="0" dy="0" stdDeviation="2.0" floodColor="#059669" floodOpacity="0.3" />
            </filter>
          </defs>

          {/* Clean Pure White Architectural Paper Sheet */}
          <rect
            x={bounds.minX}
            y={bounds.minY}
            width={bounds.width}
            height={bounds.height}
            fill="#ffffff"
          />
          <rect
            x={bounds.minX}
            y={bounds.minY}
            width={bounds.width}
            height={bounds.height}
            fill="url(#drafting-grid)"
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

            const isRectified = Boolean(
              rectifiedRoomIds && rectifiedRoomIds.length > 0 && (
                rectifiedRoomIds.includes(room.id) ||
                rectifiedRoomIds.includes((room.name || '').toLowerCase()) ||
                rectifiedRoomIds.some(id => (room.id || '').toLowerCase().includes(id.toLowerCase()))
              )
            )

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
                {/* Room Geometry - Solid Black Walls on Pure White Background (matching Real Architectural Blueprint) */}
                <polygon
                  points={formatPoints(room.polygon)}
                  fill={
                    isRectified
                      ? 'rgba(16, 185, 129, 0.12)'
                      : isTargetHighlight
                        ? 'rgba(239, 68, 68, 0.12)'
                        : (isHovered ? 'rgba(241, 245, 249, 0.9)' : '#ffffff')
                  }
                  stroke={
                    isRectified
                      ? '#059669'
                      : isTargetHighlight 
                        ? highlightColor 
                        : '#000000'
                  }
                  strokeWidth={
                    isRectified
                      ? bounds.baseDim * 0.016
                      : bounds.baseDim * 0.016
                  }
                  strokeLinejoin="miter"
                  strokeLinecap="square"
                  className="transition-all"
                />

                {/* Room Name Label (Solid Black Architectural Typography) */}
                <text
                  x={cx}
                  y={nameY}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#000000"
                  fontSize={fontSize}
                  fontWeight="700"
                  letterSpacing="0.04em"
                  fontFamily="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                  className="pointer-events-none select-none uppercase"
                >
                  {room.name || room.type || `Room ${idx + 1}`}
                </text>

                {/* Area / Dimension Tag (Under Room Name) */}
                {(room.dimensionText || area > 0) && (
                  <text
                    x={cx}
                    y={areaY}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="#334155"
                    fontSize={areaFontSize}
                    fontWeight="600"
                    fontFamily="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                    className="pointer-events-none select-none"
                  >
                    {room.dimensionText || areaDisplay}
                  </text>
                )}

                {/* Rectified Badge / Architectural Revision Stamp */}
                {isRectified && (
                  <g transform={`translate(${cx}, ${areaY + areaFontSize * 1.45})`} className="pointer-events-none select-none">
                    <rect
                      x={-fontSize * 2.8}
                      y={-areaFontSize * 0.7}
                      width={fontSize * 5.6}
                      height={areaFontSize * 1.4}
                      rx={3}
                      fill="#ecfdf5"
                      stroke="#059669"
                      strokeWidth={1}
                    />
                    <text
                      x={0}
                      y={0}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill="#047857"
                      fontSize={areaFontSize * 0.8}
                      fontWeight="800"
                      fontFamily="system-ui, sans-serif"
                    >
                      ★ RECTIFIED
                    </text>
                  </g>
                )}
              </g>
            )
          })}

          {/* Architectural Windows (Double/Triple Line CAD Symbols on White Cutout Mask) */}
          {effectiveWindows.map((win, wIdx) => {
            const center = win.center || win.position
            if (!center || center.length < 2) return null
            const [cx, cy] = center
            const w = win.width || 4.0
            const orient = getNearestWallOrientation(cx, cy, win.orientation)
            const isHoriz = orient === 'horizontal'
            const halfW = w / 2
            const svgCy = toSvgY(cy)
            const offset = bounds.baseDim * 0.004

            if (isHoriz) {
              const x1 = cx - halfW
              const x2 = cx + halfW
              return (
                <g key={win.id || wIdx} className="architectural-window pointer-events-none select-none">
                  {/* Clean Wall Opening Cutout (White mask that cuts through the black wall) */}
                  <line x1={x1} y1={svgCy} x2={x2} y2={svgCy} stroke="#ffffff" strokeWidth={bounds.baseDim * 0.024} />
                  {/* Outer Wall Face Line */}
                  <line x1={x1} y1={svgCy - offset} x2={x2} y2={svgCy - offset} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
                  {/* Center Glass Pane */}
                  <line x1={x1} y1={svgCy} x2={x2} y2={svgCy} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  {/* Inner Wall Face Line */}
                  <line x1={x1} y1={svgCy + offset} x2={x2} y2={svgCy + offset} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
                  {/* Window Jambs / Wall Stops on both sides */}
                  <line x1={x1} y1={svgCy - offset * 1.5} x2={x1} y2={svgCy + offset * 1.5} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={x2} y1={svgCy - offset * 1.5} x2={x2} y2={svgCy + offset * 1.5} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                </g>
              )
            } else {
              const y1 = cy - halfW
              const y2 = cy + halfW
              const svgY1 = toSvgY(y1)
              const svgY2 = toSvgY(y2)
              return (
                <g key={win.id || wIdx} className="architectural-window pointer-events-none select-none">
                  {/* Clean Wall Opening Cutout */}
                  <line x1={cx} y1={svgY1} x2={cx} y2={svgY2} stroke="#ffffff" strokeWidth={bounds.baseDim * 0.024} />
                  {/* Outer Frame Line */}
                  <line x1={cx - offset} y1={svgY1} x2={cx - offset} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
                  {/* Center Glass Pane */}
                  <line x1={cx} y1={svgY1} x2={cx} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  {/* Inner Frame Line */}
                  <line x1={cx + offset} y1={svgY1} x2={cx + offset} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
                  {/* Window Jambs */}
                  <line x1={cx - offset * 1.5} y1={svgY1} x2={cx + offset * 1.5} y2={svgY1} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={cx - offset * 1.5} y1={svgY2} x2={cx + offset * 1.5} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                </g>
              )
            }
          })}

          {/* Architectural Doors (Quarter-circle Swing Arc + Leaf in Black Ink on White Cutout Mask) */}
          {effectiveDoors.map((door, dIdx) => {
            const center = door.center || door.position
            if (!center || center.length < 2) return null
            const [cx, cy] = center
            const w = door.width || 3.0
            const orient = getNearestWallOrientation(cx, cy, door.orientation)
            const isHoriz = orient === 'horizontal'
            const halfW = w / 2
            const svgCy = toSvgY(cy)

            if (isHoriz) {
              const x1 = cx - halfW
              const x2 = cx + halfW
              const hingeX = x1
              const hingeY = svgCy
              const leafEndX = x1
              const leafEndY = svgCy - w * (isYAxisUp ? -1 : 1)
              const wallPointX = x2
              const wallPointY = svgCy
              const arcD = `M ${wallPointX} ${wallPointY} A ${w} ${w} 0 0 ${isYAxisUp ? 1 : 0} ${leafEndX} ${leafEndY}`

              return (
                <g key={door.id || dIdx} className="architectural-door pointer-events-none select-none">
                  {/* Clean Wall Opening Cutout (White mask that cuts through the black wall) */}
                  <line
                    x1={x1}
                    y1={svgCy}
                    x2={x2}
                    y2={svgCy}
                    stroke="#ffffff"
                    strokeWidth={bounds.baseDim * 0.024}
                  />
                  {/* Door Swing Arc (Fine black drafting arc) */}
                  <path
                    d={arcD}
                    fill="none"
                    stroke="#000000"
                    strokeWidth={bounds.baseDim * 0.002}
                  />
                  {/* Door Leaf (Solid black line) */}
                  <line
                    x1={hingeX}
                    y1={hingeY}
                    x2={leafEndX}
                    y2={leafEndY}
                    stroke="#000000"
                    strokeWidth={bounds.baseDim * 0.004}
                  />
                  {/* Door Jambs (Wall stops on both sides) */}
                  <line x1={x1} y1={svgCy - bounds.baseDim * 0.008} x2={x1} y2={svgCy + bounds.baseDim * 0.008} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={x2} y1={svgCy - bounds.baseDim * 0.008} x2={x2} y2={svgCy + bounds.baseDim * 0.008} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  {/* Main Entrance Tag */}
                  {door.is_main_entrance && (
                    <g transform={`translate(${cx}, ${svgCy + (isYAxisUp ? -bounds.baseDim * 0.05 : bounds.baseDim * 0.05)})`}>
                      <rect
                        x={-bounds.baseDim * 0.09}
                        y={-bounds.baseDim * 0.016}
                        width={bounds.baseDim * 0.18}
                        height={bounds.baseDim * 0.032}
                        rx={3}
                        fill="#000000"
                        stroke="#000000"
                      />
                      <text
                        x={0}
                        y={0}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill="#ffffff"
                        fontSize={bounds.baseDim * 0.014}
                        fontWeight="bold"
                        fontFamily="system-ui, sans-serif"
                      >
                        ▲ MAIN ENTRANCE
                      </text>
                    </g>
                  )}
                </g>
              )
            } else {
              const y1 = cy - halfW
              const y2 = cy + halfW
              const svgY1 = toSvgY(y1)
              const svgY2 = toSvgY(y2)
              const svgHingeY = Math.max(svgY1, svgY2)
              const svgWallPointY = Math.min(svgY1, svgY2)
              const hingeX = cx
              const leafEndX = cx + w
              const leafEndY = svgHingeY
              const arcD = `M ${cx} ${svgWallPointY} A ${w} ${w} 0 0 1 ${leafEndX} ${leafEndY}`

              return (
                <g key={door.id || dIdx} className="architectural-door pointer-events-none select-none">
                  {/* Clean Wall Opening Cutout */}
                  <line
                    x1={cx}
                    y1={svgY1}
                    x2={cx}
                    y2={svgY2}
                    stroke="#ffffff"
                    strokeWidth={bounds.baseDim * 0.024}
                  />
                  {/* Door Swing Arc */}
                  <path
                    d={arcD}
                    fill="none"
                    stroke="#000000"
                    strokeWidth={bounds.baseDim * 0.002}
                  />
                  {/* Door Leaf */}
                  <line
                    x1={hingeX}
                    y1={svgHingeY}
                    x2={leafEndX}
                    y2={leafEndY}
                    stroke="#000000"
                    strokeWidth={bounds.baseDim * 0.004}
                  />
                  {/* Door Jambs */}
                  <line x1={cx - bounds.baseDim * 0.008} y1={svgY1} x2={cx + bounds.baseDim * 0.008} y2={svgY1} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={cx - bounds.baseDim * 0.008} y1={svgY2} x2={cx + bounds.baseDim * 0.008} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                </g>
              )
            }
          })}

          {/* CAD Exterior Wall Double-Line Accent */}
          {cadStyle && (
            <rect
              x={bounds.rawMinX - bounds.baseDim * 0.008}
              y={bounds.rawMinY - bounds.baseDim * 0.008}
              width={bounds.rawWidth + bounds.baseDim * 0.016}
              height={bounds.rawHeight + bounds.baseDim * 0.016}
              fill="none"
              stroke="#000000"
              strokeWidth={bounds.baseDim * 0.003}
              className="pointer-events-none"
            />
          )}

          {/* Structural Columns - Solid Black Blocks */}
          {columns.map((col, idx) => (
            <polygon
              key={col.id || idx}
              points={formatPoints(col.polygon)}
              fill="#000000"
              stroke="#000000"
              strokeWidth={bounds.baseDim * 0.002}
            />
          ))}

          {/* CAD Exterior Dimension Lines (Crisp Black Architectural Drafting Ticks & Figures) */}
          {(cadStyle || outerDimensions) && (
            <g className="cad-dimension-lines pointer-events-none text-slate-900">
              {/* Top Dimension Line */}
              <line
                x1={bounds.rawMinX}
                y1={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.45}
                x2={bounds.rawMaxX}
                y2={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.45}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.0025}
              />
              {/* Top Dimension Extension Lines */}
              <line
                x1={bounds.rawMinX}
                y1={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.25}
                x2={bounds.rawMinX}
                y2={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.65}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.002}
              />
              <line
                x1={bounds.rawMaxX}
                y1={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.25}
                x2={bounds.rawMaxX}
                y2={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.65}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.002}
              />
              {/* Top 45° Architectural Slash Ticks */}
              <line
                x1={bounds.rawMinX - bounds.baseDim * 0.006}
                y1={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.45 + bounds.baseDim * 0.006}
                x2={bounds.rawMinX + bounds.baseDim * 0.006}
                y2={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.45 - bounds.baseDim * 0.006}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.0035}
              />
              <line
                x1={bounds.rawMaxX - bounds.baseDim * 0.006}
                y1={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.45 + bounds.baseDim * 0.006}
                x2={bounds.rawMaxX + bounds.baseDim * 0.006}
                y2={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.45 - bounds.baseDim * 0.006}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.0035}
              />
              <text
                x={(bounds.rawMinX + bounds.rawMaxX) / 2}
                y={bounds.minY + ((bounds as any).padTop || bounds.baseDim * 0.1) * 0.32}
                fill="#000000"
                fontSize={bounds.baseDim * 0.024}
                fontFamily="system-ui, -apple-system, sans-serif"
                textAnchor="middle"
                fontWeight="700"
              >
                {outerDimensions?.top || `${Math.round(bounds.rawWidth)}'-0"`}
              </text>

              {/* Right Dimension Line */}
              <line
                x1={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.45}
                y1={bounds.rawMinY}
                x2={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.45}
                y2={bounds.rawMaxY}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.0025}
              />
              {/* Right Dimension Extension Lines */}
              <line
                x1={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.25}
                y1={bounds.rawMinY}
                x2={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.65}
                y2={bounds.rawMinY}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.002}
              />
              <line
                x1={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.25}
                y1={bounds.rawMaxY}
                x2={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.65}
                y2={bounds.rawMaxY}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.002}
              />
              {/* Right 45° Architectural Slash Ticks */}
              <line
                x1={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.45 - bounds.baseDim * 0.006}
                y1={bounds.rawMinY + bounds.baseDim * 0.006}
                x2={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.45 + bounds.baseDim * 0.006}
                y2={bounds.rawMinY - bounds.baseDim * 0.006}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.0035}
              />
              <line
                x1={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.45 - bounds.baseDim * 0.006}
                y1={bounds.rawMaxY + bounds.baseDim * 0.006}
                x2={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.45 + bounds.baseDim * 0.006}
                y2={bounds.rawMaxY - bounds.baseDim * 0.006}
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.0035}
              />
              <text
                x={bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.62}
                y={(bounds.rawMinY + bounds.rawMaxY) / 2}
                fill="#000000"
                fontSize={bounds.baseDim * 0.024}
                fontFamily="system-ui, -apple-system, sans-serif"
                textAnchor="middle"
                fontWeight="700"
                transform={`rotate(90, ${bounds.rawMaxX + ((bounds as any).padRight || bounds.baseDim * 0.1) * 0.62}, ${(bounds.rawMinY + bounds.rawMaxY) / 2})`}
              >
                {outerDimensions?.right || `${Math.round(bounds.rawHeight)}'-0"`}
              </text>
            </g>
          )}

          {/* Vastu Issues & Attention Markers (Pins 01, 02, 03) */}
          {markers.map((marker, mIdx) => {
            let mx = marker.x
            let my = marker.y
            if (mx === undefined || my === undefined) {
              if (marker.roomId) {
                const targetRoom = rooms.find(
                  r => r.id === marker.roomId || r.name?.toLowerCase().includes(marker.roomId!.toLowerCase())
                )
                if (targetRoom) {
                  const bbox = getPolygonBBox(targetRoom.polygon)
                  mx = bbox.cx + (bbox.width * 0.22)
                  my = bbox.cy - (bbox.height * 0.22)
                }
              }
            }
            if (mx === undefined || my === undefined) return null

            const svgMy = toSvgY(my)
            const markerRadius = bounds.baseDim * 0.024
            const bg = marker.type === 'attention' ? '#f59e0b' : (marker.type === 'good' ? '#10b981' : '#ef4444')

            return (
              <g
                key={marker.id || mIdx}
                className="cursor-pointer transition-transform hover:scale-125"
                onClick={() => onMarkerClick?.(marker)}
              >
                {/* Outer halo */}
                <circle
                  cx={mx}
                  cy={svgMy}
                  r={markerRadius * 1.45}
                  fill={bg}
                  opacity={0.3}
                  className="animate-pulse"
                />
                {/* Marker Circle */}
                <circle
                  cx={mx}
                  cy={svgMy}
                  r={markerRadius}
                  fill={bg}
                  stroke="#ffffff"
                  strokeWidth={bounds.baseDim * 0.003}
                />
                {/* Marker Number Text (01, 02, etc.) */}
                <text
                  x={mx}
                  y={svgMy}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="#ffffff"
                  fontSize={markerRadius * 1.05}
                  fontFamily="monospace"
                  fontWeight="bold"
                  className="select-none pointer-events-none"
                >
                  {marker.label}
                </text>
              </g>
            )
          })}

          {/* Interactive Tooltip in Canvas */}
          {hoveredRoom && (
            <g transform={`translate(${bounds.minX + bounds.baseDim * 0.03}, ${bounds.minY + bounds.height - bounds.baseDim * 0.08})`}>
              <rect
                width={Math.min(bounds.width * 0.5, bounds.baseDim * 0.45)}
                height={bounds.baseDim * 0.055}
                rx={bounds.baseDim * 0.008}
                fill="#ffffff"
                stroke="#000000"
                strokeWidth={bounds.baseDim * 0.002}
                filter="drop-shadow(0 2px 4px rgba(0,0,0,0.1))"
              />
              <text
                x={bounds.baseDim * 0.015}
                y={bounds.baseDim * 0.035}
                fill="#000000"
                fontSize={bounds.baseDim * 0.02}
                fontFamily="system-ui, sans-serif"
                fontWeight="700"
              >
                {hoveredRoom.name || hoveredRoom.id} • {hoveredRoom.polygon?.length || 0} vertices
              </text>
            </g>
          )}
        </svg>

        {/* Compass Rose Widget (Architectural Drafting Style) */}
        <div className={`absolute top-4 ${compassPosition === 'top-left' ? 'left-4' : 'right-4'} p-2 rounded-xl bg-white/95 border border-slate-300 backdrop-blur shadow-md flex flex-col items-center select-none pointer-events-none`}>
          <div className="w-10 h-10 relative flex items-center justify-center">
            <svg viewBox="0 0 40 40" className="w-full h-full">
              <circle cx="20" cy="20" r="17" fill="none" stroke="#cbd5e1" strokeWidth="0.8" />
              <line x1="20" y1="5" x2="20" y2="35" stroke="#94a3b8" strokeWidth="0.5" />
              <line x1="5" y1="20" x2="35" y2="20" stroke="#94a3b8" strokeWidth="0.5" />
              <polygon points="20,6 23,20 20,18" fill="#ef4444" />
              <polygon points="20,6 17,20 20,18" fill="#b91c1c" />
              <polygon points="20,34 23,20 20,22" fill="#000000" />
              <polygon points="20,34 17,20 20,22" fill="#475569" />
              <text x="20" y="4" textAnchor="middle" fill="#ef4444" fontSize="4.5" fontWeight="bold">N</text>
              <text x="37" y="21.5" textAnchor="middle" fill="#475569" fontSize="3.5" fontWeight="600">E</text>
              <text x="20" y="39" textAnchor="middle" fill="#475569" fontSize="3.5" fontWeight="600">S</text>
              <text x="3" y="21.5" textAnchor="middle" fill="#475569" fontSize="3.5" fontWeight="600">W</text>
            </svg>
          </div>
        </div>
      </div>
    </div>
  )
}
