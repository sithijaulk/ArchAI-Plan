"use client"
/**
 * EliaLandscape2D — Multi-Projection Architectural CAD 2D Viewer for ELIA.
 *
 * Supports 4 Real CAD Projections:
 *   1. සැලැස්ම (Site & Landscape Master Plan)
 *   2. ඉදිරි පෙනුම (Front Elevation with Front Boundary, Entrance Gate, & House Facade)
 *   3. පැති පෙනුම (Side Elevation with Setback & Side Facade)
 *   4. පසුපස පෙනුම (Rear Elevation with Rear Yard, Garden & Back Facade)
 */
import React, { useMemo, useState, useRef, useCallback, useEffect } from 'react'
import type {
  ExteriorLandscape,
  EliaViewModel,
  ExteriorFeature,
} from '@/types/elia'
import {
  polygonBBox,
  polygonToSvgPath,
  featureCenter,
  featureCanopyRadius,
  deduplicateGates,
  normalizePolygonCoordinates,
} from '@/lib/eliaGeometry'
import { Button } from '@/components/ui/button'
import { ZoomIn, ZoomOut, RotateCcw, Compass, Layers } from 'lucide-react'

interface Props {
  viewModel?: EliaViewModel | null
  landscape?: ExteriorLandscape | null
  selectedFeatureId?: string | null
  onSelectFeature?: (id: string) => void
  lockedFeatureIds?: string[]
}

type ProjectionView = 'plan' | 'front' | 'side' | 'rear'

export default function EliaLandscape2D({
  viewModel,
  landscape: directLandscape,
  selectedFeatureId,
  onSelectFeature,
  lockedFeatureIds = [],
}: Props) {
  const landscape = viewModel?.landscape ?? directLandscape ?? null

  const [projection, setProjection] = useState<ProjectionView>('plan')
  const [zoom, setZoom] = useState(1.0)
  const [pan, setPan] = useState({ x: 0, y: 0 })

  // Extract authoritative land & house coordinates
  const landCoords = useMemo(() => {
    if (viewModel?.landPolygon?.coordinates) {
      return viewModel.landPolygon.coordinates
    }
    if (landscape?.land) {
      return normalizePolygonCoordinates(landscape.land)
    }
    return null
  }, [viewModel, landscape])

  const houseCoords = useMemo(() => {
    if (viewModel?.housePolygon?.coordinates) {
      return viewModel.housePolygon.coordinates
    }
    if (landscape?.house_exterior) {
      return normalizePolygonCoordinates(landscape.house_exterior)
    }
    return null
  }, [viewModel, landscape])

  const driveCoords = useMemo(() => {
    if (landscape?.access?.driveway) {
      return normalizePolygonCoordinates(
        landscape.access.driveway.geometry || landscape.access.driveway.polygon
      )
    }
    return null
  }, [landscape])

  const garageCoords = useMemo(() => {
    if (landscape?.access?.garage) {
      return normalizePolygonCoordinates(
        landscape.access.garage.geometry || landscape.access.garage.polygon
      )
    }
    return null
  }, [landscape])

  const garageBBox = useMemo(() => {
    if (!garageCoords || garageCoords.length === 0) return null
    return polygonBBox(garageCoords)
  }, [garageCoords])

  // Deduplicate gates
  const gates = useMemo(() => {
    return deduplicateGates(landscape?.access)
  }, [landscape?.access])

  // Compute land bounding box
  const bbox = useMemo(() => {
    const coords = landCoords && landCoords.length > 0 ? landCoords : [[[0, 0], [30, 0], [30, 20], [0, 20]]]
    return polygonBBox(coords)
  }, [landCoords])

  // Building bounds
  const houseBBox = useMemo(() => {
    if (!houseCoords || houseCoords.length === 0) {
      return {
        minX: bbox.minX + bbox.width * 0.25,
        maxX: bbox.minX + bbox.width * 0.75,
        minY: bbox.minY + bbox.height * 0.25,
        maxY: bbox.minY + bbox.height * 0.75,
        width: bbox.width * 0.5,
        height: bbox.height * 0.5,
      }
    }
    return polygonBBox(houseCoords)
  }, [houseCoords, bbox])

  const buildingHeight = 6.8
  const pad = Math.max(bbox.width, bbox.height) * 0.1

  // ViewBox per projection
  const viewBox = useMemo(() => {
    if (projection === 'plan') {
      const baseW = bbox.width + pad * 2
      const baseH = bbox.height + pad * 2
      const curW = baseW / zoom
      const curH = baseH / zoom
      const curMinX = bbox.minX - pad + (baseW - curW) / 2 - pan.x
      const curMinY = bbox.minY - pad + (baseH - curH) / 2 - pan.y
      return `${curMinX.toFixed(2)} ${curMinY.toFixed(2)} ${curW.toFixed(2)} ${curH.toFixed(2)}`
    }

    if (projection === 'front' || projection === 'rear') {
      const w = bbox.width + pad * 2
      const h = buildingHeight + 6
      const curW = w / zoom
      const curH = h / zoom
      const minX = bbox.minX - pad + (w - curW) / 2 - pan.x
      return `${minX.toFixed(2)} -${buildingHeight + 3.5} ${curW.toFixed(2)} ${curH.toFixed(2)}`
    }

    // Side view
    const w = bbox.height + pad * 2
    const h = buildingHeight + 6
    const curW = w / zoom
    const curH = h / zoom
    const minX = bbox.minY - pad + (w - curW) / 2 - pan.x
    return `${minX.toFixed(2)} -${buildingHeight + 3.5} ${curW.toFixed(2)} ${curH.toFixed(2)}`
  }, [projection, bbox, pad, buildingHeight, zoom, pan])

  const cartesianTransform = useMemo(() => {
    const baseH = bbox.height + pad * 2
    const baseMinY = bbox.minY - pad
    return `translate(0, ${baseMinY * 2 + baseH}) scale(1, -1)`
  }, [bbox, pad])

  // Mouse pan handlers
  const isDraggingRef = useRef(false)
  const dragStartRef = useRef({ x: 0, y: 0 })

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return
    isDraggingRef.current = true
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDraggingRef.current) {
      setPan({
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      })
    }
  }

  const handleMouseUp = () => {
    isDraggingRef.current = false
  }

  const handleReset = () => {
    setZoom(1.0)
    setPan({ x: 0, y: 0 })
  }

  return (
    <div className="flex flex-col w-full h-[520px] bg-[#071309] rounded-xl overflow-hidden border border-emerald-950/60 select-none relative">
      {/* ── Top CAD Navigation & Projection Switcher ─────────────────────── */}
      <div className="absolute top-3 left-3 z-20 flex flex-wrap items-center gap-2 bg-slate-950/90 backdrop-blur-md px-3.5 py-1.5 rounded-xl border border-emerald-500/30 shadow-xl text-xs text-slate-200">
        <span className="font-bold text-emerald-400 flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-emerald-400" /> ELIA Exterior CAD
        </span>
        <div className="h-3.5 w-[1px] bg-slate-700 mx-1" />

        {/* 4 Projections Switcher */}
        <div className="flex items-center gap-0.5 bg-slate-900 p-0.5 rounded-lg border border-slate-800">
          <Button
            size="sm"
            variant={projection === 'plan' ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px] font-semibold"
            onClick={() => {
              setProjection('plan')
              handleReset()
            }}
          >
            සැලැස්ම (Plan)
          </Button>
          <Button
            size="sm"
            variant={projection === 'front' ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px] font-semibold"
            onClick={() => {
              setProjection('front')
              handleReset()
            }}
          >
            ඉදිරි පෙනුම (Front)
          </Button>
          <Button
            size="sm"
            variant={projection === 'side' ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px] font-semibold"
            onClick={() => {
              setProjection('side')
              handleReset()
            }}
          >
            පැති පෙනුම (Side)
          </Button>
          <Button
            size="sm"
            variant={projection === 'rear' ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px] font-semibold"
            onClick={() => {
              setProjection('rear')
              handleReset()
            }}
          >
            පසුපස පෙනුම (Rear)
          </Button>
        </div>

        <div className="h-3.5 w-[1px] bg-slate-700 mx-1" />

        <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => setZoom((z) => Math.min(z + 0.25, 4))} title="Zoom In">
          <ZoomIn className="w-3.5 h-3.5" />
        </Button>
        <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => setZoom((z) => Math.max(z - 0.25, 0.4))} title="Zoom Out">
          <ZoomOut className="w-3.5 h-3.5" />
        </Button>
        <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={handleReset} title="Reset View">
          <RotateCcw className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* ── Top-Right North Indicator ──────────────────────────────────── */}
      <div className="absolute top-3 right-3 z-20 bg-slate-950/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-emerald-500/30 flex items-center gap-2 text-xs font-mono shadow-md">
        <Compass className="w-4 h-4 text-emerald-400" />
        <span className="font-bold text-slate-200">
          {projection === 'plan' ? 'NORTH UP (Plan View)' : projection === 'front' ? 'FRONT ELEVATION (South View)' : projection === 'side' ? 'SIDE ELEVATION (East View)' : 'REAR ELEVATION (North View)'}
        </span>
      </div>

      {/* ── SVG Drawing Canvas ─────────────────────────────────────────── */}
      <div
        className="w-full h-full cursor-grab active:cursor-grabbing flex items-center justify-center"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg
          width="100%"
          height="100%"
          viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
          className="transition-transform duration-75"
        >
          <defs>
            <pattern id="elia-grid" width="2" height="2" patternUnits="userSpaceOnUse">
              <path d="M 2 0 L 0 0 0 2" fill="none" stroke="rgba(74, 222, 128, 0.05)" strokeWidth="0.05" />
            </pattern>
            <pattern id="elia-earth" width="1.2" height="1.2" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
              <line x1="0" y1="0" x2="0" y2="1.2" stroke="#1e293b" strokeWidth="0.1" />
            </pattern>
          </defs>

          {/* Grid Background */}
          <rect x="-100" y="-100" width="300" height="300" fill="url(#elia-grid)" />

          {/* ============================================================= */}
          {/* 1. PLAN VIEW (සැලැස්ම - Site & Landscape Plan)                 */}
          {/* ============================================================= */}
          {projection === 'plan' && (
            <g transform={cartesianTransform}>
              {/* Land Boundary */}
              {landCoords && (
                <path
                  d={polygonToSvgPath(landCoords)}
                  fill="rgba(16, 185, 129, 0.06)"
                  fillRule="evenodd"
                  stroke="#10b981"
                  strokeWidth="0.25"
                  strokeDasharray="0.8 0.4"
                />
              )}

              {/* Driveway */}
              {driveCoords && (
                <path
                  d={polygonToSvgPath(driveCoords)}
                  fill="#334155"
                  fillRule="evenodd"
                  stroke="#64748b"
                  strokeWidth="0.15"
                />
              )}

              {/* Garage / Carport with CAD Parking Bays & Vehicle Silhouettes */}
              {garageCoords && garageBBox && (() => {
                const gb = garageBBox
                const capacity = Number((landscape?.access?.garage as any)?.capacity || (landscape?.access as any)?.vehicle_count || 1)
                const vProfile = String((landscape?.access?.garage as any)?.vehicle_type || (landscape?.access as any)?.vehicle_profiles?.[0]?.vehicle_type || 'car').toLowerCase()
                const isEnclosed = Boolean((landscape?.access?.garage as any)?.is_enclosed ?? true)
                
                // Decide division orientation: along the longer axis
                const isHorizontal = gb.width >= gb.height
                const bayCount = Math.max(1, Math.min(capacity, 6))
                const baySize = isHorizontal ? gb.width / bayCount : gb.height / bayCount
                const vLabel = vProfile === 'electric_vehicle' ? 'EV' : vProfile.toUpperCase()

                return (
                  <g id="elia-parking-facility">
                    {/* Parking Area Floor */}
                    <path
                      d={polygonToSvgPath(garageCoords)}
                      fill="#1e293b"
                      fillRule="evenodd"
                      stroke="#0284c7"
                      strokeWidth="0.22"
                    />
                    {/* Perimeter Accent */}
                    <path
                      d={polygonToSvgPath(garageCoords)}
                      fill="none"
                      stroke="#38bdf8"
                      strokeWidth="0.08"
                      strokeDasharray="0.4, 0.4"
                    />

                    {/* Internal Bay Dividers */}
                    {bayCount > 1 && Array.from({ length: bayCount - 1 }).map((_, idx) => {
                      const offset = (idx + 1) * baySize
                      return isHorizontal ? (
                        <line
                          key={`div_${idx}`}
                          x1={gb.minX + offset}
                          y1={gb.minY + 0.2}
                          x2={gb.minX + offset}
                          y2={gb.maxY - 0.2}
                          stroke="#f59e0b"
                          strokeWidth="0.1"
                          strokeDasharray="0.3, 0.2"
                        />
                      ) : (
                        <line
                          key={`div_${idx}`}
                          x1={gb.minX + 0.2}
                          y1={gb.minY + offset}
                          x2={gb.maxX - 0.2}
                          y2={gb.minY + offset}
                          stroke="#f59e0b"
                          strokeWidth="0.1"
                          strokeDasharray="0.3, 0.2"
                        />
                      )
                    })}

                    {/* Vehicle Silhouettes & Labels inside each bay */}
                    {Array.from({ length: bayCount }).map((_, idx) => {
                      const bayCenterX = isHorizontal
                        ? gb.minX + (idx + 0.5) * baySize
                        : (gb.minX + gb.maxX) / 2
                      const bayCenterY = isHorizontal
                        ? (gb.minY + gb.maxY) / 2
                        : gb.minY + (idx + 0.5) * baySize

                      const carW = isHorizontal ? Math.min(baySize * 0.7, 2.0) : Math.min(gb.width * 0.7, 2.0)
                      const carH = isHorizontal ? Math.min(gb.height * 0.75, 4.2) : Math.min(baySize * 0.75, 4.2)

                      return (
                        <g key={`veh_${idx}`} className="select-none pointer-events-none">
                          {/* Vehicle Body */}
                          <rect
                            x={bayCenterX - carW / 2}
                            y={bayCenterY - carH / 2}
                            width={carW}
                            height={carH}
                            rx={0.35}
                            fill="#0f172a"
                            stroke={vProfile === 'electric_vehicle' ? '#10b981' : '#38bdf8'}
                            strokeWidth="0.12"
                          />
                          {/* Windshield */}
                          <rect
                            x={bayCenterX - carW * 0.35}
                            y={bayCenterY - carH * 0.25}
                            width={carW * 0.7}
                            height={carH * 0.22}
                            rx={0.1}
                            fill={vProfile === 'electric_vehicle' ? '#065f46' : '#0369a1'}
                          />
                          {/* Rear window */}
                          <rect
                            x={bayCenterX - carW * 0.35}
                            y={bayCenterY + carH * 0.15}
                            width={carW * 0.7}
                            height={carH * 0.15}
                            rx={0.08}
                            fill={vProfile === 'electric_vehicle' ? '#065f46' : '#0369a1'}
                          />
                          {/* Text badge */}
                          <text
                            x={bayCenterX}
                            y={bayCenterY + 0.1}
                            textAnchor="middle"
                            fontSize="0.3"
                            fontWeight="700"
                            fill="#ffffff"
                            className="font-mono"
                          >
                            {`P${idx + 1}`}
                          </text>
                          <text
                            x={bayCenterX}
                            y={bayCenterY + carH / 2 + 0.35}
                            textAnchor="middle"
                            fontSize="0.22"
                            fontWeight="600"
                            fill={vProfile === 'electric_vehicle' ? '#34d399' : '#38bdf8'}
                            className="font-mono"
                          >
                            {vLabel}
                          </text>
                        </g>
                      )
                    })}

                    {/* Facility Header Badge */}
                    <text
                      x={(gb.minX + gb.maxX) / 2}
                      y={gb.minY - 0.25}
                      textAnchor="middle"
                      fontSize="0.3"
                      fontWeight="700"
                      fill="#38bdf8"
                      className="font-sans"
                    >
                      {isEnclosed ? 'ENCLOSED GARAGE' : 'PARKING FACILITY'}
                    </text>
                  </g>
                )
              })()}

              {/* House Footprint */}
              {houseCoords && (
                <path
                  d={polygonToSvgPath(houseCoords)}
                  fill="#1e293b"
                  fillRule="evenodd"
                  stroke="#94a3b8"
                  strokeWidth="0.25"
                />
              )}

              {/* Outdoor Elements (Patios, dining sets, gazebos) */}
              {landscape?.outdoor_elements?.map((el) => {
                const c = featureCenter(el)
                if (!c) return null
                const dims = el.dimensions ?? {}
                const w = dims.width_m ?? dims.width ?? 1.5
                const d = dims.depth_m ?? dims.depth ?? w
                const isSelected = selectedFeatureId === el.json_id
                const isLocked = lockedFeatureIds.includes(el.json_id)
                return (
                  <g
                    key={el.json_id}
                    onClick={() => onSelectFeature?.(el.json_id)}
                    className="cursor-pointer"
                  >
                    <rect
                      x={c[0] - w / 2}
                      y={c[1] - d / 2}
                      width={w}
                      height={d}
                      rx={0.1}
                      fill={isSelected ? '#0284c7' : '#334155'}
                      stroke={isSelected ? '#38bdf8' : isLocked ? '#f59e0b' : '#64748b'}
                      strokeWidth={isSelected ? 0.22 : 0.12}
                    />
                  </g>
                )
              })}

              {/* Vegetation Canopy Nodes (Trees & Palms) with Species Badges & Preferred Highlights */}
              {landscape?.vegetation_nodes?.map((node) => {
                const c = featureCenter(node)
                if (!c) return null
                const r = featureCanopyRadius(node)
                const isSelected = selectedFeatureId === node.json_id
                const isLocked = lockedFeatureIds.includes(node.json_id)
                const isPreferred = Boolean((node as any).is_preferred)
                const rawName = (node as any).display_name || (node as any).species_name || node.category || 'Tree'
                // Keep short readable label for plan view
                const shortName = rawName.length > 22 ? rawName.slice(0, 20) + '..' : rawName

                return (
                  <g
                    key={node.json_id}
                    onClick={() => onSelectFeature?.(node.json_id)}
                    className="cursor-pointer"
                  >
                    {/* Outer Foliage Ring */}
                    <circle
                      cx={c[0]}
                      cy={c[1]}
                      r={r}
                      fill={isSelected ? 'rgba(16, 185, 129, 0.45)' : isPreferred ? 'rgba(16, 185, 129, 0.35)' : 'rgba(34, 197, 94, 0.22)'}
                      stroke={isSelected ? '#34d399' : isPreferred ? '#10b981' : isLocked ? '#f59e0b' : '#22c55e'}
                      strokeWidth={isSelected ? 0.25 : isPreferred ? 0.2 : 0.12}
                    />
                    {/* Preferred Plant Accent Ring */}
                    {isPreferred && (
                      <circle
                        cx={c[0]}
                        cy={c[1]}
                        r={r + 0.18}
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth={0.06}
                        strokeDasharray="0.25, 0.15"
                      />
                    )}
                    {/* Inner Texture Ring */}
                    <circle
                      cx={c[0]}
                      cy={c[1]}
                      r={r * 0.65}
                      fill="none"
                      stroke={isPreferred ? '#059669' : '#10b981'}
                      strokeWidth={0.06}
                      strokeDasharray="0.3, 0.2"
                    />
                    {/* Trunk */}
                    <circle cx={c[0]} cy={c[1]} r={r * 0.16} fill="#78350f" stroke="#451a03" strokeWidth={0.03} />

                    {/* Species Badge on Plan View */}
                    <g className="select-none pointer-events-none">
                      <rect
                        x={c[0] - (shortName.length * 0.13) / 2 - 0.2}
                        y={c[1] + r + 0.08}
                        width={shortName.length * 0.13 + 0.4}
                        height={0.42}
                        rx={0.08}
                        fill="rgba(15, 23, 42, 0.88)"
                        stroke={isPreferred ? '#f59e0b' : '#334155'}
                        strokeWidth={0.04}
                      />
                      <text
                        x={c[0]}
                        y={c[1] + r + 0.36}
                        textAnchor="middle"
                        fontSize="0.24"
                        fontWeight={isPreferred ? "700" : "500"}
                        fill={isPreferred ? '#fef08a' : '#e2e8f0'}
                        className="font-sans"
                      >
                        {isPreferred ? `★ ${shortName}` : shortName}
                      </text>
                    </g>
                  </g>
                )
              })}

              {/* Boundary Gates */}
              {gates.map((gate, i) => {
                const c = featureCenter(gate)
                if (!c) return null
                return (
                  <g key={`gate_${i}`}>
                    <rect x={c[0] - 1.2} y={c[1] - 0.2} width="2.4" height="0.4" fill="#f59e0b" stroke="#ffffff" strokeWidth="0.08" />
                  </g>
                )
              })}
            </g>
          )}

          {/* ============================================================= */}
          {/* 2. FRONT ELEVATION VIEW (ඉදිරි පෙනුම)                            */}
          {/* ============================================================= */}
          {projection === 'front' && (
            <g id="elia-front-elevation">
              {/* Earth Hatch Ground */}
              <rect x={bbox.minX - pad} y="0" width={bbox.width + pad * 2} height="2" fill="url(#elia-earth)" />
              <line x1={bbox.minX - pad} y1="0" x2={bbox.maxX + pad} y2="0" stroke="#475569" strokeWidth="0.25" />
              <text x={bbox.minX - pad + 1} y="0.5" fontSize="0.3" fill="#64748b" className="font-mono">
                GL ±0.00m (NATURAL GROUND LEVEL)
              </text>

              {/* Building Facade in Background */}
              <rect
                x={houseBBox.minX}
                y={-buildingHeight}
                width={houseBBox.width}
                height={buildingHeight}
                fill="#1e293b"
                stroke="#64748b"
                strokeWidth="0.18"
              />
              {/* Roof Gabled profile */}
              <polygon
                points={`${houseBBox.minX - 0.5},-${buildingHeight} ${houseBBox.minX + houseBBox.width / 2},-${buildingHeight + 1.8} ${houseBBox.maxX + 0.5},-${buildingHeight}`}
                fill="#9a3412"
                stroke="#ea580c"
                strokeWidth="0.18"
              />
              {/* House Main Door */}
              <rect x={houseBBox.minX + houseBBox.width / 2 - 0.6} y="-2.1" width="1.2" height="2.1" fill="#15803d" stroke="#22c55e" strokeWidth="0.08" />
              {/* House Windows */}
              <rect x={houseBBox.minX + 1.0} y="-2.1" width="1.2" height="1.1" fill="#0284c7" stroke="#38bdf8" strokeWidth="0.06" />
              <rect x={houseBBox.maxX - 2.2} y="-2.1" width="1.2" height="1.1" fill="#0284c7" stroke="#38bdf8" strokeWidth="0.06" />

              {/* Front Garden Trees */}
              {landscape?.vegetation_nodes?.slice(0, 3).map((node, i) => {
                const c = featureCenter(node)
                if (!c) return null
                const r = featureCanopyRadius(node)
                const treeH = 3.5 + (i % 2) * 1.0
                return (
                  <g key={`front_tree_${i}`}>
                    {/* Trunk */}
                    <rect x={c[0] - 0.12} y={-treeH} width="0.24" height={treeH} fill="#78350f" stroke="#451a03" strokeWidth="0.04" />
                    {/* Foliage Canopy */}
                    <circle cx={c[0]} cy={-treeH - r * 0.7} r={r} fill="rgba(34, 197, 94, 0.6)" stroke="#22c55e" strokeWidth="0.1" />
                  </g>
                )
              })}

              {/* Front Boundary Wall & Entrance Gate */}
              <rect x={bbox.minX - pad} y="-1.5" width={bbox.width + pad * 2} height="1.5" fill="rgba(51, 65, 85, 0.45)" stroke="#475569" strokeWidth="0.12" />
              {/* Main Entrance Gate in wall */}
              <rect x={houseBBox.minX + 0.5} y="-1.8" width="3.2" height="1.8" fill="rgba(245, 158, 11, 0.15)" stroke="#f59e0b" strokeWidth="0.12" />
              {Array.from({ length: 8 }).map((_, i) => (
                <line key={`grill_${i}`} x1={houseBBox.minX + 0.5 + 0.4 * i} y1="0" x2={houseBBox.minX + 0.5 + 0.4 * i} y2="-1.8" stroke="#f59e0b" strokeWidth="0.04" />
              ))}
              <text x={houseBBox.minX + 2.1} y="-1.9" fontSize="0.26" fill="#f59e0b" textAnchor="middle" className="font-bold">
                MAIN ENTRANCE GATE
              </text>
            </g>
          )}

          {/* ============================================================= */}
          {/* 3. SIDE ELEVATION VIEW (පැති පෙනුම)                             */}
          {/* ============================================================= */}
          {projection === 'side' && (
            <g id="elia-side-elevation">
              {/* Earth Hatch Ground */}
              <rect x={bbox.minY - pad} y="0" width={bbox.height + pad * 2} height="2" fill="url(#elia-earth)" />
              <line x1={bbox.minY - pad} y1="0" x2={bbox.maxY + pad} y2="0" stroke="#475569" strokeWidth="0.25" />
              <text x={bbox.minY - pad + 1} y="0.5" fontSize="0.3" fill="#64748b" className="font-mono">
                GL ±0.00m (NATURAL GROUND LEVEL)
              </text>

              {/* Side Building Facade */}
              <rect
                x={houseBBox.minY}
                y={-buildingHeight}
                width={houseBBox.height}
                height={buildingHeight}
                fill="#1e293b"
                stroke="#64748b"
                strokeWidth="0.18"
              />
              {/* Side Roof Sloping Profile */}
              <polygon
                points={`${houseBBox.minY - 0.5},-${buildingHeight} ${houseBBox.minY + houseBBox.height / 2},-${buildingHeight + 1.8} ${houseBBox.maxY + 0.5},-${buildingHeight}`}
                fill="#9a3412"
                stroke="#ea580c"
                strokeWidth="0.18"
              />
              {/* Side Windows */}
              <rect x={houseBBox.minY + 1.2} y="-2.1" width="1.1" height="1.1" fill="#0284c7" stroke="#38bdf8" strokeWidth="0.06" />
              <rect x={houseBBox.maxY - 2.3} y="-2.1" width="1.1" height="1.1" fill="#0284c7" stroke="#38bdf8" strokeWidth="0.06" />

              {/* Side Setback Trees & Shrubs */}
              {landscape?.vegetation_nodes?.slice(2, 5).map((node, i) => {
                const c = featureCenter(node)
                if (!c) return null
                const r = featureCanopyRadius(node)
                const treeH = 3.2 + (i % 2) * 0.8
                return (
                  <g key={`side_tree_${i}`}>
                    <rect x={c[1] - 0.1} y={-treeH} width="0.2" height={treeH} fill="#78350f" stroke="#451a03" strokeWidth="0.04" />
                    <circle cx={c[1]} cy={-treeH - r * 0.7} r={r} fill="rgba(34, 197, 94, 0.6)" stroke="#22c55e" strokeWidth="0.1" />
                  </g>
                )
              })}

              {/* Side Boundary Wall */}
              <rect x={bbox.minY - pad} y="-1.5" width={bbox.height + pad * 2} height="1.5" fill="rgba(51, 65, 85, 0.4)" stroke="#475569" strokeWidth="0.12" />
              <text x={bbox.minY - pad + 1} y="-1.6" fontSize="0.24" fill="#94a3b8" className="font-mono">
                SIDE BOUNDARY WALL (H: 1.50m)
              </text>
            </g>
          )}

          {/* ============================================================= */}
          {/* 4. REAR ELEVATION VIEW (පසුපස පෙනුම)                             */}
          {/* ============================================================= */}
          {projection === 'rear' && (
            <g id="elia-rear-elevation">
              {/* Earth Hatch Ground */}
              <rect x={bbox.minX - pad} y="0" width={bbox.width + pad * 2} height="2" fill="url(#elia-earth)" />
              <line x1={bbox.minX - pad} y1="0" x2={bbox.maxX + pad} y2="0" stroke="#475569" strokeWidth="0.25" />
              <text x={bbox.minX - pad + 1} y="0.5" fontSize="0.3" fill="#64748b" className="font-mono">
                GL ±0.00m (NATURAL GROUND LEVEL)
              </text>

              {/* Rear Building Facade */}
              <rect
                x={houseBBox.minX}
                y={-buildingHeight}
                width={houseBBox.width}
                height={buildingHeight}
                fill="#1e293b"
                stroke="#64748b"
                strokeWidth="0.18"
              />
              {/* Roof Profile */}
              <polygon
                points={`${houseBBox.minX - 0.5},-${buildingHeight} ${houseBBox.minX + houseBBox.width / 2},-${buildingHeight + 1.8} ${houseBBox.maxX + 0.5},-${buildingHeight}`}
                fill="#9a3412"
                stroke="#ea580c"
                strokeWidth="0.18"
              />
              {/* Rear Patio Sliding Glass Door */}
              <rect x={houseBBox.minX + houseBBox.width / 2 - 1.2} y="-2.1" width="2.4" height="2.1" fill="rgba(56, 189, 248, 0.3)" stroke="#38bdf8" strokeWidth="0.1" />
              <line x1={houseBBox.minX + houseBBox.width / 2} y1="0" x2={houseBBox.minX + houseBBox.width / 2} y2="-2.1" stroke="#38bdf8" strokeWidth="0.08" />

              {/* Rear Yard Trees & Canopy Garden */}
              {landscape?.vegetation_nodes?.slice(1, 4).map((node, i) => {
                const c = featureCenter(node)
                if (!c) return null
                const r = featureCanopyRadius(node)
                const treeH = 3.6 + (i % 2) * 1.2
                return (
                  <g key={`rear_tree_${i}`}>
                    <rect x={c[0] - 0.12} y={-treeH} width="0.24" height={treeH} fill="#78350f" stroke="#451a03" strokeWidth="0.04" />
                    <circle cx={c[0]} cy={-treeH - r * 0.7} r={r} fill="rgba(34, 197, 94, 0.65)" stroke="#22c55e" strokeWidth="0.1" />
                  </g>
                )
              })}

              {/* Rear Boundary Wall */}
              <rect x={bbox.minX - pad} y="-1.8" width={bbox.width + pad * 2} height="1.8" fill="rgba(51, 65, 85, 0.45)" stroke="#475569" strokeWidth="0.12" />
              <text x={bbox.minX - pad + 1} y="-1.9" fontSize="0.24" fill="#94a3b8" className="font-mono">
                REAR BOUNDARY WALL (H: 1.80m)
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* ── Architectural Drawing Title Block (Bottom Right) ───────────── */}
      <div className="absolute bottom-3 right-3 z-20 bg-slate-950/95 backdrop-blur-md px-3.5 py-2.5 rounded-xl border border-emerald-500/30 shadow-2xl flex flex-col gap-1 text-[11px] min-w-[240px] text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-800 pb-1">
          <span className="font-mono font-bold text-emerald-400 text-xs">ARCHAI • ELIA SITE BLUEPRINT</span>
          <span className="bg-emerald-500/20 text-emerald-300 font-mono text-[10px] px-1.5 py-0.5 rounded">CAD V2</span>
        </div>
        <div className="grid grid-cols-2 gap-x-2 text-[10px]">
          <div>
            <span className="text-muted-foreground block">DRAWING:</span>
            <strong className="text-white">
              {projection === 'plan' ? 'SITE PLAN (සැලැස්ම)' : projection === 'front' ? 'FRONT ELEV. (ඉදිරි)' : projection === 'side' ? 'SIDE ELEV. (පැති)' : 'REAR ELEV. (පසුපස)'}
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block">SCALE:</span>
            <strong className="text-white font-mono">1:200 @ A3</strong>
          </div>
          <div>
            <span className="text-muted-foreground block">STATUS:</span>
            <strong className="text-emerald-400">APPROVED EXTERIOR</strong>
          </div>
          <div>
            <span className="text-muted-foreground block">NORTH REF:</span>
            <strong className="text-emerald-300 font-mono">0° CANONICAL</strong>
          </div>
        </div>
      </div>
    </div>
  )
}
