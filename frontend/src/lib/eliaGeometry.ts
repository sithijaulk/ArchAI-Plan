/**
 * Geometry helpers for ELIA exterior landscape visualization (Three.js and 2D SVG).
 *
 * Mathematical Coordinate Mapping:
 *   Established local XY Cartesian convention (meters):
 *     - scene X = (source X in meters - origin X) * display scale
 *     - scene Y = elevation in meters * display scale
 *     - scene Z = -(source Y in meters - origin Y) * display scale
 *
 * In Three.js:
 *   Mesh rotation: [-Math.PI / 2, 0, 0]
 *   Under Euler X rotation of -90°:
 *     local u (source X) -> world X
 *     local v (source Y) -> world -Z (which is scene Z)
 *     local w (extrusion depth) -> world +Y (which is scene Y, extruding upward)
 *   Consequently, polygon surfaces, outlines, and point objects coincide exactly.
 *
 * Inverse Mapping:
 *     - source X = scene X / display scale + origin X
 *     - source Y = -scene Z / display scale + origin Y
 *     - elevation = scene Y / display scale
 */
import * as THREE from 'three'
import type {
  ExteriorFeature,
  ExteriorAccess,
  ExteriorLandscape,
  GeoJsonGeometry,
  GeoJsonPolygon,
  EliaViewModel,
} from '@/types/elia'

// ---------------------------------------------------------------------------
// 1. Explicit Coordinate Conversions
// ---------------------------------------------------------------------------

/**
 * Forward transformation: Source Cartesian meters -> Three.js world scene coordinates.
 */
export function sourceToScene(
  sourceX: number,
  sourceY: number,
  elevationM = 0,
  origin: [number, number] = [0, 0],
  scale = 1
): [number, number, number] {
  const sceneX = (sourceX - origin[0]) * scale
  const sceneY = elevationM * scale
  const sceneZ = -(sourceY - origin[1]) * scale
  return [sceneX, sceneY, sceneZ]
}

/**
 * Three.js Vector3 helper using sourceToScene.
 */
export function eliaToThree(
  x: number,
  y: number,
  elev = 0,
  origin: [number, number] = [0, 0],
  scale = 1
): THREE.Vector3 {
  const [sx, sy, sz] = sourceToScene(x, y, elev, origin, scale)
  return new THREE.Vector3(sx, sy, sz)
}

/**
 * Inverse transformation: Three.js scene coordinates -> Source Cartesian meters.
 * Defined for future interactive selection and customization.
 */
export function sceneToSource(
  sceneX: number,
  sceneY: number,
  sceneZ: number,
  origin: [number, number] = [0, 0],
  scale = 1
): { sourceX: number; sourceY: number; elevationM: number } {
  const sourceX = sceneX / scale + origin[0]
  const sourceY = -sceneZ / scale + origin[1]
  const elevationM = sceneY / scale
  return { sourceX, sourceY, elevationM }
}

// ---------------------------------------------------------------------------
// 2. Feature Dimension and Gate Deduplication Helpers
// ---------------------------------------------------------------------------

/** Extract [x, y] in meters from an ExteriorFeature. */
export function featureCenter(f: ExteriorFeature): [number, number] | null {
  if (f.position) {
    if (Array.isArray(f.position) && f.position.length >= 2) {
      return [Number(f.position[0]), Number(f.position[1])]
    }
    if (typeof f.position === 'object') {
      const pos = f.position as { x: number; y: number }
      if (typeof pos.x === 'number' && typeof pos.y === 'number') {
        return [pos.x, pos.y]
      }
    }
  }
  const poly = featurePolygonCoordinates(f)
  if (poly && poly[0] && poly[0].length >= 3) {
    const ring = poly[0]
    const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length
    const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length
    return [cx, cy]
  }
  return null
}

/**
 * Read vegetation canopy radius in meters directly from backend object fields.
 * Prefers top-level canopy_radius_m, then dimensions fields.
 */
export function featureCanopyRadius(f: ExteriorFeature): number {
  if (typeof f.canopy_radius_m === 'number' && f.canopy_radius_m > 0) {
    return f.canopy_radius_m
  }
  const dims = f.dimensions ?? {}
  if (typeof dims.canopy_radius_m === 'number') return dims.canopy_radius_m
  if (typeof dims.canopy_width_m === 'number') return dims.canopy_width_m / 2
  if (typeof dims.diameter_m === 'number') return dims.diameter_m / 2
  if (typeof dims.width_m === 'number') return dims.width_m / 2
  return 1.0
}

/**
 * Read feature height in meters directly from backend object fields.
 * Prefers top-level height_m, then dimensions fields.
 */
export function featureHeight(f: ExteriorFeature, fallback = 1.5): number {
  if (typeof f.height_m === 'number' && f.height_m > 0) {
    return f.height_m
  }
  const dims = f.dimensions ?? {}
  if (typeof dims.height_m === 'number') return dims.height_m
  if (typeof dims.height === 'number') return dims.height
  return fallback
}

/**
 * Deduplicate gates using stable identifiers since access.gate may also appear in access.gates.
 */
export function deduplicateGates(access?: ExteriorAccess | null): ExteriorFeature[] {
  if (!access) return []
  const map = new Map<string, ExteriorFeature>()
  if (access.gate && (access.gate.json_id || access.gate.id)) {
    const id = String(access.gate.json_id || access.gate.id)
    map.set(id, access.gate)
  }
  if (Array.isArray(access.gates)) {
    for (const g of access.gates) {
      if (g) {
        const id = String(g.json_id || g.id || `gate_${map.size}`)
        if (!map.has(id)) {
          map.set(id, g)
        }
      }
    }
  }
  return Array.from(map.values())
}

// ---------------------------------------------------------------------------
// 3. Polygon Geometry & Hole Preservation
// ---------------------------------------------------------------------------

/**
 * Normalizes any polygon representation into GeoJSON coordinates: number[][][]
 * [0] = exterior ring, [1..n] = interior rings (holes).
 */
export function normalizePolygonCoordinates(raw: unknown): number[][][] | null {
  if (!raw) return null
  if (typeof raw === 'object' && 'type' in (raw as Record<string, unknown>)) {
    const geo = raw as GeoJsonGeometry
    if (geo.type === 'Polygon' && Array.isArray((geo as any).coordinates)) {
      return (geo as any).coordinates as number[][][]
    }
  }
  if (Array.isArray(raw)) {
    if (raw.length === 0) return null
    // Array of rings: number[][][]
    if (Array.isArray(raw[0]) && raw[0].length > 0 && Array.isArray(raw[0][0])) {
      return raw as number[][][]
    }
    // Single ring: number[][]
    if (Array.isArray(raw[0]) && raw.length >= 3 && typeof raw[0][0] === 'number') {
      return [raw as number[][]]
    }
    // Array of {x, y}
    if (typeof raw[0] === 'object' && raw[0] !== null && 'x' in raw[0]) {
      const ring = (raw as Array<{ x: number; y: number }>).map(p => [Number(p.x), Number(p.y)])
      return [ring]
    }
  }
  return null
}

/** Extract full GeoJSON polygon coordinates (including holes) from an ExteriorFeature. */
export function featurePolygonCoordinates(f: ExteriorFeature): number[][][] | null {
  if (f.geometry) {
    const coords = normalizePolygonCoordinates(f.geometry)
    if (coords) return coords
  }
  if (f.polygon) {
    const coords = normalizePolygonCoordinates(f.polygon)
    if (coords) return coords
  }
  if (f.footprint) {
    const coords = normalizePolygonCoordinates(f.footprint)
    if (coords) return coords
  }
  return null
}

/** Outer ring extractor for backwards compatibility. */
export function polygonRing(f: ExteriorFeature): [number, number][] | null {
  const coords = featurePolygonCoordinates(f)
  if (coords && coords[0] && coords[0].length >= 3) {
    return coords[0] as [number, number][]
  }
  return null
}

export function ringFromGeometry(geo: GeoJsonGeometry): [number, number][] | null {
  const coords = normalizePolygonCoordinates(geo)
  if (coords && coords[0] && coords[0].length >= 3) {
    return coords[0] as [number, number][]
  }
  return null
}

/**
 * Build a THREE.Shape preserving interior holes.
 * Local shape coordinate convention:
 *   u = (sourceX - originX) * scale
 *   v = (sourceY - originY) * scale
 * When mesh is rotated by [-Math.PI / 2, 0, 0]:
 *   sceneX = u, sceneY = extrusion, sceneZ = -v
 */
export function polygonToShape(
  coords: number[][][],
  origin: [number, number] = [0, 0],
  scale = 1
): THREE.Shape | null {
  if (!coords || coords.length === 0 || !coords[0] || coords[0].length < 3) return null

  const outer = coords[0]
  const shape = new THREE.Shape()
  shape.moveTo((outer[0][0] - origin[0]) * scale, (outer[0][1] - origin[1]) * scale)
  for (let i = 1; i < outer.length; i++) {
    shape.lineTo((outer[i][0] - origin[0]) * scale, (outer[i][1] - origin[1]) * scale)
  }
  shape.closePath()

  // Interior rings (holes)
  for (let h = 1; h < coords.length; h++) {
    const holeRing = coords[h]
    if (holeRing && holeRing.length >= 3) {
      const path = new THREE.Path()
      path.moveTo((holeRing[0][0] - origin[0]) * scale, (holeRing[0][1] - origin[1]) * scale)
      for (let j = 1; j < holeRing.length; j++) {
        path.lineTo((holeRing[j][0] - origin[0]) * scale, (holeRing[j][1] - origin[1]) * scale)
      }
      path.closePath()
      shape.holes.push(path)
    }
  }

  return shape
}

/**
 * Build a flat or extruded Three.js BufferGeometry preserving holes.
 */
export function polygonToBufferGeometry(
  coords: number[][][],
  depth = 0,
  origin: [number, number] = [0, 0],
  scale = 1
): THREE.BufferGeometry | null {
  const shape = polygonToShape(coords, origin, scale)
  if (!shape) return null
  if (depth > 0) {
    return new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false })
  }
  return new THREE.ShapeGeometry(shape)
}

/**
 * Build closed line points for all rings (outer boundary + holes).
 * Each loop is an array of THREE.Vector3 points closed back to start.
 */
export function polygonToLineLoops(
  coords: number[][][],
  elev = 0,
  origin: [number, number] = [0, 0],
  scale = 1
): THREE.Vector3[][] {
  if (!coords || coords.length === 0) return []
  const loops: THREE.Vector3[][] = []
  for (const ring of coords) {
    if (ring && ring.length >= 3) {
      const pts = ring.map(([x, y]) => eliaToThree(x, y, elev, origin, scale))
      pts.push(pts[0].clone()) // close
      loops.push(pts)
    }
  }
  return loops
}

// ---------------------------------------------------------------------------
// 4. Bounding Box & Scale Calculations
// ---------------------------------------------------------------------------

export interface BBox {
  minX: number
  maxX: number
  minY: number
  maxY: number
  width: number
  height: number
  cx: number
  cy: number
}

/** Compute bounding box across all rings of a polygon. */
export function polygonBBox(coords: number[][][]): BBox {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const ring of coords) {
    for (const [x, y] of ring) {
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
  }
  if (!isFinite(minX)) {
    return { minX: 0, maxX: 20, minY: 0, maxY: 20, width: 20, height: 20, cx: 10, cy: 10 }
  }
  const width = Math.max(0.1, maxX - minX)
  const height = Math.max(0.1, maxY - minY)
  return { minX, maxX, minY, maxY, width, height, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 }
}

export function ringBBox(ring: [number, number][]): BBox {
  return polygonBBox([ring])
}

export function normScale(bbox: BBox, targetSize = 20): number {
  const longest = Math.max(bbox.width, bbox.height, 1)
  return targetSize / longest
}

// ---------------------------------------------------------------------------
// 5. SVG 2D Plan View Helpers with Hole Support
// ---------------------------------------------------------------------------

/**
 * Produces an SVG path string for a polygon with supported holes.
 * Must be rendered with fillRule="evenodd" so interior holes are subtracted.
 */
export function polygonToSvgPath(coords: number[][][]): string {
  if (!coords || coords.length === 0) return ''
  let d = ''
  for (const ring of coords) {
    if (ring && ring.length >= 3) {
      const [first, ...rest] = ring
      d += `M${first[0].toFixed(2)},${first[1].toFixed(2)} ` +
        rest.map(([x, y]) => `L${x.toFixed(2)},${y.toFixed(2)}`).join(' ') + ' Z '
    }
  }
  return d.trim()
}

// ---------------------------------------------------------------------------
// 6. Upstream Master JSON Normalization & EliaViewModel Derivation
// ---------------------------------------------------------------------------

const UNIT_SCALE_TO_METERS: Record<string, number> = {
  m: 1.0,
  meter: 1.0,
  meters: 1.0,
  ft: 0.3048,
  foot: 0.3048,
  feet: 0.3048,
  cm: 0.01,
}

function resolveUnitScale(masterJson: any): number {
  if (!masterJson || typeof masterJson !== 'object') return 1.0
  const u = masterJson.units || masterJson.land_info?.units || 'm'
  const key = typeof u === 'string' ? u.trim().toLowerCase() : 'm'
  return UNIT_SCALE_TO_METERS[key] ?? 1.0
}

function scalePolygonCoords(coords: number[][][], scale: number): number[][][] {
  if (scale === 1.0) return coords
  return coords.map(ring => ring.map(([x, y]) => [x * scale, y * scale]))
}

/**
 * Extracts and normalizes upstream land and house geometry from the real Master JSON,
 * pairing it with the ELIA proposal into an in-memory EliaViewModel.
 *
 * Rules:
 *   - Normalizes upstream units to meters exactly once.
 *   - Preserves polygon holes.
 *   - Checks revision consistency between Master JSON and candidate metadata.
 *   - Does not duplicate geometry into persisted output.
 *   - Does not mutate the source Master JSON document.
 */
export function extractNormalizedUpstreamGeometry(
  masterJson: any,
  landscape: ExteriorLandscape | null,
  projectId?: string
): EliaViewModel {
  if (!masterJson || typeof masterJson !== 'object') {
    return {
      projectId,
      sourceRevision: null,
      landPolygon: null,
      housePolygon: null,
      buildingHeightM: null,
      isHeightEstimated: true,
      landscape,
      geometryState: 'missing_all',
      geometryMessage: 'No Master JSON project document available.',
    }
  }

  const unitScale = resolveUnitScale(masterJson)
  const sourceRevision = typeof masterJson.revision === 'number' ? masterJson.revision : null

  // Extract raw land geometry from authoritative paths
  const rawLand =
    masterJson.land_boundary_polygon ||
    masterJson.land_info?.mathematical_polygon ||
    masterJson.land_info?.land_boundary_polygon ||
    masterJson.land_info?.boundary_polygon ||
    masterJson.land_info?.boundary_points

  // Extract raw house footprint from authoritative paths
  const rawHouse =
    masterJson.house_exterior_polygon ||
    masterJson.buildable_footprint?.house_exterior_polygon ||
    masterJson.house?.exterior_polygon ||
    masterJson.building_footprint ||
    masterJson.floor_plan?.ground_floor?.house_exterior_polygon ||
    masterJson.floor_plan?.ground_floor?.exterior_polygon

  const landCoords = normalizePolygonCoordinates(rawLand)
  const houseCoords = normalizePolygonCoordinates(rawHouse)

  const landPolygon: GeoJsonPolygon | null = landCoords
    ? { type: 'Polygon', coordinates: scalePolygonCoords(landCoords, unitScale) }
    : null

  const housePolygon: GeoJsonPolygon | null = houseCoords
    ? { type: 'Polygon', coordinates: scalePolygonCoords(houseCoords, unitScale) }
    : null

  // Extract upstream building height if supplied
  let buildingHeightM: number | null = null
  let isHeightEstimated = true
  const bldgExt = masterJson.building_exterior || masterJson.building
  if (bldgExt && typeof bldgExt.height_m === 'number' && bldgExt.height_m > 0) {
    buildingHeightM = bldgExt.height_m
    isHeightEstimated = false
  } else if (bldgExt && typeof bldgExt.height === 'number' && bldgExt.height > 0) {
    buildingHeightM = bldgExt.height * unitScale
    isHeightEstimated = false
  } else {
    buildingHeightM = 3.0 // Explicit display-only default marked as estimated
    isHeightEstimated = true
  }

  // Revision consistency check
  const candidateSourceRev = (landscape as any)?.source_revision ?? (landscape as any)?.meta?.source_revision
  if (
    sourceRevision !== null &&
    typeof candidateSourceRev === 'number' &&
    candidateSourceRev !== sourceRevision
  ) {
    return {
      projectId,
      sourceRevision,
      landPolygon,
      housePolygon,
      buildingHeightM,
      isHeightEstimated,
      landscape,
      geometryState: 'revision_mismatch',
      geometryMessage: `Source revision conflict: candidate was generated against revision ${candidateSourceRev}, but current project revision is ${sourceRevision}.`,
    }
  }

  if (!landPolygon && !housePolygon) {
    return {
      projectId,
      sourceRevision,
      landPolygon: null,
      housePolygon: null,
      buildingHeightM,
      isHeightEstimated,
      landscape,
      geometryState: 'missing_all',
      geometryMessage: 'Site geometry (land boundary and house footprint) is not available from previous components.',
    }
  }

  if (!landPolygon) {
    return {
      projectId,
      sourceRevision,
      landPolygon: null,
      housePolygon,
      buildingHeightM,
      isHeightEstimated,
      landscape,
      geometryState: 'missing_land',
      geometryMessage: 'Land boundary polygon is missing from upstream Master JSON.',
    }
  }

  if (!housePolygon) {
    return {
      projectId,
      sourceRevision,
      landPolygon,
      housePolygon: null,
      buildingHeightM,
      isHeightEstimated,
      landscape,
      geometryState: 'missing_house',
      geometryMessage: 'House exterior footprint is missing from upstream Master JSON.',
    }
  }

  return {
    projectId,
    sourceRevision,
    landPolygon,
    housePolygon,
    buildingHeightM,
    isHeightEstimated,
    landscape,
    geometryState: 'ready',
  }
}
