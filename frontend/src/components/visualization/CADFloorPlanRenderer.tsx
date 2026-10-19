"use client"

import React, { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  Compass, 
  ZoomIn, 
  ZoomOut, 
  RotateCcw, 
  Sun, 
  Moon, 
  Layers,
  Sparkles
} from 'lucide-react'

export interface CADRoom {
  id: string
  name?: string
  type?: string
  polygon: [number, number][]
  isRectified?: boolean
}

export interface CADFloorPlanRendererProps {
  rooms?: CADRoom[]
  structuralElements?: { id: string; type?: string; polygon: [number, number][] }[]
  landInfo?: {
    orientation?: string
    road_facing?: string
    area_sqft?: number
  }
  title?: string
  score?: number
  className?: string
}

export function CADFloorPlanRenderer({
  rooms = [],
  structuralElements = [],
  landInfo,
  title = "VUE EN PLAN",
  score,
  className = "",
}: CADFloorPlanRendererProps) {
  // Theme & Display Controls
  const [theme, setTheme] = useState<'whitepaper' | 'blueprint'>('whitepaper')
  const [showDimensions, setShowDimensions] = useState(true)
  const [showStencils, setShowStencils] = useState(true)
  const [showHatch, setShowHatch] = useState(true)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })

  // Compute canonical bounding box enclosing all rooms
  const { minX, maxX, minY, maxY, width, height } = useMemo(() => {
    let allX: number[] = []
    let allY: number[] = []
    rooms.forEach(r => {
      r.polygon.forEach(([x, y]) => {
        allX.push(x)
        allY.push(y)
      })
    })
    if (allX.length === 0) {
      return { minX: 0, maxX: 60, minY: 0, maxY: 60, width: 60, height: 60 }
    }
    const xMin = Math.min(...allX)
    const xMax = Math.max(...allX)
    const yMin = Math.min(...allY)
    const yMax = Math.max(...allY)
    return {
      minX: xMin,
      maxX: xMax,
      minY: yMin,
      maxY: yMax,
      width: Math.max(xMax - xMin, 1),
      height: Math.max(yMax - yMin, 1),
    }
  }, [rooms])

  // Dynamic Scale & Proportional Dimensions
  const baseDim = Math.max(width, height, 10)
  const isMillimeters = baseDim > 500
  const unitScale = isMillimeters ? 0.001 : 1.0
  const unitLabel = "m"

  // Standard architectural drawing line weights scaled to viewBox coordinates
  const wallThick = baseDim * 0.022 // ~240mm exterior/interior wall cavity
  const wallOutlineStroke = baseDim * 0.0045 // ~50mm contour line
  const doorLeafStroke = baseDim * 0.0055 // ~65mm solid door leaf
  const doorArcStroke = baseDim * 0.0028 // ~30mm door swing trajectory
  const stencilHeavy = baseDim * 0.0042 // Primary furniture contour
  const stencilLight = baseDim * 0.0024 // Secondary details (burners, cushions, faucets)
  const dimLineStroke = baseDim * 0.002 // Dimension line
  const dimSlashStroke = baseDim * 0.0042 // 45° architectural slash ticks
  const hatchSpacing = baseDim * 0.015 // Diagonal cross-hatch pattern size

  // Margins for external dimension chains and "VUE EN PLAN" title banner
  const padLeft = width * 0.18
  const padRight = width * 0.12
  const padTop = height * 0.18
  const padBottom = height * 0.24

  const viewBox = `${minX - padLeft} ${minY - padTop} ${width + padLeft + padRight} ${height + padTop + padBottom}`

  // Colors based on theme
  const isWhite = theme === 'whitepaper'
  const strokeColor = isWhite ? '#0f172a' : '#f8fafc'
  const wallHatchColor = isWhite ? '#334155' : '#94a3b8'
  const dimColor = isWhite ? '#334155' : '#cbd5e1'
  const bgColor = isWhite ? '#ffffff' : '#0b0f19'
  const gridLineColor = isWhite ? '#f1f5f9' : '#1e293b'
  const fixtureFill = isWhite ? '#f8fafc' : '#1e293b'
  const fixtureAccent = isWhite ? '#e2e8f0' : '#334155'

  // Pre-calculate Room Metrics (BBoxes, areas, collision detection)
  const roomMetrics = useMemo(() => {
    return rooms.map(room => {
      const xs = room.polygon.map(p => p[0])
      const ys = room.polygon.map(p => p[1])
      const rxMin = Math.min(...xs)
      const rxMax = Math.max(...xs)
      const ryMin = Math.min(...ys)
      const ryMax = Math.max(...ys)
      const rw = Math.max(rxMax - rxMin, 1)
      const rh = Math.max(ryMax - ryMin, 1)
      const cx = (rxMin + rxMax) / 2
      const cy = (ryMin + ryMax) / 2

      let area = 0
      for (let i = 0; i < room.polygon.length; i++) {
        const j = (i + 1) % room.polygon.length
        area += room.polygon[i][0] * room.polygon[j][1]
        area -= room.polygon[j][0] * room.polygon[i][1]
      }
      area = Math.abs(area / 2) * (unitScale * unitScale)

      const raw = (room.name || room.type || '').toLowerCase()
      const isStairs = raw.includes('stair') || raw.includes('escalier')

      return {
        room,
        minX: rxMin,
        maxX: rxMax,
        minY: ryMin,
        maxY: ryMax,
        w: rw,
        h: rh,
        cx,
        cy,
        area,
        raw,
        isStairs,
      }
    })
  }, [rooms, unitScale])

  // Identify nested rooms (e.g. Staircase inside Store Room / Central Hall) to avoid label collisions
  const labelPositions = useMemo(() => {
    const map = new Map<string, { x: number; y: number; isSubordinate: boolean }>()
    roomMetrics.forEach(curr => {
      let isInsideAnother = false
      let labelY = curr.cy

      // Check if another room contains this room
      for (const other of roomMetrics) {
        if (other.room.id === curr.room.id) continue
        const contains = (
          curr.minX >= other.minX - 5 &&
          curr.maxX <= other.maxX + 5 &&
          curr.minY >= other.minY - 5 &&
          curr.maxY <= other.maxY + 5 &&
          (curr.w * curr.h < other.w * other.h * 0.8)
        )
        if (contains) {
          isInsideAnother = true
          break
        }
      }

      // Check if centers are nearly identical
      for (const other of roomMetrics) {
        if (other.room.id === curr.room.id) continue
        const dist = Math.hypot(curr.cx - other.cx, curr.cy - other.cy)
        if (dist < baseDim * 0.08) {
          if (curr.isStairs) {
            labelY = curr.cy + curr.h * 0.28
          } else if (other.isStairs) {
            labelY = curr.cy - other.h * 0.35
          }
        }
      }

      map.set(curr.room.id, { x: curr.cx, y: labelY, isSubordinate: isInsideAnother })
    })
    return map
  }, [roomMetrics, baseDim])

  // Pan & Zoom Handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true)
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
  }
  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y })
    }
  }
  const handleMouseUp = () => setIsDragging(false)

  // --------------------------------------------------------------------------
  // Architectural Stencils Renderer (High contrast, scaled to viewBox)
  // --------------------------------------------------------------------------
  const renderRoomStencil = (m: typeof roomMetrics[0]) => {
    if (!showStencils) return null
    const { raw, minX: rxMin, maxX: rxMax, minY: ryMin, maxY: ryMax, w: rw, h: rh, cx, cy } = m

    // 1. STAIRCASE (Architectural Tread Steps & Flight Direction Arrow)
    if (m.isStairs) {
      const stepCount = 10
      const stepHeight = rh / stepCount
      return (
        <g stroke={strokeColor} fill="none" opacity={0.92}>
          {/* Staircase Enclosing Flight Box */}
          <rect
            x={rxMin}
            y={ryMin}
            width={rw}
            height={rh}
            strokeWidth={wallOutlineStroke}
            fill={fixtureFill}
          />
          {/* Parallel Tread Lines */}
          {Array.from({ length: stepCount - 1 }).map((_, i) => (
            <line
              key={`stair-step-${i}`}
              x1={rxMin}
              y1={ryMin + (i + 1) * stepHeight}
              x2={rxMax}
              y2={ryMin + (i + 1) * stepHeight}
              strokeWidth={stencilLight}
            />
          ))}
          {/* Center Dividing Handrail Line */}
          <line
            x1={cx}
            y1={ryMin}
            x2={cx}
            y2={ryMax}
            strokeWidth={stencilHeavy}
            strokeDasharray={`${baseDim * 0.006} ${baseDim * 0.004}`}
          />
          {/* Directional Flight Arrow & "UP" Label */}
          <line
            x1={cx}
            y1={ryMax - rh * 0.15}
            x2={cx}
            y2={ryMin + rh * 0.15}
            strokeWidth={stencilHeavy}
          />
          <polygon
            points={`${cx},${ryMin + rh * 0.08} ${cx - rw * 0.08},${ryMin + rh * 0.18} ${cx + rw * 0.08},${ryMin + rh * 0.18}`}
            fill={strokeColor}
          />
          <circle cx={cx} cy={ryMax - rh * 0.15} r={baseDim * 0.005} fill={strokeColor} />
        </g>
      )
    }

    // 2. KITCHEN (L-Countertop, Double Basin Stainless Sink, 4-Burner Cooktop)
    if (raw.includes('kitchen') || raw.includes('cuisine') || raw.includes('labo')) {
      const counterDepth = Math.min(rw, rh) * 0.24
      const sinkW = rw * 0.32
      const sinkH = counterDepth * 0.74
      const sinkX = rxMin + rw * 0.08
      const sinkY = ryMin + counterDepth * 0.13

      const stoveW = rw * 0.28
      const stoveH = counterDepth * 0.74
      const stoveX = rxMax - rw * 0.08 - stoveW
      const stoveY = ryMin + counterDepth * 0.13

      return (
        <g stroke={strokeColor} fill="none" opacity={0.95}>
          {/* Solid Continuous Countertop with Perimeter Stroke */}
          <rect
            x={rxMin}
            y={ryMin}
            width={rw}
            height={counterDepth}
            fill={fixtureFill}
            stroke={strokeColor}
            strokeWidth={stencilHeavy}
          />

          {/* Stainless Steel Double Basin Sink */}
          <rect
            x={sinkX}
            y={sinkY}
            width={sinkW}
            height={sinkH}
            rx={baseDim * 0.003}
            fill={fixtureAccent}
            strokeWidth={stencilHeavy}
          />
          {/* Left Bowl */}
          <rect
            x={sinkX + sinkW * 0.06}
            y={sinkY + sinkH * 0.1}
            width={sinkW * 0.4}
            height={sinkH * 0.8}
            rx={baseDim * 0.002}
            fill={bgColor}
            strokeWidth={stencilLight}
          />
          {/* Right Bowl */}
          <rect
            x={sinkX + sinkW * 0.54}
            y={sinkY + sinkH * 0.1}
            width={sinkW * 0.4}
            height={sinkH * 0.8}
            rx={baseDim * 0.002}
            fill={bgColor}
            strokeWidth={stencilLight}
          />
          {/* Swivel Faucet */}
          <circle cx={sinkX + sinkW * 0.5} cy={sinkY + sinkH * 0.15} r={baseDim * 0.004} fill={strokeColor} />

          {/* 4-Burner Gas Cooktop Plate */}
          <rect
            x={stoveX}
            y={stoveY}
            width={stoveW}
            height={stoveH}
            rx={baseDim * 0.004}
            fill={fixtureAccent}
            strokeWidth={stencilHeavy}
          />
          {/* 4 Concentric Burner Rings */}
          <circle cx={stoveX + stoveW * 0.28} cy={stoveY + stoveH * 0.3} r={stoveH * 0.22} strokeWidth={stencilHeavy} />
          <circle cx={stoveX + stoveW * 0.28} cy={stoveY + stoveH * 0.3} r={stoveH * 0.08} fill={strokeColor} />

          <circle cx={stoveX + stoveW * 0.72} cy={stoveY + stoveH * 0.3} r={stoveH * 0.18} strokeWidth={stencilHeavy} />
          <circle cx={stoveX + stoveW * 0.72} cy={stoveY + stoveH * 0.3} r={stoveH * 0.07} fill={strokeColor} />

          <circle cx={stoveX + stoveW * 0.28} cy={stoveY + stoveH * 0.7} r={stoveH * 0.18} strokeWidth={stencilHeavy} />
          <circle cx={stoveX + stoveW * 0.28} cy={stoveY + stoveH * 0.7} r={stoveH * 0.07} fill={strokeColor} />

          <circle cx={stoveX + stoveW * 0.72} cy={stoveY + stoveH * 0.7} r={stoveH * 0.22} strokeWidth={stencilHeavy} />
          <circle cx={stoveX + stoveW * 0.72} cy={stoveY + stoveH * 0.7} r={stoveH * 0.08} fill={strokeColor} />
        </g>
      )
    }

    // 3. MASTER BEDROOM & BEDROOMS (King Bed, Pillows, Duvet Fold, Bedside Tables)
    if (raw.includes('bed') || raw.includes('chambre')) {
      const isMaster = raw.includes('master')
      const bedW = rw * (isMaster ? 0.44 : 0.38)
      const bedH = rh * (isMaster ? 0.52 : 0.46)
      const bedX = cx - bedW / 2
      const bedY = ryMin + rh * 0.06

      const tableW = bedW * 0.22
      const tableH = bedW * 0.22

      return (
        <g stroke={strokeColor} fill="none" opacity={0.92}>
          {/* Bed Headboard along Wall */}
          <rect
            x={bedX - bedW * 0.04}
            y={bedY}
            width={bedW * 1.08}
            height={bedH * 0.1}
            rx={baseDim * 0.002}
            fill={fixtureAccent}
            strokeWidth={stencilHeavy}
          />
          {/* Bed Mattress */}
          <rect
            x={bedX}
            y={bedY + bedH * 0.1}
            width={bedW}
            height={bedH * 0.9}
            rx={baseDim * 0.003}
            fill={fixtureFill}
            strokeWidth={stencilHeavy}
          />
          {/* Turned-down Duvet Fold Sheet */}
          <line
            x1={bedX}
            y1={bedY + bedH * 0.46}
            x2={bedX + bedW}
            y2={bedY + bedH * 0.46}
            strokeWidth={stencilLight}
          />
          {/* Left Pillow */}
          <rect
            x={bedX + bedW * 0.08}
            y={bedY + bedH * 0.15}
            width={bedW * 0.38}
            height={bedH * 0.22}
            rx={baseDim * 0.003}
            fill={bgColor}
            strokeWidth={stencilLight}
          />
          {/* Right Pillow */}
          <rect
            x={bedX + bedW * 0.54}
            y={bedY + bedH * 0.15}
            width={bedW * 0.38}
            height={bedH * 0.22}
            rx={baseDim * 0.003}
            fill={bgColor}
            strokeWidth={stencilLight}
          />
          {/* Left Bedside Nightstand & Lamp */}
          <rect
            x={bedX - tableW - bedW * 0.04}
            y={bedY + bedH * 0.06}
            width={tableW}
            height={tableH}
            rx={baseDim * 0.002}
            fill={fixtureFill}
            strokeWidth={stencilHeavy}
          />
          <circle cx={bedX - tableW / 2 - bedW * 0.04} cy={bedY + bedH * 0.06 + tableH / 2} r={tableW * 0.22} strokeWidth={stencilLight} />

          {/* Right Bedside Nightstand & Lamp */}
          <rect
            x={bedX + bedW + bedW * 0.04}
            y={bedY + bedH * 0.06}
            width={tableW}
            height={tableH}
            rx={baseDim * 0.002}
            fill={fixtureFill}
            strokeWidth={stencilHeavy}
          />
          <circle cx={bedX + bedW + bedW * 0.04 + tableW / 2} cy={bedY + bedH * 0.06 + tableH / 2} r={tableW * 0.22} strokeWidth={stencilLight} />
        </g>
      )
    }

    // 4. LIVING ROOM & SALON (3-Seater Sofa, Coffee Table, Dining Ensemble)
    if (raw.includes('living') || raw.includes('salon') || raw.includes('sejour')) {
      const sofaW = rw * 0.46
      const sofaH = rh * 0.26
      const sofaX = cx - sofaW / 2
      const sofaY = ryMin + rh * 0.08

      const tableW = sofaW * 0.65
      const tableH = sofaH * 0.42
      const tableX = cx - tableW / 2
      const tableY = sofaY + sofaH + rh * 0.05

      return (
        <g stroke={strokeColor} fill="none" opacity={0.92}>
          {/* Sofa Outer Frame */}
          <rect
            x={sofaX}
            y={sofaY}
            width={sofaW}
            height={sofaH}
            rx={baseDim * 0.004}
            fill={fixtureFill}
            strokeWidth={stencilHeavy}
          />
          {/* Backrest Line */}
          <line
            x1={sofaX}
            y1={sofaY + sofaH * 0.3}
            x2={sofaX + sofaW}
            y2={sofaY + sofaH * 0.3}
            strokeWidth={stencilHeavy}
          />
          {/* Left Armrest */}
          <line
            x1={sofaX + sofaW * 0.12}
            y1={sofaY}
            x2={sofaX + sofaW * 0.12}
            y2={sofaY + sofaH}
            strokeWidth={stencilHeavy}
          />
          {/* Right Armrest */}
          <line
            x1={sofaX + sofaW * 0.88}
            y1={sofaY}
            x2={sofaX + sofaW * 0.88}
            y2={sofaY + sofaH}
            strokeWidth={stencilHeavy}
          />
          {/* 3 Cushion Divider Lines */}
          <line
            x1={sofaX + sofaW * 0.37}
            y1={sofaY + sofaH * 0.3}
            x2={sofaX + sofaW * 0.37}
            y2={sofaY + sofaH}
            strokeWidth={stencilLight}
          />
          <line
            x1={sofaX + sofaW * 0.63}
            y1={sofaY + sofaH * 0.3}
            x2={sofaX + sofaW * 0.63}
            y2={sofaY + sofaH}
            strokeWidth={stencilLight}
          />

          {/* Coffee Table */}
          <rect
            x={tableX}
            y={tableY}
            width={tableW}
            height={tableH}
            rx={baseDim * 0.003}
            fill={fixtureAccent}
            strokeWidth={stencilHeavy}
          />
        </g>
      )
    }

    // 5. WASHROOM / BATHROOM / WC (Toilet Suite & Vanity Washbasin)
    if (raw.includes('bath') || raw.includes('wash') || raw.includes('wc') || raw.includes('toilet')) {
      const tw = rw * 0.32
      const th = rh * 0.42
      const tx = rxMin + rw * 0.12
      const ty = ryMin + rh * 0.1

      const vw = rw * 0.34
      const vh = rh * 0.34
      const vx = rxMax - vw - rw * 0.1
      const vy = ryMin + rh * 0.1

      return (
        <g stroke={strokeColor} fill="none" opacity={0.92}>
          {/* Toilet Cistern Tank */}
          <rect
            x={tx}
            y={ty}
            width={tw}
            height={th * 0.36}
            rx={baseDim * 0.002}
            fill={fixtureAccent}
            strokeWidth={stencilHeavy}
          />
          {/* Flush Push Button */}
          <circle cx={tx + tw / 2} cy={ty + th * 0.18} r={baseDim * 0.003} fill={strokeColor} />
          {/* Toilet Bowl (Elongated Porcelain Oval) */}
          <ellipse
            cx={tx + tw / 2}
            cy={ty + th * 0.72}
            rx={tw * 0.42}
            ry={th * 0.38}
            fill={fixtureFill}
            strokeWidth={stencilHeavy}
          />
          <ellipse
            cx={tx + tw / 2}
            cy={ty + th * 0.72}
            rx={tw * 0.24}
            ry={th * 0.22}
            strokeWidth={stencilLight}
          />

          {/* Vanity Basin Cabinet */}
          <rect
            x={vx}
            y={vy}
            width={vw}
            height={vh}
            rx={baseDim * 0.002}
            fill={fixtureFill}
            strokeWidth={stencilHeavy}
          />
          {/* Washbasin Oval Bowl */}
          <ellipse
            cx={vx + vw / 2}
            cy={vy + vh / 2}
            rx={vw * 0.38}
            ry={vh * 0.32}
            fill={bgColor}
            strokeWidth={stencilHeavy}
          />
          <circle cx={vx + vw / 2} cy={vy + vh * 0.22} r={baseDim * 0.003} fill={strokeColor} />
        </g>
      )
    }

    return null
  }

  // --------------------------------------------------------------------------
  // Door Swing Geometry (High Visibility 90° Swing Arc & Bold Door Leaf)
  // --------------------------------------------------------------------------
  const renderDoor = (m: typeof roomMetrics[0]) => {
    // Avoid drawing doors on pure stairs
    if (m.isStairs) return null

    const { minX: rxMin, maxX: rxMax, minY: ryMin, maxY: ryMax, w: rw, h: rh } = m
    const doorSize = Math.min(rw, rh) * 0.24 // Realistic 800mm-900mm passage

    // Intelligent door placement on interior partitions
    // Default door on bottom interior wall
    const dx = rxMin + rw * 0.18
    const dy = ryMax

    // Door leaf extends 90° vertically into the room: (dx, dy) -> (dx, dy - doorSize)
    const leafX2 = dx
    const leafY2 = dy - doorSize

    // 90° circular arc from leaf end (dx, dy - doorSize) to wall opening edge (dx + doorSize, dy)
    const arcPath = `M ${dx} ${dy - doorSize} A ${doorSize} ${doorSize} 0 0 1 ${dx + doorSize} ${dy}`

    return (
      <g key={`door-${m.room.id}`} opacity={1}>
        {/* Door Opening Gap Cut in Wall */}
        <line
          x1={dx - baseDim * 0.001}
          y1={dy}
          x2={dx + doorSize + baseDim * 0.001}
          y2={dy}
          stroke={bgColor}
          strokeWidth={wallThick * 1.3}
          strokeLinecap="butt"
        />

        {/* 90° Dotted Circular Trajectory Swing Arc */}
        <path
          d={arcPath}
          stroke={strokeColor}
          strokeWidth={doorArcStroke}
          strokeDasharray={`${baseDim * 0.008} ${baseDim * 0.006}`}
          fill="none"
        />

        {/* Solid Architectural Door Leaf */}
        <line
          x1={dx}
          y1={dy}
          x2={leafX2}
          y2={leafY2}
          stroke={strokeColor}
          strokeWidth={doorLeafStroke}
          strokeLinecap="round"
        />

        {/* Door Hinge Pivot Point Dot */}
        <circle
          cx={dx}
          cy={dy}
          r={baseDim * 0.004}
          fill={strokeColor}
        />
      </g>
    )
  }

  return (
    <div className={`relative w-full rounded-2xl overflow-hidden border border-border shadow-xl flex flex-col ${isWhite ? 'bg-white text-slate-900' : 'bg-slate-950 text-slate-100'} ${className}`}>
      {/* Top Interactive Toolbar */}
      <div className={`flex flex-wrap items-center justify-between gap-2 p-3 border-b z-20 backdrop-blur-md ${isWhite ? 'bg-slate-50/90 border-slate-200' : 'bg-slate-900/90 border-slate-800'}`}>
        <div className="flex items-center gap-2">
          <Badge className={`font-mono text-xs font-semibold px-2.5 py-0.5 ${isWhite ? 'bg-slate-900 text-white' : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'}`}>
            {title}
          </Badge>
          {score !== undefined && (
            <span className="text-xs font-mono font-bold text-emerald-500 flex items-center gap-1">
              <Sparkles className="w-3.5 h-3.5" /> {score}% Vastu Aligned
            </span>
          )}
        </div>

        {/* Right Toolbar Controls */}
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setTheme(isWhite ? 'blueprint' : 'whitepaper')}
            className="h-7 px-2 text-[11px] gap-1"
            title="Toggle CAD White / Blueprint Dark theme"
          >
            {isWhite ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
            {isWhite ? 'Blueprint Dark' : 'CAD Whitepaper'}
          </Button>

          <Button
            size="sm"
            variant={showDimensions ? 'default' : 'ghost'}
            onClick={() => setShowDimensions(!showDimensions)}
            className="h-7 px-2 text-[11px]"
          >
            Dimensions
          </Button>

          <Button
            size="sm"
            variant={showStencils ? 'default' : 'ghost'}
            onClick={() => setShowStencils(!showStencils)}
            className="h-7 px-2 text-[11px]"
          >
            Fixtures
          </Button>

          <div className="h-4 w-[1px] bg-border mx-1" />

          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => setZoom(z => Math.min(z + 0.2, 3))}
            title="Zoom In"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => setZoom(z => Math.max(z - 0.2, 0.6))}
            title="Zoom Out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}
            title="Reset View"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* SVG CAD Canvas Viewport */}
      <div 
        className="relative w-full h-[540px] overflow-hidden cursor-grab active:cursor-grabbing select-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg
          viewBox={viewBox}
          className="w-full h-full"
          style={{
            transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
            transformOrigin: 'center center',
            transition: isDragging ? 'none' : 'transform 0.15s ease-out',
          }}
        >
          <defs>
            {/* 45° Diagonal Wall Cross-Hatch Pattern Scaled to Real Dimensions */}
            <pattern
              id="cad-wall-hatch"
              width={hatchSpacing}
              height={hatchSpacing}
              patternUnits="userSpaceOnUse"
            >
              <path
                d={`M 0 0 L ${hatchSpacing} ${hatchSpacing} M ${hatchSpacing} 0 L 0 ${hatchSpacing}`}
                stroke={wallHatchColor}
                strokeWidth={baseDim * 0.0018}
                opacity={isWhite ? 0.5 : 0.65}
              />
            </pattern>
          </defs>

          {/* Background Drawing Sheet */}
          <rect
            x={minX - padLeft}
            y={minY - padTop}
            width={width + padLeft + padRight}
            height={height + padTop + padBottom}
            fill={bgColor}
          />

          {/* Subtle Drawing Paper Grid */}
          <g opacity={isWhite ? 0.35 : 0.15}>
            {Array.from({ length: 16 }).map((_, i) => (
              <line
                key={`gx-${i}`}
                x1={minX - padLeft}
                y1={minY - padTop + (i * (height + padTop + padBottom)) / 15}
                x2={maxX + padRight}
                y2={minY - padTop + (i * (height + padTop + padBottom)) / 15}
                stroke={gridLineColor}
                strokeWidth={baseDim * 0.001}
                strokeDasharray={`${baseDim * 0.006} ${baseDim * 0.006}`}
              />
            ))}
            {Array.from({ length: 16 }).map((_, i) => (
              <line
                key={`gy-${i}`}
                x1={minX - padLeft + (i * (width + padLeft + padRight)) / 15}
                y1={minY - padTop}
                x2={minX - padLeft + (i * (width + padLeft + padRight)) / 15}
                y2={maxY + padBottom}
                stroke={gridLineColor}
                strokeWidth={baseDim * 0.001}
                strokeDasharray={`${baseDim * 0.006} ${baseDim * 0.006}`}
              />
            ))}
          </g>

          {/* 1. LAYER ONE: Room Interior Surfaces */}
          {rooms.map((room) => {
            const ptsStr = room.polygon.map(p => `${p[0]},${p[1]}`).join(' ')
            return (
              <polygon
                key={`poly-${room.id}`}
                points={ptsStr}
                fill={isWhite ? (room.isRectified ? "#f0fdf4" : "#ffffff") : (room.isRectified ? "#062e1e" : "#0d1527")}
                stroke="none"
              />
            )
          })}

          {/* 2. LAYER TWO: Architectural Fixtures & Stencils */}
          {roomMetrics.map(m => (
            <g key={`stencil-${m.room.id}`}>
              {renderRoomStencil(m)}
            </g>
          ))}

          {/* 3. LAYER THREE: Double-Line Walls with Architectural Diagonal Hatching */}
          {rooms.map((room) => {
            const ptsStr = room.polygon.map(p => `${p[0]},${p[1]}`).join(' ')
            return (
              <g key={`walls-${room.id}`}>
                {/* Wall Cavity with Visible 45° Diagonal Hatching */}
                {showHatch && (
                  <polygon
                    points={ptsStr}
                    fill="none"
                    stroke="url(#cad-wall-hatch)"
                    strokeWidth={wallThick}
                    strokeLinejoin="miter"
                  />
                )}
                {/* Outer/Inner Solid Contour Lines */}
                <polygon
                  points={ptsStr}
                  fill="none"
                  stroke={strokeColor}
                  strokeWidth={wallOutlineStroke}
                  strokeLinejoin="miter"
                />
              </g>
            )
          })}

          {/* 4. LAYER FOUR: Door Openings & 90° Swing Arcs */}
          {roomMetrics.map(m => renderDoor(m))}

          {/* 5. LAYER FIVE: Architectural Dimension Chains (External & Witness Lines) */}
          {showDimensions && (
            <g stroke={dimColor} fill={dimColor} fontSize={Math.max(baseDim * 0.024, 9)}>
              {/* Top Overall Horizontal Dimension */}
              <g>
                <line
                  x1={minX}
                  y1={minY - padTop * 0.55}
                  x2={maxX}
                  y2={minY - padTop * 0.55}
                  strokeWidth={dimLineStroke}
                />
                {/* Extension Witness Lines */}
                <line x1={minX} y1={minY - padTop * 0.72} x2={minX} y2={minY - padTop * 0.08} strokeWidth={dimLineStroke * 0.8} />
                <line x1={maxX} y1={minY - padTop * 0.72} x2={maxX} y2={minY - padTop * 0.08} strokeWidth={dimLineStroke * 0.8} />
                {/* 45° Architectural Slash Tick Marks */}
                <line
                  x1={minX - baseDim * 0.01}
                  y1={minY - padTop * 0.55 + baseDim * 0.01}
                  x2={minX + baseDim * 0.01}
                  y2={minY - padTop * 0.55 - baseDim * 0.01}
                  strokeWidth={dimSlashStroke}
                />
                <line
                  x1={maxX - baseDim * 0.01}
                  y1={minY - padTop * 0.55 + baseDim * 0.01}
                  x2={maxX + baseDim * 0.01}
                  y2={minY - padTop * 0.55 - baseDim * 0.01}
                  strokeWidth={dimSlashStroke}
                />
                {/* Dimension Text with Background Pill */}
                <text
                  x={(minX + maxX) / 2}
                  y={minY - padTop * 0.65}
                  textAnchor="middle"
                  fontWeight="bold"
                  fontFamily="monospace"
                  fill={strokeColor}
                >
                  {(width * unitScale).toFixed(2)} {unitLabel}
                </text>
              </g>

              {/* Left Overall Vertical Dimension */}
              <g>
                <line
                  x1={minX - padLeft * 0.55}
                  y1={minY}
                  x2={minX - padLeft * 0.55}
                  y2={maxY}
                  strokeWidth={dimLineStroke}
                />
                {/* Extension Witness Lines */}
                <line x1={minX - padLeft * 0.72} y1={minY} x2={minX - padLeft * 0.08} y2={minY} strokeWidth={dimLineStroke * 0.8} />
                <line x1={minX - padLeft * 0.72} y1={maxY} x2={minX - padLeft * 0.08} y2={maxY} strokeWidth={dimLineStroke * 0.8} />
                {/* 45° Architectural Slash Tick Marks */}
                <line
                  x1={minX - padLeft * 0.55 - baseDim * 0.01}
                  y1={minY + baseDim * 0.01}
                  x2={minX - padLeft * 0.55 + baseDim * 0.01}
                  y2={minY - baseDim * 0.01}
                  strokeWidth={dimSlashStroke}
                />
                <line
                  x1={minX - padLeft * 0.55 - baseDim * 0.01}
                  y1={maxY + baseDim * 0.01}
                  x2={minX - padLeft * 0.55 + baseDim * 0.01}
                  y2={maxY - baseDim * 0.01}
                  strokeWidth={dimSlashStroke}
                />
                {/* Dimension Text */}
                <text
                  x={minX - padLeft * 0.66}
                  y={(minY + maxY) / 2}
                  textAnchor="middle"
                  transform={`rotate(-90, ${minX - padLeft * 0.66}, ${(minY + maxY) / 2})`}
                  fontWeight="bold"
                  fontFamily="monospace"
                  fill={strokeColor}
                >
                  {(height * unitScale).toFixed(2)} {unitLabel}
                </text>
              </g>
            </g>
          )}

          {/* 6. LAYER SIX: Room Stamps (Non-colliding Room Title, Area in m², Rectified Badge) */}
          {roomMetrics.map((m) => {
            const pos = labelPositions.get(m.room.id) || { x: m.cx, y: m.cy, isSubordinate: false }
            const lx = pos.x
            const ly = pos.y
            const displayName = (m.room.name || m.room.type || 'ROOM').toUpperCase()
            const nameFontSize = Math.max(baseDim * 0.024, 9)
            const areaFontSize = Math.max(baseDim * 0.018, 7.5)

            // If it's a subordinate room (e.g. Staircase), render a compact clean tag
            if (m.isStairs) {
              return (
                <g key={`label-${m.room.id}`} textAnchor="middle" pointerEvents="none">
                  <rect
                    x={lx - baseDim * 0.08}
                    y={ly - baseDim * 0.02}
                    width={baseDim * 0.16}
                    height={baseDim * 0.038}
                    rx={baseDim * 0.005}
                    fill={isWhite ? "rgba(255,255,255,0.92)" : "rgba(15,23,42,0.92)"}
                    stroke={strokeColor}
                    strokeWidth={baseDim * 0.0018}
                  />
                  <text
                    x={lx}
                    y={ly + baseDim * 0.006}
                    fill={strokeColor}
                    fontWeight="bold"
                    fontSize={baseDim * 0.016}
                    fontFamily="system-ui, sans-serif"
                    letterSpacing="0.06em"
                  >
                    STAIRCASE
                  </text>
                </g>
              )
            }

            return (
              <g key={`label-${m.room.id}`} textAnchor="middle" pointerEvents="none">
                {/* Background Legibility Card Pill */}
                <rect
                  x={lx - baseDim * 0.14}
                  y={ly - nameFontSize * 1.2}
                  width={baseDim * 0.28}
                  height={nameFontSize * 2.8 + (m.room.isRectified ? nameFontSize : 0)}
                  rx={baseDim * 0.006}
                  fill={isWhite ? "rgba(255,255,255,0.88)" : "rgba(11,15,25,0.88)"}
                  stroke={isWhite ? "rgba(226,232,240,0.8)" : "rgba(51,65,85,0.8)"}
                  strokeWidth={baseDim * 0.0015}
                />

                {/* Room Title */}
                <text
                  x={lx}
                  y={ly - 2}
                  fill={strokeColor}
                  fontWeight="bold"
                  fontSize={nameFontSize}
                  fontFamily="system-ui, -apple-system, sans-serif"
                  letterSpacing="0.04em"
                >
                  {displayName}
                </text>

                {/* Area Tag in m² */}
                <text
                  x={lx}
                  y={ly + nameFontSize + 1}
                  fill={isWhite ? '#475569' : '#94a3b8'}
                  fontWeight="600"
                  fontSize={areaFontSize}
                  fontFamily="monospace"
                >
                  {m.area > 0 ? `${m.area.toFixed(2)} m²` : ''}
                </text>

                {/* Rectified Badge if modified by VSAI */}
                {m.room.isRectified && (
                  <text
                    x={lx}
                    y={ly + nameFontSize * 2.2 + 2}
                    fill="#10b981"
                    fontWeight="bold"
                    fontSize={Math.max(baseDim * 0.015, 6)}
                    fontFamily="monospace"
                  >
                    ★ RECTIFIED
                  </text>
                )}
              </g>
            )
          })}

          {/* 7. LAYER SEVEN: Authentic "VUE EN PLAN" Title Banner Scaled Dynamically */}
          {(() => {
            const bannerW = baseDim * 0.32
            const bannerH = baseDim * 0.062
            const bannerX = (minX + maxX) / 2
            const bannerY = maxY + padBottom * 0.58
            return (
              <g transform={`translate(${bannerX}, ${bannerY})`}>
                <rect
                  x={-bannerW / 2}
                  y={-bannerH / 2}
                  width={bannerW}
                  height={bannerH}
                  rx={bannerH / 2}
                  fill={isWhite ? "#ffffff" : "#0f172a"}
                  stroke={strokeColor}
                  strokeWidth={baseDim * 0.0035}
                />
                <text
                  x="0"
                  y={bannerH * 0.16}
                  textAnchor="middle"
                  fill={strokeColor}
                  fontWeight="900"
                  fontSize={bannerH * 0.44}
                  letterSpacing="0.18em"
                  fontFamily="system-ui, -apple-system, sans-serif"
                >
                  VUE EN PLAN
                </text>
              </g>
            )
          })()}
        </svg>

        {/* Compass Indicator Card with High Contrast */}
        <div className={`absolute bottom-4 left-4 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-mono backdrop-blur-md shadow-md ${
          isWhite 
            ? 'bg-white/95 border-slate-300 text-slate-900 shadow-slate-200' 
            : 'bg-slate-900/95 border-slate-700 text-slate-100 shadow-slate-950'
        }`}>
          <Compass className="w-4 h-4 text-emerald-500 animate-pulse" />
          <span>Orientation: <strong className={isWhite ? 'text-slate-950 font-bold' : 'text-white font-bold'}>{landInfo?.orientation || 'North (N)'}</strong></span>
        </div>
      </div>
    </div>
  )
}
