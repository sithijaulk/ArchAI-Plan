"use client"
import React, { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Compass, Sparkles, Layers, ArrowRight, CheckCircle2, AlertTriangle, Eye, RotateCcw } from 'lucide-react'

interface Room {
  id: string;
  name?: string;
  type?: string;
  polygon: [number, number][];
  dimensionText?: string;
}

interface StructuralElement {
  id: string;
  type?: string;
  polygon: [number, number][];
}

interface DoorElement {
  id: string;
  name?: string;
  center?: [number, number];
  position?: [number, number];
  width?: number;
  orientation?: 'horizontal' | 'vertical' | string;
  swing?: 'inward' | 'outward' | string;
}

interface WindowElement {
  id: string;
  name?: string;
  center?: [number, number];
  position?: [number, number];
  width?: number;
  orientation?: 'horizontal' | 'vertical' | string;
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

interface FloorPlanDiffViewerProps {
  baselineFloorPlan?: {
    rooms?: Room[];
    structural_elements?: StructuralElement[];
    doors?: DoorElement[];
    windows?: WindowElement[];
    units?: string;
    coordinate_system?: {
      origin?: string;
      y_axis?: 'up' | 'down';
    };
  };
  rectifiedFloorPlan?: {
    rooms?: Room[];
    structural_elements?: StructuralElement[];
    doors?: DoorElement[];
    windows?: WindowElement[];
    units?: string;
    coordinate_system?: {
      origin?: string;
      y_axis?: 'up' | 'down';
    };
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

export function FloorPlanDiffViewer({
  baselineFloorPlan,
  rectifiedFloorPlan,
  landInfo,
  modifications = [],
  selectedRoomId,
  baselineScore = 42,
  rectifiedScore = 88,
  onSelectRoom,
}: FloorPlanDiffViewerProps) {
  // View mode: 'after' (AI Rectified) | 'before' (Baseline) | 'overlay' (Diff)
  const [viewMode, setViewMode] = useState<'after' | 'before' | 'overlay'>('after')
  const [hoveredRoomId, setHoveredRoomId] = useState<string | null>(null)

  const activePlan = viewMode === 'before' ? baselineFloorPlan : rectifiedFloorPlan
  const rooms = useMemo(() => activePlan?.rooms || [], [activePlan])
  const columns = useMemo(() => activePlan?.structural_elements || [], [activePlan])
  const baselineRooms = useMemo(() => baselineFloorPlan?.rooms || [], [baselineFloorPlan])
  const rectifiedRooms = useMemo(() => rectifiedFloorPlan?.rooms || [], [rectifiedFloorPlan])
  const boundary = useMemo(() => landInfo?.boundary_points || [], [landInfo])

  const rawDoors = useMemo(() => (activePlan as any)?.doors || [], [activePlan])
  const rawWindows = useMemo(() => (activePlan as any)?.windows || [], [activePlan])

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
        cx: 50, cy: 50, baseDim: 100
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

    const padX = baseDim * 0.12
    const padTop = baseDim * 0.14
    const padBottom = baseDim * 0.10

    return {
      minX: minX - padX,
      minY: minY - padTop,
      maxX: maxX + padX,
      maxY: maxY + padBottom,
      width: rawW + padX * 2,
      height: rawH + padTop + padBottom,
      rawMinX: minX,
      rawMaxX: maxX,
      rawMinY: minY,
      rawMaxY: maxY,
      rawWidth: rawW,
      rawHeight: rawH,
      cx: (minX + maxX) / 2,
      cy: (minY + maxY) / 2,
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

  // Derive doors if not provided
  const effectiveDoors = useMemo<DoorElement[]>(() => {
    if (rawDoors.length > 0) return rawDoors
    if (rooms.length === 0) return []
    const generated: DoorElement[] = []
    let doorIdx = 1

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
                  id: `diff-door-${doorIdx++}`,
                  name: `Door`,
                  center: [midX, pa1[1]],
                  width: Math.min(3.2, (overlapMax - overlapMin) * 0.7),
                  orientation: 'horizontal',
                })
              }
            } else if (
              Math.abs(pa1[0] - pa2[0]) < 0.25 &&
              Math.abs(pb1[0] - pb2[0]) < 0.25 &&
              Math.abs(pa1[0] - pb1[0]) < 0.25
            ) {
              const overlapMin = Math.max(Math.min(pa1[1], pa2[1]), Math.min(pb1[1], pb2[1]))
              const overlapMax = Math.min(Math.max(pa1[1], pa2[1]), Math.max(pb1[1], pb2[1]))
              if (overlapMax - overlapMin >= 3.0) {
                const midY = (overlapMin + overlapMax) / 2
                generated.push({
                  id: `diff-door-${doorIdx++}`,
                  name: `Door`,
                  center: [pa1[0], midY],
                  width: Math.min(3.2, (overlapMax - overlapMin) * 0.7),
                  orientation: 'vertical',
                })
              }
            }
          }
        }
      }
    }
    return generated
  }, [rawDoors, rooms])

  // Derive windows if not provided
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
        const edgeLength = Math.hypot(p2[0] - p1[0], p2[1] - p1[1])

        const isExterior =
          (Math.abs(p1[1] - bounds.rawMinY) < 0.5 && Math.abs(p2[1] - bounds.rawMinY) < 0.5) ||
          (Math.abs(p1[1] - bounds.rawMaxY) < 0.5 && Math.abs(p2[1] - bounds.rawMaxY) < 0.5) ||
          (Math.abs(p1[0] - bounds.rawMinX) < 0.5 && Math.abs(p2[0] - bounds.rawMinX) < 0.5) ||
          (Math.abs(p1[0] - bounds.rawMaxX) < 0.5 && Math.abs(p2[0] - bounds.rawMaxX) < 0.5)

        if (isExterior && edgeLength >= 4.0) {
          const midX = (p1[0] + p2[0]) / 2
          const midY = (p1[1] + p2[1]) / 2
          const isHoriz = Math.abs(p1[1] - p2[1]) < 0.25
          generated.push({
            id: `diff-win-${winIdx++}`,
            name: `Window`,
            center: [midX, midY],
            width: Math.min(4.5, edgeLength * 0.4),
            orientation: isHoriz ? 'horizontal' : 'vertical',
          })
        }
      }
    })
    return generated
  }, [rawWindows, rooms, bounds])

  return (
    <div className="flex flex-col w-full h-full bg-white border border-slate-300 rounded-2xl overflow-hidden shadow-lg select-none">
      {/* Top Header / Mode Switch Bar (Clean Architectural Style) */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 px-4 py-2.5 bg-slate-50 border-b border-slate-200 text-xs">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="gap-1.5 py-0.5 font-bold border-slate-300 text-slate-900 bg-white shadow-xs">
            <Layers className="w-3.5 h-3.5 text-primary" /> Architectural Spatial Diff
          </Badge>
          <span className="text-slate-600 font-medium text-[11px] hidden sm:inline">
            {rooms.length} Rooms • {effectiveDoors.length} Doors • {effectiveWindows.length} Windows
          </span>
        </div>

        {/* View Mode Selector */}
        <div className="flex items-center gap-1 bg-white p-1 rounded-lg border border-slate-300 shadow-xs">
          <button
            type="button"
            onClick={() => setViewMode('after')}
            className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all cursor-pointer ${
              viewMode === 'after'
                ? 'bg-emerald-600 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            Rectified ({rectifiedScore}%)
          </button>
          <button
            type="button"
            onClick={() => setViewMode('before')}
            className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all cursor-pointer ${
              viewMode === 'before'
                ? 'bg-rose-600 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            Baseline ({baselineScore}%)
          </button>
          <button
            type="button"
            onClick={() => setViewMode('overlay')}
            className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all cursor-pointer ${
              viewMode === 'overlay'
                ? 'bg-sky-600 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            Ghost Overlay
          </button>
        </div>
      </div>

      {/* Main Architectural Plan Canvas (Pure White Drawing Sheet) */}
      <div className="relative w-full aspect-[4/3] min-h-[440px] max-h-[620px] p-4 flex items-center justify-center overflow-hidden bg-white">
        <svg
          id="architectural-diff-svg"
          xmlns="http://www.w3.org/2000/svg"
          viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
          className="w-full h-full select-none"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Subtle drafting grid */}
            <pattern
              id="diff-drafting-grid"
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

            {/* Displacement Arrowhead */}
            <marker
              id="diff-arrow"
              viewBox="0 0 10 10"
              refX="6"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#059669" />
            </marker>
          </defs>

          {/* Pure White Background Sheet */}
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
            fill="url(#diff-drafting-grid)"
          />

          {/* Land / Plot Boundary */}
          {boundary.length >= 3 && (
            <polygon
              points={formatPoints(boundary)}
              fill="rgba(0, 0, 0, 0.01)"
              stroke="#94a3b8"
              strokeWidth={bounds.baseDim * 0.003}
              strokeDasharray="4,3"
            />
          )}

          {/* OVERLAY MODE: Ghost of previous Baseline plan (dashed rose walls) */}
          {viewMode === 'overlay' && baselineRooms.map((room, idx) => (
            <g key={`ghost-${room.id || idx}`} opacity="0.6">
              <polygon
                points={formatPoints(room.polygon)}
                fill="rgba(244, 63, 94, 0.08)"
                stroke="#e11d48"
                strokeWidth={bounds.baseDim * 0.008}
                strokeDasharray={`${bounds.baseDim * 0.012},${bounds.baseDim * 0.008}`}
              />
            </g>
          ))}

          {/* Render Active Plan Rooms (Solid Black Architectural Poché Walls) */}
          {rooms.map((room, idx) => {
            const rId = room.id.toLowerCase()
            const isModified = modifiedRoomIds.has(rId) || modifiedRoomIds.has((room.name || '').toLowerCase())
            const isHovered = hoveredRoomId === room.id
            const isSelected = selectedRoomId === room.id || (selectedRoomId && room.name?.toLowerCase().includes(selectedRoomId.toLowerCase()))

            const bbox = getPolygonBBox(room.polygon)
            const area = calculateArea(room.polygon)

            const rW = Math.max(bbox.width, bounds.baseDim * 0.05)
            const rH = Math.max(bbox.height, bounds.baseDim * 0.05)
            const charCount = Math.max((room.name || room.type || '').length, 4)

            const maxFontByW = (rW * 0.88) / (charCount * 0.55)
            const maxFontByH = rH * 0.24
            const idealFont = Math.min(bounds.baseDim * 0.026, maxFontByW, maxFontByH)
            const fontSize = Math.max(idealFont, bounds.baseDim * 0.009)

            const cx = bbox.cx
            const cy = toSvgY(bbox.cy)

            const tagText = isModified && (viewMode === 'after' || viewMode === 'overlay')
              ? '★ RECTIFIED'
              : (viewMode === 'before' && isModified ? '⚠ DEFECT' : '')

            const nameY = area > 0 ? cy - fontSize * 0.55 : cy
            const areaY = cy + fontSize * 0.75
            const areaFontSize = fontSize * 0.8

            // Determine display units
            const units = (activePlan as any)?.units?.toLowerCase() || ''
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

            return (
              <g
                key={room.id || idx}
                onMouseEnter={() => setHoveredRoomId(room.id)}
                onMouseLeave={() => setHoveredRoomId(null)}
                onClick={() => onSelectRoom?.(room.id)}
                className="cursor-pointer transition-all duration-200"
              >
                {/* Room Geometry - Solid Black Poché Walls on Pure White Paper */}
                <polygon
                  points={formatPoints(room.polygon)}
                  fill={
                    isSelected
                      ? 'rgba(16, 185, 129, 0.22)'
                      : (isModified && (viewMode === 'after' || viewMode === 'overlay')
                        ? 'rgba(16, 185, 129, 0.12)'
                        : (viewMode === 'before' && isModified
                          ? 'rgba(239, 68, 68, 0.10)'
                          : (isHovered ? 'rgba(241, 245, 249, 0.9)' : '#ffffff')))
                  }
                  stroke={
                    isSelected
                      ? '#059669'
                      : (isModified && (viewMode === 'after' || viewMode === 'overlay')
                        ? '#059669'
                        : (viewMode === 'before' && isModified
                          ? '#dc2626'
                          : '#000000'))
                  }
                  strokeWidth={bounds.baseDim * 0.016}
                  strokeLinejoin="miter"
                  strokeLinecap="square"
                />

                {/* Room Name Label (Solid Black Bold Architectural Typography) */}
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
                  {room.name || room.type}
                </text>

                {/* Area Tag */}
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

                {/* Subtitle / Rectification Tag Badge */}
                {tagText && (
                  <g transform={`translate(${cx}, ${areaY + areaFontSize * 1.45})`} className="pointer-events-none select-none">
                    <rect
                      x={-fontSize * 2.8}
                      y={-areaFontSize * 0.7}
                      width={fontSize * 5.6}
                      height={areaFontSize * 1.4}
                      rx={3}
                      fill={isModified && (viewMode === 'after' || viewMode === 'overlay') ? '#ecfdf5' : '#fff1f2'}
                      stroke={isModified && (viewMode === 'after' || viewMode === 'overlay') ? '#059669' : '#e11d48'}
                      strokeWidth={1}
                    />
                    <text
                      x={0}
                      y={0}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill={isModified && (viewMode === 'after' || viewMode === 'overlay') ? '#047857' : '#be123c'}
                      fontSize={areaFontSize * 0.8}
                      fontWeight="800"
                      fontFamily="system-ui, sans-serif"
                    >
                      {tagText}
                    </text>
                  </g>
                )}
              </g>
            )
          })}

          {/* Architectural Windows (White Cutout Mask + Glass Pane) */}
          {effectiveWindows.map((win, wIdx) => {
            const center = win.center || win.position
            if (!center || center.length < 2) return null
            const [cx, cy] = center
            const w = win.width || 4.0
            const isHoriz = win.orientation === 'horizontal'
            const halfW = w / 2
            const svgCy = toSvgY(cy)
            const offset = bounds.baseDim * 0.004

            if (isHoriz) {
              const x1 = cx - halfW
              const x2 = cx + halfW
              return (
                <g key={win.id || wIdx} className="architectural-window pointer-events-none select-none">
                  <line x1={x1} y1={svgCy} x2={x2} y2={svgCy} stroke="#ffffff" strokeWidth={bounds.baseDim * 0.024} />
                  <line x1={x1} y1={svgCy - offset} x2={x2} y2={svgCy - offset} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
                  <line x1={x1} y1={svgCy} x2={x2} y2={svgCy} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={x1} y1={svgCy + offset} x2={x2} y2={svgCy + offset} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
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
                  <line x1={cx} y1={svgY1} x2={cx} y2={svgY2} stroke="#ffffff" strokeWidth={bounds.baseDim * 0.024} />
                  <line x1={cx - offset} y1={svgY1} x2={cx - offset} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
                  <line x1={cx} y1={svgY1} x2={cx} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={cx + offset} y1={svgY1} x2={cx + offset} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0025} />
                  <line x1={cx - offset * 1.5} y1={svgY1} x2={cx + offset * 1.5} y2={svgY1} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={cx - offset * 1.5} y1={svgY2} x2={cx + offset * 1.5} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                </g>
              )
            }
          })}

          {/* Architectural Doors (White Cutout Mask + Solid Black Leaf & 90° Swing Arc) */}
          {effectiveDoors.map((door, dIdx) => {
            const center = door.center || door.position
            if (!center || center.length < 2) return null
            const [cx, cy] = center
            const w = door.width || 3.0
            const isHoriz = door.orientation === 'horizontal'
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
                  <line x1={x1} y1={svgCy} x2={x2} y2={svgCy} stroke="#ffffff" strokeWidth={bounds.baseDim * 0.024} />
                  <path d={arcD} fill="none" stroke="#000000" strokeWidth={bounds.baseDim * 0.002} />
                  <line x1={hingeX} y1={hingeY} x2={leafEndX} y2={leafEndY} stroke="#000000" strokeWidth={bounds.baseDim * 0.004} />
                  <line x1={x1} y1={svgCy - bounds.baseDim * 0.008} x2={x1} y2={svgCy + bounds.baseDim * 0.008} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={x2} y1={svgCy - bounds.baseDim * 0.008} x2={x2} y2={svgCy + bounds.baseDim * 0.008} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
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
                  <line x1={cx} y1={svgY1} x2={cx} y2={svgY2} stroke="#ffffff" strokeWidth={bounds.baseDim * 0.024} />
                  <path d={arcD} fill="none" stroke="#000000" strokeWidth={bounds.baseDim * 0.002} />
                  <line x1={hingeX} y1={svgHingeY} x2={leafEndX} y2={leafEndY} stroke="#000000" strokeWidth={bounds.baseDim * 0.004} />
                  <line x1={cx - bounds.baseDim * 0.008} y1={svgY1} x2={cx + bounds.baseDim * 0.008} y2={svgY1} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                  <line x1={cx - bounds.baseDim * 0.008} y1={svgY2} x2={cx + bounds.baseDim * 0.008} y2={svgY2} stroke="#000000" strokeWidth={bounds.baseDim * 0.0035} />
                </g>
              )
            }
          })}

          {/* OVERLAY MODE: Draw Animated Displacement Vectors */}
          {viewMode === 'overlay' && modifications.map((mod, i) => {
            if (!mod.previousCenter || !mod.newCenter) return null
            const [x1, y1] = mod.previousCenter
            const [x2, y2] = mod.newCenter
            return (
              <g key={`arrow-${i}`} className="displacement-vector pointer-events-none select-none">
                <line
                  x1={x1}
                  y1={toSvgY(y1)}
                  x2={x2}
                  y2={toSvgY(y2)}
                  stroke="#059669"
                  strokeWidth={bounds.baseDim * 0.006}
                  strokeDasharray={`${bounds.baseDim * 0.015},${bounds.baseDim * 0.01}`}
                  markerEnd="url(#diff-arrow)"
                />
                <circle cx={x1} cy={toSvgY(y1)} r={bounds.baseDim * 0.012} fill="#e11d48" />
                <circle cx={x2} cy={toSvgY(y2)} r={bounds.baseDim * 0.012} fill="#059669" />
              </g>
            )
          })}

        </svg>

        {/* Compass Widget */}
        <div className="absolute top-4 right-4 p-2 rounded-xl bg-white/95 border border-slate-300 backdrop-blur shadow-md flex flex-col items-center select-none pointer-events-none">
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
