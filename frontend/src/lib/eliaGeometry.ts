/**
 * Geometry helpers for ELIA exterior landscape Three.js rendering.
 *
 * Coordinate system note:
 *   ELIA uses a flat XY plane (meters). Three.js uses XZY (Y is up).
 *   All helpers convert: ELIA (x, y) → Three.js (x, 0, -y)
 *   The negation of y gives correct orientation when camera looks down.
 */
import * as THREE from 'three'
import type { ExteriorFeature, GeoJsonGeometry } from '@/types/elia'

// ---------------------------------------------------------------------------
// Coordinate conversion
// ---------------------------------------------------------------------------

/** Convert an ELIA [x, y] pair to a Three.js Vector3 at elevation `elev`. */
export function eliaToThree(x: number, y: number, elev = 0): THREE.Vector3 {
  return new THREE.Vector3(x, elev, -y)
}

/** Extract [x, y] center from an ExteriorFeature. Returns null when unavailable. */
export function featureCenter(f: ExteriorFeature): [number, number] | null {
  if (f.position) {
    if (Array.isArray(f.position)) return [f.position[0], f.position[1]]
    if (typeof f.position === 'object') return [(f.position as { x: number; y: number }).x, (f.position as { x: number; y: number }).y]
  }
  const ring = polygonRing(f)
  if (ring && ring.length >= 3) {
    const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length
    const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length
    return [cx, cy]
  }
  return null
}

// ---------------------------------------------------------------------------
// Polygon extraction
// ---------------------------------------------------------------------------

/** Extract the outer ring from an ExteriorFeature as [x,y][] or null. */
export function polygonRing(f: ExteriorFeature): [number, number][] | null {
  if (f.polygon && f.polygon.length >= 3) return f.polygon as [number, number][]
  if (f.geometry) return ringFromGeometry(f.geometry as GeoJsonGeometry)
  return null
}

/** Extract outer ring from a GeoJSON Polygon geometry. */
export function ringFromGeometry(geo: GeoJsonGeometry): [number, number][] | null {
  if (!geo || typeof geo !== 'object') return null
  if (geo.type === 'Polygon') {
    const coords = (geo as { type: 'Polygon'; coordinates: number[][][] }).coordinates
    if (coords && coords[0] && coords[0].length >= 3) {
      return coords[0].map(p => [p[0], p[1]] as [number, number])
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// THREE shape helpers
// ---------------------------------------------------------------------------

/**
 * Build a THREE.Shape from a flat ELIA polygon ring (clockwise/counter-clockwise
 * — Three.js tolerates both; it will triangulate correctly).
 */
export function ringToShape(ring: [number, number][]): THREE.Shape {
  const shape = new THREE.Shape()
  shape.moveTo(ring[0][0], -ring[0][1])
  for (let i = 1; i < ring.length; i++) shape.lineTo(ring[i][0], -ring[i][1])
  shape.closePath()
  return shape
}

/**
 * Build a THREE.BufferGeometry as a flat polygon mesh from an ELIA ring.
 * The mesh lies in the XZ plane (y = 0 unless extruded).
 */
export function ringToFlatGeometry(ring: [number, number][], depth = 0): THREE.BufferGeometry {
  const shape = ringToShape(ring)
  if (depth > 0) {
    return new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false })
  }
  return new THREE.ShapeGeometry(shape)
}

/**
 * Build an array of Vector3 points suitable for a THREE Line loop from a ring.
 * Points are closed (last === first).
 */
export function ringToLinePoints(ring: [number, number][], elev = 0): THREE.Vector3[] {
  const pts = ring.map(([x, y]) => eliaToThree(x, y, elev))
  if (pts.length > 0) pts.push(pts[0].clone()) // close
  return pts
}

// ---------------------------------------------------------------------------
// Bounding box helpers
// ---------------------------------------------------------------------------

export interface BBox {
  minX: number; maxX: number; minY: number; maxY: number;
  width: number; height: number; cx: number; cy: number;
}

/** Compute bounding box for a ring. */
export function ringBBox(ring: [number, number][]): BBox {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const [x, y] of ring) {
    if (x < minX) minX = x; if (x > maxX) maxX = x
    if (y < minY) minY = y; if (y > maxY) maxY = y
  }
  const width = maxX - minX; const height = maxY - minY
  return { minX, maxX, minY, maxY, width, height, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 }
}

/** Scale factor to normalise a bbox so the longest side ≈ `targetSize`. */
export function normScale(bbox: BBox, targetSize = 20): number {
  const longest = Math.max(bbox.width, bbox.height, 1)
  return targetSize / longest
}
