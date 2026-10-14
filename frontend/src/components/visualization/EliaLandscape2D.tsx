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
import React, { useMemo } from 'react'
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
}: Props) {
  const landscape = viewModel?.landscape ?? directLandscape ?? null

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
  const { viewBox, bbox, pad, cartesianTransform } = useMemo(() => {
    const coords = landCoords && landCoords.length > 0 ? landCoords : [[[0, 0], [30, 0], [30, 20], [0, 20]]]
    const b = polygonBBox(coords)
    const p = Math.max(b.width, b.height) * 0.08
    const vbMinX = b.minX - p
    const vbMinY = b.minY - p
    const vbWidth = b.width + p * 2
    const vbHeight = b.height + p * 2

    // In SVG, Y increases downward. To orient +Y upward while keeping text readable:
    // We map Cartesian Y to SVG Y: svgY = (vbMinY + vbHeight) - (cartY - vbMinY) = 2*vbMinY + vbHeight - cartY
    // Or we use a group transform: translate(0, 2*b.cy) scale(1, -1)
    const transform = `translate(0, ${vbMinY * 2 + vbHeight}) scale(1, -1)`

    return {
      viewBox: `${vbMinX.toFixed(2)} ${vbMinY.toFixed(2)} ${vbWidth.toFixed(2)} ${vbHeight.toFixed(2)}`,
      bbox: b,
      pad: p,
      cartesianTransform: transform,
    }
  }, [landCoords])

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
      <div className="flex items-center gap-3 mb-3 flex-wrap">
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
        <span className="text-xs text-muted-foreground ml-auto font-mono">
          2D plan view · meters (+Y Up)
        </span>
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
      <div className="flex-1 bg-[#0a140a] rounded-lg overflow-hidden border border-border relative">
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
          width="100%"
          height="100%"
          viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="ELIA exterior landscape 2D plan view"
          style={{ background: '#0a140a' }}
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
              return (
                <rect
                  key={el.json_id}
                  x={c[0] - w / 2}
                  y={c[1] - d / 2}
                  width={w}
                  height={d}
                  fill="#4b5563"
                  stroke="#6b7280"
                  strokeWidth="0.1"
                />
              )
            })}

            {/* Vegetation nodes (real canopy_radius_m) */}
            {landscape?.vegetation_nodes?.map((node) => {
              const c = featureCenter(node)
              if (!c) return null
              const r = featureCanopyRadius(node)
              return (
                <g key={node.json_id}>
                  <circle
                    cx={c[0]}
                    cy={c[1]}
                    r={r}
                    fill="#16a34a"
                    opacity={0.7}
                    stroke="#22c55e"
                    strokeWidth="0.1"
                  />
                  <circle cx={c[0]} cy={c[1]} r={r * 0.15} fill="#713f12" />
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
              return (
                <path
                  key={node.json_id}
                  d={starPath(c[0], c[1], 0.35)}
                  fill="#fbbf24"
                  stroke="#d97706"
                  strokeWidth="0.06"
                />
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
