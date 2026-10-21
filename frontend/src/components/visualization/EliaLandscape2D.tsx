"use client"
/**
 * EliaLandscape2D — SVG plan-view renderer for ELIA exterior_landscape data.
 *
 * Geometry & Coordinate System:
 *   - Local Cartesian meters: +X is right, +Y is UP.
 *   - Renders top-down 2D plan view preserving all interior polygon holes (fillRule="evenodd").
 *   - Authoritative upstream land and house boundaries derived via EliaViewModel.
 *   - Real vegetation canopy dimensions mapped directly from backend.
 *   - Stable gate deduplication.
 *   - Clear missing-geometry and revision-conflict alerts.
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

interface Props {
  viewModel?: EliaViewModel | null
  landscape?: ExteriorLandscape | null
  selectedFeatureId?: string | null
  onSelectFeature?: (id: string) => void
  lockedFeatureIds?: string[]
}

function diamondPath(cx: number, cy: number, r: number): string {
  return `M${cx},${cy - r} L${cx + r * 0.65},${cy} L${cx},${cy + r} L${cx - r * 0.65},${cy} Z`
}

function starPath(cx: number, cy: number, r: number, points = 5): string {
  let d = ''
  for (let i = 0; i < points * 2; i++) {
    const angle = (Math.PI / points) * i - Math.PI / 2
    const radius = i % 2 === 0 ? r : r * 0.45
    const x = cx + Math.cos(angle) * radius
    const y = cy + Math.sin(angle) * radius
    d += (i === 0 ? 'M' : 'L') + `${x.toFixed(2)},${y.toFixed(2)} `
  }
  return d + 'Z'
}

export default function EliaLandscape2D({
  viewModel,
  landscape: directLandscape,
  selectedFeatureId,
  onSelectFeature,
  lockedFeatureIds = [],
}: Props) {
  const landscape = viewModel?.landscape ?? directLandscape ?? null

  // Interactive Pan and Zoom State
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

  // Compute viewBox in standard Cartesian meters (+X right, +Y up)
  const { baseViewBox, bbox, pad, cartesianTransform, dynamicViewBox } = useMemo(() => {
    const coords = landCoords && landCoords.length > 0 ? landCoords : [[[0, 0], [30, 0], [30, 20], [0, 20]]]
    const b = polygonBBox(coords)
    const p = Math.max(b.width, b.height) * 0.08
    const baseW = b.width + p * 2
    const baseH = b.height + p * 2
    const baseMinX = b.minX - p
    const baseMinY = b.minY - p

    // Apply zoom & pan: center stays anchored as zoom changes
    const curW = baseW / zoom
    const curH = baseH / zoom
    const curMinX = baseMinX + (baseW - curW) / 2 - pan.x
    const curMinY = baseMinY + (baseH - curH) / 2 - pan.y

    const transform = `translate(0, ${baseMinY * 2 + baseH}) scale(1, -1)`

    return {
      baseViewBox: `${baseMinX.toFixed(2)} ${baseMinY.toFixed(2)} ${baseW.toFixed(2)} ${baseH.toFixed(2)}`,
      dynamicViewBox: `${curMinX.toFixed(2)} ${curMinY.toFixed(2)} ${curW.toFixed(2)} ${curH.toFixed(2)}`,
      bbox: b,
      pad: p,
      cartesianTransform: transform,
    }
  }, [landCoords, zoom, pan])

  const svgRef = useRef<SVGSVGElement | null>(null)
  const isDraggingRef = useRef(false)
  const hasDraggedRef = useRef(false)
  const dragStartRef = useRef({ x: 0, y: 0 })
  const lastMousePosRef = useRef({ x: 0, y: 0 })

  // Non-passive wheel event listener to prevent unintended page scroll while zooming
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const factor = e.deltaY < 0 ? 1.15 : 0.85
      setZoom((z) => Math.min(Math.max(z * factor, 0.4), 6.0))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  // Robust pointer drag-to-pan with pointer capture
  const handlePointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return // Left click only
    isDraggingRef.current = true
    hasDraggedRef.current = false
    dragStartRef.current = { x: e.clientX, y: e.clientY }
    lastMousePosRef.current = { x: e.clientX, y: e.clientY }
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // Ignore if pointer capture unsupported
    }
  }, [])

  const handlePointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!isDraggingRef.current) return
    const dx = e.clientX - lastMousePosRef.current.x
    const dy = e.clientY - lastMousePosRef.current.y
    lastMousePosRef.current = { x: e.clientX, y: e.clientY }

    if (Math.hypot(e.clientX - dragStartRef.current.x, e.clientY - dragStartRef.current.y) > 3) {
      hasDraggedRef.current = true
    }

    const rect = e.currentTarget.getBoundingClientRect()
    if (rect.width > 0 && rect.height > 0) {
      const scaleX = (bbox.width / zoom) / rect.width
      const scaleY = (bbox.height / zoom) / rect.height
      setPan((prev) => ({
        x: prev.x + dx * scaleX,
        y: prev.y + dy * scaleY,
      }))
    }
  }, [bbox.width, bbox.height, zoom])

  const handlePointerUp = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    isDraggingRef.current = false
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // Ignore
    }
  }, [])

  const handleResetZoom = useCallback(() => {
    setZoom(1.0)
    setPan({ x: 0, y: 0 })
  }, [])

  const gates = useMemo(() => deduplicateGates(landscape?.access), [landscape])
  const validation = landscape?.validation_summary
  const northAngle = landscape?.environment?.north_angle ?? 0

  // North arrow: centered at top-left of the bounding box
  const arrowCx = bbox.minX + pad * 0.5
  const arrowCy = bbox.maxY - pad * 0.5
  const arrowLen = Math.max(bbox.width, bbox.height) * 0.08
  const rad = (northAngle * Math.PI) / 180
  const arrowTipX = arrowCx + Math.sin(rad) * arrowLen
  const arrowTipY = arrowCy + Math.cos(rad) * arrowLen // In +Y up Cartesian!

  const isMissingGeometry =
    viewModel &&
    (viewModel.geometryState === 'missing_all' ||
      viewModel.geometryState === 'missing_land' ||
      viewModel.geometryState === 'revision_mismatch')

  return (
    <div className="w-full h-full min-h-[480px] flex flex-col">
      {/* Header validation & metadata banner */}
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        {validation && (
          <>
            <span
              className={`px-2 py-0.5 rounded text-xs font-semibold ${
                validation.valid ? 'bg-green-900/60 text-green-300' : 'bg-red-900/60 text-red-300'
              }`}
            >
              {validation.valid ? '✓ Valid layout' : '✗ Infeasible'}
            </span>
            <span className="text-xs text-muted-foreground font-mono">
              {validation.checks_passed}/{validation.checks_total} checks ·{' '}
              {(validation.constraint_satisfaction_rate * 100).toFixed(0)}%
            </span>
          </>
        )}
        {viewModel?.isHeightEstimated && (
          <span className="text-[11px] text-amber-300 bg-amber-950/60 border border-amber-800/40 px-2 py-0.5 rounded font-mono">
            Height ~{viewModel.buildingHeightM?.toFixed(1)}m (est)
          </span>
        )}
        
        {/* Interactive Pan/Zoom Controls Bar */}
        <div className="flex items-center gap-1.5 ml-auto text-xs font-mono">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(z * 1.25, 6.0))}
            className="px-2 py-0.5 rounded bg-muted/60 hover:bg-muted text-foreground border border-border/60 transition-colors"
            title="Zoom In"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(z / 1.25, 0.4))}
            className="px-2 py-0.5 rounded bg-muted/60 hover:bg-muted text-foreground border border-border/60 transition-colors"
            title="Zoom Out"
          >
            -
          </button>
          <button
            type="button"
            onClick={handleResetZoom}
            className="px-2 py-0.5 rounded bg-muted/60 hover:bg-muted text-foreground border border-border/60 transition-colors text-[11px]"
            title="Reset Pan &amp; Zoom"
          >
            Fit (100%)
          </button>
          <span className="text-muted-foreground ml-2 text-[11px]">
            {Math.round(zoom * 100)}% · Drag to pan
          </span>
        </div>
      </div>
        {/* Violations */}
        {Array.isArray(validation?.violations) && validation.violations.length > 0 && (
          <ul className="text-xs text-red-400 mb-2 space-y-0.5 max-h-20 overflow-y-auto">
            {validation.violations.map((v, i) => (
              <li key={i} className="pl-2 border-l border-red-800">
                ⚠ {String(v)}
              </li>
            ))}
          </ul>
        )}

        {/* SVG Canvas */}
        <div className="flex-1 bg-[#0a140a] rounded-lg overflow-hidden border border-border relative select-none">
          {isMissingGeometry && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/75 backdrop-blur-sm p-6 text-center">
              <div className="max-w-md space-y-2">
                <div className="text-amber-400 font-semibold text-sm">
                  {viewModel?.geometryState === 'revision_mismatch'
                    ? 'Source Revision Conflict'
                    : 'Upstream Site Geometry Required'}
                </div>
                <p className="text-xs text-white/80 leading-relaxed">
                  {viewModel?.geometryMessage}
                </p>
              </div>
            </div>
          )}

          <svg
            ref={svgRef}
            width="100%"
            height="100%"
            viewBox={dynamicViewBox}
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="ELIA exterior landscape 2D plan view"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            style={{ background: '#0a140a', cursor: 'grab', touchAction: 'none' }}
          >
          <defs>
            <marker id="arrow-north-head" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#ef4444" />
            </marker>
          </defs>

          {/* Geometry group transformed so Cartesian +Y goes UP */}
          <g transform={cartesianTransform}>
            {/* Land boundary with hole preservation */}
            {landCoords && (
              <path
                d={polygonToSvgPath(landCoords)}
                fill="#1a2a1a"
                fillRule="evenodd"
                stroke="#4ade80"
                strokeWidth="0.3"
                strokeDasharray="1 0.5"
              />
            )}

            {/* Driveway */}
            {driveCoords && (
              <path
                d={polygonToSvgPath(driveCoords)}
                fill="#374151"
                fillRule="evenodd"
                stroke="#6b7280"
                strokeWidth="0.15"
              />
            )}

            {/* Garage */}
            {garageCoords && (
              <path
                d={polygonToSvgPath(garageCoords)}
                fill="#1e3a5f"
                fillRule="evenodd"
                stroke="#60a5fa"
                strokeWidth="0.2"
              />
            )}

            {/* House Footprint with hole preservation */}
            {houseCoords && (
              <path
                d={polygonToSvgPath(houseCoords)}
                fill="#334155"
                fillRule="evenodd"
                stroke="#94a3b8"
                strokeWidth="0.25"
              />
            )}

            {/* Outdoor elements */}
            {landscape?.outdoor_elements?.map((el) => {
              const c = featureCenter(el)
              if (!c) return null
              const dims = el.dimensions ?? {}
              const w = dims.width_m ?? dims.width ?? 1
              const d = dims.depth_m ?? dims.depth ?? w
              const isSelected = selectedFeatureId === el.json_id
              const isLocked = lockedFeatureIds.includes(el.json_id)
              return (
                <g
                  key={el.json_id}
                  onClick={() => {
                    if (!hasDraggedRef.current) onSelectFeature?.(el.json_id)
                  }}
                  style={{ cursor: onSelectFeature ? 'pointer' : 'default' }}
                >
                  <rect
                    x={c[0] - w / 2}
                    y={c[1] - d / 2}
                    width={w}
                    height={d}
                    fill={isSelected ? '#3b82f6' : '#4b5563'}
                    stroke={isSelected ? '#60a5fa' : isLocked ? '#f59e0b' : '#6b7280'}
                    strokeWidth={isSelected ? 0.25 : isLocked ? 0.2 : 0.1}
                  />
                  {isLocked && (
                    <circle cx={c[0]} cy={c[1]} r={0.2} fill="#f59e0b" stroke="#ffffff" strokeWidth="0.05" />
                  )}
                </g>
              )
            })}

            {/* Vegetation nodes (real canopy_radius_m) */}
            {landscape?.vegetation_nodes?.map((node) => {
              const c = featureCenter(node)
              if (!c) return null
              const r = featureCanopyRadius(node)
              const isSelected = selectedFeatureId === node.json_id
              const isLocked = lockedFeatureIds.includes(node.json_id)
              return (
                <g
                  key={node.json_id}
                  onClick={() => {
                    if (!hasDraggedRef.current) onSelectFeature?.(node.json_id)
                  }}
                  style={{ cursor: onSelectFeature ? 'pointer' : 'default' }}
                >
                  <circle
                    cx={c[0]}
                    cy={c[1]}
                    r={r}
                    fill={isSelected ? '#059669' : '#16a34a'}
                    opacity={isSelected ? 0.9 : 0.7}
                    stroke={isSelected ? '#38bdf8' : isLocked ? '#f59e0b' : '#22c55e'}
                    strokeWidth={isSelected ? 0.3 : isLocked ? 0.2 : 0.1}
                  />
                  <circle cx={c[0]} cy={c[1]} r={r * 0.15} fill="#713f12" />
                  {isLocked && (
                    <circle cx={c[0]} cy={c[1]} r={0.25} fill="#f59e0b" stroke="#ffffff" strokeWidth="0.06" />
                  )}
                  {isSelected && (
                    <circle
                      cx={c[0]}
                      cy={c[1]}
                      r={r + 0.15}
                      fill="none"
                      stroke="#38bdf8"
                      strokeWidth="0.08"
                      strokeDasharray="0.3 0.2"
                    />
                  )}
                </g>
              )
            })}

            {/* Gates (deduplicated) */}
            {gates.map((gate, i) => {
              const c = featureCenter(gate)
              if (!c) return null
              return (
                <path
                  key={String(gate.json_id || (gate as any).id || `gate_${i}`)}
                  d={diamondPath(c[0], c[1], 0.45)}
                  fill="#f97316"
                  stroke="#ffffff"
                  strokeWidth="0.08"
                />
              )
            })}

            {/* Lighting nodes */}
            {landscape?.outdoor_lighting?.nodes?.map((node) => {
              const c = featureCenter(node)
              if (!c) return null
              const isSelected = selectedFeatureId === node.json_id
              const isLocked = lockedFeatureIds.includes(node.json_id)
              return (
                <g
                  key={node.json_id}
                  onClick={() => {
                    if (!hasDraggedRef.current) onSelectFeature?.(node.json_id)
                  }}
                  style={{ cursor: onSelectFeature ? 'pointer' : 'default' }}
                >
                  <path
                    d={starPath(c[0], c[1], 0.35)}
                    fill={isSelected ? '#fef08a' : '#fbbf24'}
                    stroke={isSelected ? '#38bdf8' : isLocked ? '#f59e0b' : '#d97706'}
                    strokeWidth={isSelected ? 0.15 : 0.06}
                  />
                  {isLocked && (
                    <circle cx={c[0]} cy={c[1]} r={0.15} fill="#f59e0b" stroke="#ffffff" strokeWidth="0.04" />
                  )}
                </g>
              )
            })}

            {/* Vertical greenery elements */}
            {landscape?.vertical_greenery?.elements?.map((el) => {
              const c = featureCenter(el)
              if (!c) return null
              const s = 0.55
              return (
                <rect
                  key={el.json_id}
                  x={c[0] - s / 2}
                  y={c[1] - s / 2}
                  width={s}
                  height={s}
                  fill="#0d9488"
                  stroke="#2dd4bf"
                  strokeWidth="0.1"
                  opacity={0.85}
                />
              )
            })}

            {/* North arrow in Cartesian group */}
            <line
              x1={arrowCx}
              y1={arrowCy}
              x2={arrowTipX}
              y2={arrowTipY}
              stroke="#ef4444"
              strokeWidth="0.35"
              markerEnd="url(#arrow-north-head)"
            />
          </g>

          {/* North 'N' text rendered in un-inverted space to stay readable */}
          {/* arrowCy in Cartesian space translates to: */}
          <text
            x={arrowCx}
            y={bbox.minY * 2 + bbox.height + 2 * pad - (arrowCy + arrowLen * 1.5)}
            textAnchor="middle"
            fontSize={Math.max(0.8, pad * 0.6)}
            fill="#ef4444"
            fontFamily="monospace"
            fontWeight="bold"
          >
            N
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10px] font-mono text-muted-foreground">
        {[
          { color: '#4ade80', label: 'Land' },
          { color: '#94a3b8', label: 'House' },
          { color: '#6b7280', label: 'Driveway' },
          { color: '#60a5fa', label: 'Garage' },
          { color: '#f97316', label: 'Gate' },
          { color: '#22c55e', label: 'Vegetation' },
          { color: '#fbbf24', label: 'Lighting' },
          { color: '#0d9488', label: 'Vertical greenery' },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}
