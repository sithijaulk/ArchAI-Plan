"use client"
/**
 * EliaLandscape2D — SVG plan-view renderer for ELIA exterior_landscape data.
 *
 * Renders a top-down 2D plan view with:
 *   - Land boundary (dashed green outline)
 *   - House footprint (filled blue-grey)
 *   - Driveway (grey)
 *   - Garage (dark blue)
 *   - Gate positions (orange diamond)
 *   - Vegetation nodes (green circles scaled to canopy width)
 *   - Lighting nodes (yellow stars)
 *   - Outdoor elements (grey rectangles)
 *   - North arrow
 *   - Validation badge
 *
 * All values are in ELIA meter space projected directly to SVG.
 * The viewBox is computed from the land boundary bounding box.
 */
import React, { useMemo } from 'react'
import type { ExteriorFeature, ExteriorLandscape } from '@/types/elia'
import { ringFromGeometry, polygonRing, featureCenter, ringBBox } from '@/lib/eliaGeometry'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ringToSvgPoints(ring: [number, number][]): string {
  return ring.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
}

function ringToSvgPath(ring: [number, number][]): string {
  if (!ring.length) return ''
  const [first, ...rest] = ring
  return `M${first[0].toFixed(2)},${first[1].toFixed(2)} ` +
    rest.map(([x, y]) => `L${x.toFixed(2)},${y.toFixed(2)}`).join(' ') + ' Z'
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

function diamondPath(cx: number, cy: number, r: number): string {
  return `M${cx},${cy - r} L${cx + r * 0.6},${cy} L${cx},${cy + r} L${cx - r * 0.6},${cy} Z`
}

// ---------------------------------------------------------------------------
// Feature dimensions helper
// ---------------------------------------------------------------------------
function canopyRadius(f: ExteriorFeature): number {
  const dims = f.dimensions ?? {}
  const w = dims.canopy_width_m ?? dims.diameter_m ?? dims.width_m ?? dims.width ?? 2
  return Math.max(0.5, w / 2)
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
interface Props {
  landscape: ExteriorLandscape
}

export default function EliaLandscape2D({ landscape }: Props) {
  // Compute viewBox from land boundary
  const { viewBox, padding, landRing, houseRing, driveRing, garageRing } = useMemo(() => {
    const landGeo = landscape.land ?? (landscape.site_analysis as any)?.land_polygon
    const land = landGeo ? ringFromGeometry(landGeo as any) : null
    const house = landscape.house_exterior
      ? ringFromGeometry(landscape.house_exterior as any)
      : null
    const drive = landscape.access?.driveway
      ? polygonRing(landscape.access.driveway)
      : null
    const garage = landscape.access?.garage
      ? polygonRing(landscape.access.garage)
      : null

    const bbox = land ? ringBBox(land) : { minX: 0, minY: 0, width: 30, height: 20, cx: 15, cy: 10, maxX: 30, maxY: 20 }
    const pad = Math.max(bbox.width, bbox.height) * 0.08

    return {
      viewBox: `${(bbox.minX - pad).toFixed(2)} ${(bbox.minY - pad).toFixed(2)} ${(bbox.width + pad * 2).toFixed(2)} ${(bbox.height + pad * 2).toFixed(2)}`,
      padding: pad,
      landRing: land,
      houseRing: house,
      driveRing: drive,
      garageRing: garage,
    }
  }, [landscape])

  const northAngle = landscape.environment?.north_angle ?? 0
  const validation = landscape.validation_summary
  const gates: ExteriorFeature[] = [
    ...(landscape.access?.gate ? [landscape.access.gate] : []),
    ...(landscape.access?.gates ?? []),
  ]

  // North arrow: from center of scene, arrow tip direction
  const landGeo = landscape.land ?? (landscape.site_analysis as any)?.land_polygon
  const landRingForArrow = landGeo ? ringFromGeometry(landGeo as any) : null
  const bbox2 = landRingForArrow ? ringBBox(landRingForArrow) : null
  const arrowCx = bbox2 ? bbox2.minX - padding * 0.6 : 0
  const arrowCy = bbox2 ? bbox2.minY + (bbox2.height * 0.15) : 0
  const arrowLen = bbox2 ? Math.max(bbox2.width, bbox2.height) * 0.08 : 2
  const rad = (northAngle * Math.PI) / 180
  const arrowTipX = arrowCx + Math.sin(rad) * arrowLen
  const arrowTipY = arrowCy - Math.cos(rad) * arrowLen // SVG Y is down, north is up

  return (
    <div className="w-full h-full min-h-[480px] flex flex-col">
      {/* Validation badge */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        {validation && (
          <>
            <span
              className={`px-2 py-0.5 rounded text-xs font-semibold ${validation.valid ? 'bg-green-900/60 text-green-300' : 'bg-red-900/60 text-red-300'}`}
            >
              {validation.valid ? '✓ Valid layout' : '✗ Infeasible'}
            </span>
            <span className="text-xs text-muted-foreground">
              {validation.checks_passed}/{validation.checks_total} checks · {(validation.constraint_satisfaction_rate * 100).toFixed(0)}%
            </span>
          </>
        )}
        <span className="text-xs text-muted-foreground ml-auto font-mono">2D plan · meters</span>
      </div>

      {/* Violations */}
      {validation?.violations?.length > 0 && (
        <ul className="text-xs text-red-400 mb-2 space-y-0.5 max-h-20 overflow-y-auto">
          {validation.violations.map((v, i) => <li key={i} className="pl-2 border-l border-red-800">⚠ {v}</li>)}
        </ul>
      )}

      {/* SVG plan */}
      <div className="flex-1 bg-[#0a140a] rounded-lg overflow-hidden border border-border">
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
            <marker id="arrow-north" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#ef4444" />
            </marker>
          </defs>

          {/* Land boundary */}
          {landRing && (
            <polygon
              points={ringToSvgPoints(landRing)}
              fill="#1a2a1a"
              stroke="#4ade80"
              strokeWidth="0.3"
              strokeDasharray="1 0.5"
            />
          )}

          {/* Driveway */}
          {driveRing && (
            <polygon
              points={ringToSvgPoints(driveRing)}
              fill="#374151"
              stroke="#6b7280"
              strokeWidth="0.15"
            />
          )}

          {/* Garage */}
          {garageRing && (
            <polygon
              points={ringToSvgPoints(garageRing)}
              fill="#1e3a5f"
              stroke="#60a5fa"
              strokeWidth="0.2"
            />
          )}

          {/* House */}
          {houseRing && (
            <polygon
              points={ringToSvgPoints(houseRing)}
              fill="#334155"
              stroke="#94a3b8"
              strokeWidth="0.25"
            />
          )}

          {/* Outdoor elements */}
          {landscape.outdoor_elements?.map((el) => {
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

          {/* Vegetation nodes */}
          {landscape.vegetation_nodes?.map((node) => {
            const c = featureCenter(node)
            if (!c) return null
            const r = canopyRadius(node)
            return (
              <g key={node.json_id}>
                {/* Canopy */}
                <circle cx={c[0]} cy={c[1]} r={r} fill="#16a34a" opacity={0.7} stroke="#22c55e" strokeWidth="0.1" />
                {/* Trunk dot */}
                <circle cx={c[0]} cy={c[1]} r={r * 0.15} fill="#713f12" />
              </g>
            )
          })}

          {/* Gate markers */}
          {gates.map((gate) => {
            const c = featureCenter(gate)
            if (!c) return null
            const r = 0.4
            return (
              <g key={gate.json_id}>
                <path d={diamondPath(c[0], c[1], r)} fill="#f97316" stroke="#fff" strokeWidth="0.08" />
              </g>
            )
          })}

          {/* Lighting nodes */}
          {landscape.outdoor_lighting?.nodes?.map((node) => {
            const c = featureCenter(node)
            if (!c) return null
            return (
              <path key={node.json_id} d={starPath(c[0], c[1], 0.35)} fill="#fbbf24" stroke="#d97706" strokeWidth="0.06" />
            )
          })}

          {/* Vertical greenery (small teal squares on building edge) */}
          {landscape.vertical_greenery?.elements?.map((el) => {
            const c = featureCenter(el)
            if (!c) return null
            const s = 0.5
            return (
              <rect key={el.json_id} x={c[0] - s / 2} y={c[1] - s / 2} width={s} height={s}
                fill="#0d9488" stroke="#2dd4bf" strokeWidth="0.1" opacity={0.85} />
            )
          })}

          {/* North arrow */}
          <line
            x1={arrowCx}
            y1={arrowCy}
            x2={arrowTipX}
            y2={arrowTipY}
            stroke="#ef4444"
            strokeWidth="0.3"
            markerEnd="url(#arrow-north)"
          />
          <text x={arrowCx} y={arrowCy + arrowLen * 1.6} textAnchor="middle" fontSize="0.8" fill="#ef4444" fontFamily="monospace">N</text>
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
