"use client"
/**
 * ExteriorSceneViewer — Three.js / R3F scene for ELIA exterior_landscape visualization.
 *
 * Strict Coordinate System Mapping:
 *   Local Cartesian meters -> Three.js scene coordinates:
 *     scene X = (source X - origin X) * scale
 *     scene Y = elevation * scale
 *     scene Z = -(source Y - origin Y) * scale
 *   Polygon meshes are defined with shape u = (source X - origin X) * scale,
 *   v = (source Y - origin Y) * scale and rotated by [-π/2, 0, 0].
 *   This ensures polygon fills, extruded volumes, boundary lines, and point objects
 *   coincide with identical sign and orientation. Extrusion extends upward into +Y.
 *
 * Features:
 *   - Upstream land boundary and house footprint rendered with supported interior holes.
 *   - Real vegetation dimensions (height_m, canopy_radius_m) mapped directly from backend.
 *   - Stable gate deduplication (handles access.gate appearing in access.gates).
 *   - Displays clear missing-geometry / revision-mismatch states when input is unavailable.
 *   - Clear distinction between surveyed building heights and display-only approximations.
 */
import React, { useMemo, useState, useRef, useEffect, Suspense } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, OrthographicCamera, PerspectiveCamera, TransformControls } from '@react-three/drei'
import * as THREE from 'three'
import type {
  ExteriorFeature,
  ExteriorLandscape,
  EliaViewModel,
  GeoJsonPolygon,
  GroundSurface,
} from '@/types/elia'
import {
  sourceToScene,
  sceneToSource,
  polygonToBufferGeometry,
  polygonToLineLoops,
  polygonBBox,
  normScale,
  featureCenter,
  featureCanopyRadius,
  featureHeight,
  featurePolygonCoordinates,
  deduplicateGates,
  normalizePolygonCoordinates,
} from '@/lib/eliaGeometry'

// ---------------------------------------------------------------------------
// Color Palette
// ---------------------------------------------------------------------------
const COLORS = {
  ground: '#1a2a1a',
  land: '#1e3a1e',
  landEdge: '#4ade80',
  landHoleEdge: '#22c55e',
  house: '#334155',
  houseEdge: '#94a3b8',
  driveway: '#374151',
  drivewayEdge: '#6b7280',
  garage: '#1e3a5f',
  garageEdge: '#60a5fa',
  gate: '#f97316',
  vegetationTrunk: '#713f12',
  vegetationCanopy: '#22c55e',
  lighting: '#fbbf24',
  lightingPole: '#d97706',
  vertical: '#0d9488',
  outdoor: '#6b7280',
  north: '#ef4444',
  pool: '#0284c7',
  pond: '#0e7490',
  well: '#64748b',
  tap: '#94a3b8',
  boundaryWall: '#475569',
  parkingBay: '#1e293b',
  lawnSurface: '#166534',
  gardenBedSurface: '#78350f',
  pathSurface: '#94a3b8',
  solarPanel: '#1e3a8a',
  solarFrame: '#94a3b8',
  balconyPot: '#c2410c',
  rooftopPlanter: '#78350f',
  rooftopFurniture: '#d97706',
} as const

interface SceneTransformProps {
  scale: number
  offset: [number, number]
}

// ---------------------------------------------------------------------------
// 1. Land Boundary (with hole preservation)
// ---------------------------------------------------------------------------
function LandPolygonMesh({
  polygon,
  scale,
  offset,
}: {
  polygon: GeoJsonPolygon | null
} & SceneTransformProps) {
  const { geometry, lineLoops } = useMemo(() => {
    if (!polygon || !polygon.coordinates || polygon.coordinates.length === 0) {
      return { geometry: null, lineLoops: [] }
    }
    const geom = polygonToBufferGeometry(polygon.coordinates, 0, offset, scale)
    const loops = polygonToLineLoops(polygon.coordinates, 0, offset, scale)
    return { geometry: geom, lineLoops: loops }
  }, [polygon, scale, offset])

  if (!geometry) return null

  return (
    <group>
      {/* Flat ground surface */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <primitive object={geometry} attach="geometry" />
        <meshStandardMaterial color={COLORS.land} side={THREE.DoubleSide} roughness={0.9} />
      </mesh>
      {/* Outer boundary and interior hole lines */}
      {lineLoops.map((pts, i) => (
        <line key={`land-line-${i}`}>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[new Float32Array(pts.flatMap(v => [v.x, v.y, v.z])), 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial
            color={i === 0 ? COLORS.landEdge : COLORS.landHoleEdge}
            linewidth={i === 0 ? 2 : 1.5}
          />
        </line>
      ))}
    </group>
  )
}

// ---------------------------------------------------------------------------
// 2. House Footprint (extruded upward, hole-preserving)
// ---------------------------------------------------------------------------
function HouseBlockMesh({
  polygon,
  buildingHeightM,
  scale,
  offset,
}: {
  polygon: GeoJsonPolygon | null
  buildingHeightM: number
} & SceneTransformProps) {
  const { geometry, baseLoops } = useMemo(() => {
    if (!polygon || !polygon.coordinates || polygon.coordinates.length === 0) {
      return { geometry: null, baseLoops: [] }
    }
    const extrudeDepth = Math.max(0.5, buildingHeightM) * scale
    const geom = polygonToBufferGeometry(polygon.coordinates, extrudeDepth, offset, scale)
    const loops = polygonToLineLoops(polygon.coordinates, 0, offset, scale)
    return { geometry: geom, baseLoops: loops }
  }, [polygon, buildingHeightM, scale, offset])

  if (!geometry) return null

  return (
    <group>
      {/* Extruded house volume */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <primitive object={geometry} attach="geometry" />
        <meshStandardMaterial color={COLORS.house} roughness={0.7} />
      </mesh>
      {/* Footprint outline at ground */}
      {baseLoops.map((pts, i) => (
        <line key={`house-base-${i}`}>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[new Float32Array(pts.flatMap(v => [v.x, v.y, v.z])), 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial color={COLORS.houseEdge} linewidth={2} />
        </line>
      ))}
    </group>
  )
}

// ---------------------------------------------------------------------------
// 3. Driveway & Garage
// ---------------------------------------------------------------------------
function DrivewayMesh({
  feature,
  scale,
  offset,
}: {
  feature?: ExteriorFeature | null
} & SceneTransformProps) {
  const geometry = useMemo(() => {
    if (!feature) return null
    const coords = featurePolygonCoordinates(feature)
    if (!coords) return null
    return polygonToBufferGeometry(coords, 0, offset, scale)
  }, [feature, scale, offset])

  if (!geometry) return null

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
      <primitive object={geometry} attach="geometry" />
      <meshStandardMaterial color={COLORS.driveway} roughness={0.9} />
    </mesh>
  )
}

function GarageMesh({
  feature,
  scale,
  offset,
}: {
  feature?: ExteriorFeature | null
} & SceneTransformProps) {
  const geometry = useMemo(() => {
    if (!feature) return null
    const coords = featurePolygonCoordinates(feature)
    if (!coords) return null
    const h = featureHeight(feature, 2.5) * scale
    return polygonToBufferGeometry(coords, h, offset, scale)
  }, [feature, scale, offset])

  if (!geometry) return null

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.008, 0]}>
      <primitive object={geometry} attach="geometry" />
      <meshStandardMaterial color={COLORS.garage} roughness={0.6} />
    </mesh>
  )
}

// ---------------------------------------------------------------------------
// 4. Gates (deduplicated)
// ---------------------------------------------------------------------------
function GatesMesh({
  access,
  scale,
  offset,
}: {
  access?: ExteriorLandscape['access'] | null
} & SceneTransformProps) {
  const gates = useMemo(() => deduplicateGates(access), [access])

  return (
    <>
      {gates.map((gate, i) => {
        const c = featureCenter(gate)
        if (!c) return null
        const [x, , z] = sourceToScene(c[0], c[1], 0, offset, scale)
        const poleH = 2.0 * scale
        return (
          <group key={String(gate.json_id || (gate as any).id || `gate_${i}`)} position={[x, 0, z]}>
            {/* Gate post */}
            <mesh position={[0, poleH / 2, 0]}>
              <cylinderGeometry args={[0.05 * scale, 0.05 * scale, poleH, 8]} />
              <meshStandardMaterial color={COLORS.gate} />
            </mesh>
            {/* Cap */}
            <mesh position={[0, poleH, 0]}>
              <sphereGeometry args={[0.1 * scale, 8, 8]} />
              <meshStandardMaterial color={COLORS.gate} emissive={COLORS.gate} emissiveIntensity={0.5} />
            </mesh>
          </group>
        )
      })}
    </>
  )
}

// ---------------------------------------------------------------------------
// 5. Vegetation (using real height_m and canopy_radius_m)
// ---------------------------------------------------------------------------
function VegetationNodesMesh({
  nodes,
  scale,
  offset,
}: {
  nodes?: ExteriorFeature[] | null
} & SceneTransformProps) {
  if (!nodes || nodes.length === 0) return null

  return (
    <>
      {nodes.map((node) => {
        const c = featureCenter(node)
        if (!c) return null
        const [x, , z] = sourceToScene(c[0], c[1], 0, offset, scale)
        const r = Math.max(0.3, featureCanopyRadius(node)) * scale
        const h = Math.max(0.5, featureHeight(node, 2.0)) * scale

        return (
          <group key={node.json_id} position={[x, 0, z]}>
            {/* Trunk */}
            <mesh position={[0, h * 0.3, 0]}>
              <cylinderGeometry args={[r * 0.12, r * 0.16, h * 0.6, 6]} />
              <meshStandardMaterial color={COLORS.vegetationTrunk} />
            </mesh>
            {/* Canopy */}
            <mesh position={[0, h * 0.75, 0]}>
              <sphereGeometry args={[r, 7, 7]} />
              <meshStandardMaterial color={COLORS.vegetationCanopy} roughness={0.8} />
            </mesh>
          </group>
        )
      })}
    </>
  )
}

// ---------------------------------------------------------------------------
// 6. Outdoor Lighting
// ---------------------------------------------------------------------------
function LightingNodesMesh({
  nodes,
  scale,
  offset,
}: {
  nodes?: ExteriorFeature[] | null
} & SceneTransformProps) {
  if (!nodes || nodes.length === 0) return null

  return (
    <>
      {nodes.map((node) => {
        const c = featureCenter(node)
        if (!c) return null
        const [x, , z] = sourceToScene(c[0], c[1], 0, offset, scale)
        const poleH = 2.8 * scale

        return (
          <group key={node.json_id} position={[x, 0, z]}>
            {/* Pole */}
            <mesh position={[0, poleH / 2, 0]}>
              <cylinderGeometry args={[0.03 * scale, 0.04 * scale, poleH, 6]} />
              <meshStandardMaterial color={COLORS.lightingPole} />
            </mesh>
            {/* Lamp fixture */}
            <mesh position={[0, poleH, 0]} rotation={[Math.PI, 0, 0]}>
              <coneGeometry args={[0.15 * scale, 0.25 * scale, 8]} />
              <meshStandardMaterial color={COLORS.lighting} emissive={COLORS.lighting} emissiveIntensity={0.6} />
            </mesh>
            <pointLight position={[0, poleH, 0]} intensity={1.5} color={COLORS.lighting} distance={8 * scale} decay={2} />
          </group>
        )
      })}
    </>
  )
}

// ---------------------------------------------------------------------------
// 7. Outdoor Elements & Vertical Greenery
// ---------------------------------------------------------------------------
function GroundSurfacesMesh({
  surfaces,
  scale,
  offset,
}: {
  surfaces?: GroundSurface[] | null
} & SceneTransformProps) {
  if (!surfaces || surfaces.length === 0) return null

  return (
    <>
      {surfaces.map((s) => {
        const coords = s.polygon ? [s.polygon] : normalizePolygonCoordinates(s.geometry)
        if (!coords || coords.length === 0) return null
        const geom = polygonToBufferGeometry(coords, 0, offset, scale)
        if (!geom) return null
        const color =
          s.type === 'lawn'
            ? COLORS.lawnSurface
            : s.type === 'garden_bed'
            ? COLORS.gardenBedSurface
            : s.type === 'pedestrian_path'
            ? COLORS.pathSurface
            : COLORS.driveway
        const yOffset = s.type === 'lawn' ? -0.005 : s.type === 'garden_bed' ? 0.002 : 0.004

        return (
          <mesh key={s.json_id} rotation={[-Math.PI / 2, 0, 0]} position={[0, yOffset, 0]}>
            <primitive object={geom} attach="geometry" />
            <meshStandardMaterial color={color} roughness={0.8} />
          </mesh>
        )
      })}
    </>
  )
}

function OutdoorElementsMesh({
  elements,
  scale,
  offset,
}: {
  elements?: ExteriorFeature[] | null
} & SceneTransformProps) {
  if (!elements || elements.length === 0) return null

  return (
    <>
      {elements.map((el) => {
        const c = featureCenter(el)
        if (!c) return null
        const elev = typeof el.elevation_m === 'number' ? el.elevation_m : 0
        const [x, y, z] = sourceToScene(c[0], c[1], elev, offset, scale)
        const dims = el.dimensions ?? {}
        const w = (dims.width_m ?? dims.width ?? 1) * scale
        const h = (dims.height_m ?? dims.height ?? 0.5) * scale
        const d = (dims.length_m ?? dims.depth_m ?? dims.depth ?? w) * scale

        if (el.type === 'solar_panel_array' || el.type === 'solar_panel') {
          // If el.modules contains individual panel placements, render each faithfully
          const modules = Array.isArray((el as any).modules) ? (el as any).modules : []
          if (modules.length > 0) {
            return (
              <group key={el.json_id}>
                {modules.map((mod: any, mIdx: number) => {
                  const modCenter = mod.center || [0, 0]
                  const modElev = typeof mod.elevation_m === 'number' ? mod.elevation_m : elev
                  const [mx, my, mz] = sourceToScene(modCenter[0], modCenter[1], modElev, offset, scale)
                  const modDims = mod.dimensions || {}
                  const mw = (modDims.width_m ?? 1.1) * scale
                  const ml = (modDims.length_m ?? modDims.depth_m ?? 1.8) * scale
                  const mh = (modDims.height_m ?? 0.04) * scale
                  const tiltDeg = typeof mod.tilt_degrees === 'number' ? mod.tilt_degrees : (typeof el.tilt_degrees === 'number' ? el.tilt_degrees : 15)
                  const azDeg = typeof mod.azimuth_degrees === 'number' ? mod.azimuth_degrees : (typeof el.azimuth_degrees === 'number' ? el.azimuth_degrees : 180)
                  const tiltRad = (tiltDeg * Math.PI) / 180
                  const azRad = ((azDeg - 180) * Math.PI) / 180

                  return (
                    <group key={mod.id ?? `${el.json_id}-mod-${mIdx}`} position={[mx, my + 0.02 * scale, mz]}>
                      <mesh rotation={[-tiltRad, -azRad, 0]}>
                        <boxGeometry args={[mw, mh, ml]} />
                        <meshStandardMaterial color={COLORS.solarPanel} roughness={0.2} metalness={0.7} />
                      </mesh>
                    </group>
                  )
                })}
              </group>
            )
          }

          // Fallback legacy bounding box: read length_m directly, do not substitute width
          const tiltDeg = typeof el.tilt_degrees === 'number' ? el.tilt_degrees : 15
          const tiltRad = (tiltDeg * Math.PI) / 180
          const azDeg = typeof el.azimuth_degrees === 'number' ? el.azimuth_degrees : (typeof el.rotation_degrees === 'number' ? el.rotation_degrees : 180)
          const azRad = ((azDeg - 180) * Math.PI) / 180
          return (
            <group key={el.json_id} position={[x, y + 0.05 * scale, z]}>
              <mesh rotation={[-tiltRad, -azRad, 0]}>
                <boxGeometry args={[w, 0.04 * scale, d]} />
                <meshStandardMaterial color={COLORS.solarPanel} roughness={0.2} metalness={0.7} />
              </mesh>
            </group>
          )
        }
        if (el.type === 'balcony_pot') {
          return (
            <group key={el.json_id} position={[x, y, z]}>
              <mesh position={[0, h / 2, 0]}>
                <cylinderGeometry args={[w / 2, (w / 2) * 0.7, h, 8]} />
                <meshStandardMaterial color={COLORS.balconyPot} roughness={0.7} />
              </mesh>
              <mesh position={[0, h * 0.9, 0]}>
                <sphereGeometry args={[w * 0.5, 6, 6]} />
                <meshStandardMaterial color={COLORS.vegetationCanopy} roughness={0.8} />
              </mesh>
            </group>
          )
        }
        if (el.type === 'rooftop_planter') {
          return (
            <group key={el.json_id} position={[x, y, z]}>
              <mesh position={[0, h / 2, 0]}>
                <boxGeometry args={[w, h, d]} />
                <meshStandardMaterial color={COLORS.rooftopPlanter} roughness={0.8} />
              </mesh>
              <mesh position={[0, h + 0.08 * scale, 0]}>
                <boxGeometry args={[w * 0.9, 0.16 * scale, d * 0.9]} />
                <meshStandardMaterial color={COLORS.vegetationCanopy} roughness={0.85} />
              </mesh>
            </group>
          )
        }
        if (el.type === 'rooftop_table_set' || el.type === 'balcony_seating') {
          return (
            <mesh key={el.json_id} position={[x, y + h / 2, z]}>
              <boxGeometry args={[w, h, d]} />
              <meshStandardMaterial color={COLORS.rooftopFurniture} roughness={0.6} />
            </mesh>
          )
        }
        if (el.type === 'swimming_pool') {
          return (
            <mesh key={el.json_id} position={[x, 0.02, z]}>
              <boxGeometry args={[w, 0.04, d]} />
              <meshStandardMaterial color={COLORS.pool} roughness={0.15} metalness={0.1} />
            </mesh>
          )
        }
        if (el.type === 'garden_pond') {
          return (
            <mesh key={el.json_id} position={[x, 0.02, z]}>
              <boxGeometry args={[w, 0.04, d]} />
              <meshStandardMaterial color={COLORS.pond} roughness={0.2} metalness={0.2} />
            </mesh>
          )
        }
        if (el.type === 'water_well') {
          const r = (w / 2) || 0.8 * scale
          return (
            <group key={el.json_id} position={[x, 0, z]}>
              <mesh position={[0, 0.4 * scale, 0]}>
                <cylinderGeometry args={[r, r, 0.8 * scale, 12]} />
                <meshStandardMaterial color={COLORS.well} roughness={0.9} />
              </mesh>
            </group>
          )
        }
        if (el.type === 'garden_tap') {
          return (
            <group key={el.json_id} position={[x, 0, z]}>
              <mesh position={[0, 0.45 * scale, 0]}>
                <cylinderGeometry args={[0.04 * scale, 0.04 * scale, 0.9 * scale, 6]} />
                <meshStandardMaterial color={COLORS.tap} metalness={0.8} roughness={0.3} />
              </mesh>
            </group>
          )
        }
        if (el.type === 'parking_bay') {
          return (
            <mesh key={el.json_id} position={[x, 0.01, z]}>
              <boxGeometry args={[w, 0.02, d]} />
              <meshStandardMaterial color={COLORS.parkingBay} roughness={0.9} />
            </mesh>
          )
        }
        if (el.type === 'boundary_wall') {
          const coords = featurePolygonCoordinates(el)
          if (coords) {
            const wallH = (el.height_m ?? 1.8) * scale
            const geom = polygonToBufferGeometry(coords, wallH, offset, scale)
            if (geom) {
              return (
                <mesh key={el.json_id} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
                  <primitive object={geom} attach="geometry" />
                  <meshStandardMaterial color={COLORS.boundaryWall} roughness={0.9} />
                </mesh>
              )
            }
          }
        }

        return (
          <mesh key={el.json_id} position={[x, y + h / 2, z]}>
            <boxGeometry args={[w, h, d]} />
            <meshStandardMaterial color={COLORS.outdoor} roughness={0.8} />
          </mesh>
        )
      })}
    </>
  )
}

function VerticalGreeneryMesh({
  elements,
  scale,
  offset,
}: {
  elements?: ExteriorFeature[] | null
} & SceneTransformProps) {
  if (!elements || elements.length === 0) return null

  return (
    <>
      {elements.map((el) => {
        const c = featureCenter(el)
        if (!c) return null
        const elev = typeof el.elevation_m === 'number' ? el.elevation_m : 2.5
        const [x, y, z] = sourceToScene(c[0], c[1], elev, offset, scale)
        const s = 0.6 * scale

        return (
          <mesh key={el.json_id} position={[x, y, z]}>
            <boxGeometry args={[s, s, 0.1 * scale]} />
            <meshStandardMaterial color={COLORS.vertical} roughness={0.5} />
          </mesh>
        )
      })}
    </>
  )
}

// ---------------------------------------------------------------------------
// 8. North Direction Indicator
// ---------------------------------------------------------------------------
function NorthIndicator({
  northAngle,
}: {
  northAngle: number
}) {
  // Convention: northAngle is degrees clockwise from local +Y toward +X.
  // In source space: vector to North is (sin θ, cos θ).
  // In Three.js scene: scene X = sin θ, scene Z = -cos θ.
  const rad = (northAngle * Math.PI) / 180
  const len = 2.2
  const tipX = Math.sin(rad) * len
  const tipZ = -Math.cos(rad) * len

  const points = [new THREE.Vector3(0, 0.1, 0), new THREE.Vector3(tipX, 0.1, tipZ)]

  return (
    <group position={[-8, 0, -8]}>
      <line>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[new Float32Array(points.flatMap(v => [v.x, v.y, v.z])), 3]}
          />
        </bufferGeometry>
        <lineBasicMaterial color={COLORS.north} linewidth={3} />
      </line>
      <mesh position={[tipX, 0.1, tipZ]} rotation={[0, -rad, 0]}>
        <coneGeometry args={[0.2, 0.45, 6]} />
        <meshStandardMaterial color={COLORS.north} />
      </mesh>
    </group>
  )
}

// ---------------------------------------------------------------------------
// 9. Interactive 3D Candidate Gizmo
// ---------------------------------------------------------------------------
function SelectedFeatureGizmo({
  featureId,
  landscape,
  scale,
  offset,
  controlsRef,
  gizmoMode = 'translate',
  onFeatureMoved,
  onFeatureRotated,
  onFeatureScaled,
}: {
  featureId: string
  landscape: ExteriorLandscape
  scale: number
  offset: [number, number]
  controlsRef: React.MutableRefObject<any>
  gizmoMode?: 'translate' | 'rotate' | 'scale'
  onFeatureMoved?: (id: string, pos: [number, number]) => void
  onFeatureRotated?: (id: string, angleDeg: number) => void
  onFeatureScaled?: (id: string, factor: number) => void
}) {
  const targetGroupRef = useRef<THREE.Group>(null)
  const transformRef = useRef<any>(null)

  // Find candidate feature
  const feature = useMemo(() => {
    for (const v of landscape.vegetation_nodes ?? []) {
      if (v.json_id === featureId) {
        const pos = Array.isArray(v.position) ? v.position : [(v.position as any)?.x, (v.position as any)?.y]
        return { id: v.json_id, type: 'vegetation', pos, elev: (v as any).elevation_m ?? 0 }
      }
    }
    for (const l of landscape.outdoor_lighting?.nodes ?? []) {
      if (l.json_id === featureId) {
        const pos = Array.isArray(l.position) ? l.position : [(l.position as any)?.x, (l.position as any)?.y]
        return { id: l.json_id, type: 'lighting', pos, elev: (l as any).elevation_m ?? 0 }
      }
    }
    for (const o of landscape.outdoor_elements ?? []) {
      if (o.json_id === featureId) {
        const c = featureCenter(o)
        return { id: o.json_id, type: o.type, pos: c, elev: typeof o.elevation_m === 'number' ? o.elevation_m : 0 }
      }
    }
    return null
  }, [featureId, landscape])

  // Sync position when selection changes
  useEffect(() => {
    if (targetGroupRef.current && feature?.pos) {
      const [sx, sy, sz] = sourceToScene(feature.pos[0], feature.pos[1], feature.elev, offset, scale)
      targetGroupRef.current.position.set(sx, sy, sz)
      targetGroupRef.current.rotation.set(0, 0, 0)
      targetGroupRef.current.scale.set(1, 1, 1)
    }
  }, [feature, offset, scale])

  useEffect(() => {
    const controls = transformRef.current
    if (!controls) return

    const handleDraggingChanged = (event: any) => {
      if (controlsRef.current) {
        controlsRef.current.enabled = !event.value
      }
      if (!event.value && targetGroupRef.current && feature) {
        if (gizmoMode === 'translate' && onFeatureMoved) {
          const { sourceX, sourceY } = sceneToSource(
            targetGroupRef.current.position.x,
            targetGroupRef.current.position.y,
            targetGroupRef.current.position.z,
            offset,
            scale
          )
          onFeatureMoved(feature.id, [
            Math.round(sourceX * 100) / 100,
            Math.round(sourceY * 100) / 100,
          ])
        } else if (gizmoMode === 'rotate' && onFeatureRotated) {
          const angleDeg = Math.round((-targetGroupRef.current.rotation.y * 180 / Math.PI) % 360)
          const normalizedAngle = (angleDeg + 360) % 360
          onFeatureRotated(feature.id, normalizedAngle)
          targetGroupRef.current.rotation.set(0, 0, 0)
        } else if (gizmoMode === 'scale' && onFeatureScaled) {
          const factor = (targetGroupRef.current.scale.x + targetGroupRef.current.scale.z) / 2
          onFeatureScaled(feature.id, Math.round(factor * 100) / 100)
          targetGroupRef.current.scale.set(1, 1, 1)
        }
      }
    }

    controls.addEventListener('dragging-changed', handleDraggingChanged)
    return () => {
      controls.removeEventListener('dragging-changed', handleDraggingChanged)
    }
  }, [controlsRef, onFeatureMoved, onFeatureRotated, onFeatureScaled, gizmoMode, feature, offset, scale])

  if (!feature || !feature.pos) return null

  const [initialX, initialY, initialZ] = sourceToScene(
    feature.pos[0],
    feature.pos[1],
    feature.elev,
    offset,
    scale
  )

  return (
    <TransformControls
      ref={transformRef}
      mode={gizmoMode}
      showX={gizmoMode !== 'rotate'}
      showZ={gizmoMode !== 'rotate'}
      showY={gizmoMode === 'rotate'}
      size={0.65}
    >
      <group ref={targetGroupRef} position={[initialX, initialY, initialZ]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
          <ringGeometry args={[0.35 * scale, 0.45 * scale, 16]} />
          <meshBasicMaterial color="#3b82f6" side={THREE.DoubleSide} />
        </mesh>
      </group>
    </TransformControls>
  )
}

// ---------------------------------------------------------------------------
// 10. Camera Controller (True Orthographic Presets & Repeated Reset)
// ---------------------------------------------------------------------------
export type CameraPreset = 'perspective' | 'top' | 'front' | 'back' | 'left' | 'right'

function CameraController({
  preset,
  sceneRadius,
  resetCount,
  controlsRef,
  orthoZoom,
}: {
  preset: CameraPreset
  sceneRadius: number
  resetCount: number
  controlsRef: React.MutableRefObject<any>
  orthoZoom: number
}) {
  const { camera } = useThree()

  useEffect(() => {
    const dist = Math.max(16, sceneRadius * 1.8)
    const target = new THREE.Vector3(0, 0, 0)

    if (controlsRef.current) {
      controlsRef.current.target.copy(target)
    }

    if (preset === 'perspective') {
      camera.position.set(dist * 0.7, dist * 0.85, dist * 0.7)
      camera.up.set(0, 1, 0)
      camera.lookAt(target)
    } else {
      // Orthographic Presets
      if ('zoom' in camera) {
        (camera as THREE.OrthographicCamera).zoom = orthoZoom
        camera.updateProjectionMatrix()
      }
      if (preset === 'top') {
        // True Top Plan View (North Up) looking down -Y
        camera.position.set(0, 120, 0)
        camera.up.set(0, 0, -1)
        camera.lookAt(target)
      } else if (preset === 'front') {
        // Front Elevation (South looking North along -Z)
        camera.position.set(0, 0, 120)
        camera.up.set(0, 1, 0)
        camera.lookAt(target)
      } else if (preset === 'back') {
        // Back Elevation (North looking South along +Z)
        camera.position.set(0, 0, -120)
        camera.up.set(0, 1, 0)
        camera.lookAt(target)
      } else if (preset === 'left') {
        // Left Elevation (West looking East along +X)
        camera.position.set(-120, 0, 0)
        camera.up.set(0, 1, 0)
        camera.lookAt(target)
      } else if (preset === 'right') {
        // Right Elevation (East looking West along -X)
        camera.position.set(120, 0, 0)
        camera.up.set(0, 1, 0)
        camera.lookAt(target)
      }
    }

    if (controlsRef.current) {
      controlsRef.current.update()
    }
  }, [preset, sceneRadius, resetCount, camera, controlsRef, orthoZoom])

  return null
}

interface ViewerProps {
  viewModel?: EliaViewModel | null
  landscape?: ExteriorLandscape | null
  selectedFeatureId?: string | null
  gizmoMode?: 'translate' | 'rotate' | 'scale'
  onGizmoModeChange?: (mode: 'translate' | 'rotate' | 'scale') => void
  onFeatureMoved?: (id: string, pos: [number, number]) => void
  onFeatureRotated?: (id: string, angleDeg: number) => void
  onFeatureScaled?: (id: string, factor: number) => void
  lockedFeatureIds?: string[]
}

function MainScene({
  viewModel,
  landscape,
  cameraPreset,
  resetCount,
  controlsRef,
  selectedFeatureId,
  gizmoMode = 'translate',
  onFeatureMoved,
  onFeatureRotated,
  onFeatureScaled,
  lockedFeatureIds,
}: {
  viewModel: EliaViewModel | null
  landscape: ExteriorLandscape | null
  cameraPreset: CameraPreset
  resetCount: number
  controlsRef: React.MutableRefObject<any>
  selectedFeatureId?: string | null
  gizmoMode?: 'translate' | 'rotate' | 'scale'
  onFeatureMoved?: (id: string, pos: [number, number]) => void
  onFeatureRotated?: (id: string, angleDeg: number) => void
  onFeatureScaled?: (id: string, factor: number) => void
  lockedFeatureIds?: string[]
}) {
  const { size } = useThree()

  // Determine land coordinates: prefer viewModel authoritative geometry
  const landCoords = useMemo(() => {
    if (viewModel?.landPolygon?.coordinates) {
      return viewModel.landPolygon.coordinates
    }
    if (landscape?.land) {
      return normalizePolygonCoordinates(landscape.land)
    }
    return null
  }, [viewModel, landscape])

  const housePolygon = viewModel?.housePolygon ?? (landscape?.house_exterior ? { type: 'Polygon', coordinates: normalizePolygonCoordinates(landscape.house_exterior) ?? [] } as GeoJsonPolygon : null)
  const buildingHeightM = viewModel?.buildingHeightM ?? 3.0

  // Calculate bounding box and scale from authoritative land boundary
  const { scale, offset, sceneRadius } = useMemo(() => {
    if (landCoords && landCoords.length > 0) {
      const bbox = polygonBBox(landCoords)
      const s = normScale(bbox, 22)
      const radius = (Math.max(bbox.width, bbox.height) / 2) * s
      return { scale: s, offset: [bbox.cx, bbox.cy] as [number, number], sceneRadius: radius }
    }
    return { scale: 1, offset: [0, 0] as [number, number], sceneRadius: 15 }
  }, [landCoords])

  const northAngle = landscape?.environment?.north_angle ?? 0
  const transformProps: SceneTransformProps = { scale, offset }

  // Orthographic zoom calibrated to canvas viewport dimensions and scene bounds
  const orthoZoom = useMemo(() => {
    const minDim = Math.min(size.width, size.height)
    return Math.max(1, (minDim * 0.85) / Math.max(1, sceneRadius * 2.2))
  }, [size.width, size.height, sceneRadius])

  const isEditable = selectedFeatureId && !lockedFeatureIds?.includes(selectedFeatureId)

  return (
    <>
      <PerspectiveCamera
        makeDefault={cameraPreset === 'perspective'}
        fov={45}
        near={0.1}
        far={600}
      />
      <OrthographicCamera
        makeDefault={cameraPreset !== 'perspective'}
        near={-300}
        far={600}
        zoom={orthoZoom}
      />

      <CameraController
        preset={cameraPreset}
        sceneRadius={sceneRadius}
        resetCount={resetCount}
        controlsRef={controlsRef}
        orthoZoom={orthoZoom}
      />

      <ambientLight intensity={0.65} />
      <directionalLight position={[12, 22, 10]} intensity={1.3} castShadow />
      <directionalLight position={[-10, 16, -10]} intensity={0.35} color="#85929e" />

      {/* Reference grid */}
      <Grid
        infiniteGrid
        fadeDistance={45}
        sectionColor="#1a3a1a"
        cellColor="#0e1f0e"
        position={[0, -0.015, 0]}
      />

      {/* Upstream Base Geometry (Read-only) */}
      <LandPolygonMesh polygon={viewModel?.landPolygon ?? (landCoords ? { type: 'Polygon', coordinates: landCoords } : null)} {...transformProps} />
      <HouseBlockMesh polygon={housePolygon} buildingHeightM={buildingHeightM} {...transformProps} />

      {/* ELIA Proposed Exterior Features */}
      {landscape && (
        <>
          <GroundSurfacesMesh surfaces={landscape.ground_surfaces} {...transformProps} />
          <DrivewayMesh feature={landscape.access?.driveway} {...transformProps} />
          <GarageMesh feature={landscape.access?.garage} {...transformProps} />
          <GatesMesh access={landscape.access} {...transformProps} />
          <VegetationNodesMesh nodes={landscape.vegetation_nodes} {...transformProps} />
          <LightingNodesMesh nodes={landscape.outdoor_lighting?.nodes} {...transformProps} />
          <OutdoorElementsMesh elements={landscape.outdoor_elements} {...transformProps} />
          <VerticalGreeneryMesh elements={landscape.vertical_greenery?.elements} {...transformProps} />
        </>
      )}

      {/* 3D Transform Gizmo for active candidate editing */}
      {landscape && isEditable && (
        <SelectedFeatureGizmo
          featureId={selectedFeatureId}
          landscape={landscape}
          scale={scale}
          offset={offset}
          controlsRef={controlsRef}
          gizmoMode={gizmoMode}
          onFeatureMoved={onFeatureMoved}
          onFeatureRotated={onFeatureRotated}
          onFeatureScaled={onFeatureScaled}
        />
      )}

      {/* True North Orientation */}
      <NorthIndicator northAngle={northAngle} />

      <OrbitControls
        ref={controlsRef}
        target={[0, 0, 0]}
        enableZoom
        enablePan
        enableRotate={cameraPreset === 'perspective'}
        maxPolarAngle={cameraPreset === 'top' ? Math.PI : Math.PI / 2 - 0.02}
        minDistance={2}
        maxDistance={250}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// 11. Public Component Export
// ---------------------------------------------------------------------------
export default function ExteriorSceneViewer({
  viewModel,
  landscape: directLandscape,
  selectedFeatureId,
  gizmoMode: externalGizmoMode,
  onGizmoModeChange,
  onFeatureMoved,
  onFeatureRotated,
  onFeatureScaled,
  lockedFeatureIds,
}: ViewerProps) {
  const landscape = viewModel?.landscape ?? directLandscape ?? null
  const [cameraPreset, setCameraPreset] = useState<CameraPreset>('perspective')
  const [internalGizmoMode, setInternalGizmoMode] = useState<'translate' | 'rotate' | 'scale'>('translate')
  const [resetCount, setResetCount] = useState<number>(0)
  const controlsRef = useRef<any>(null)

  const activeGizmoMode = externalGizmoMode ?? internalGizmoMode
  const handleGizmoMode = onGizmoModeChange ?? setInternalGizmoMode

  // Check geometry state
  const isMissingGeometry =
    viewModel &&
    (viewModel.geometryState === 'missing_all' ||
      viewModel.geometryState === 'missing_land' ||
      viewModel.geometryState === 'revision_mismatch')

  return (
    <div className="w-full h-full min-h-[480px] relative rounded-lg overflow-hidden bg-[#0a140a]">
      {/* 3D Camera Controls Toolbar */}
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 bg-black/70 backdrop-blur-md p-1 rounded-lg border border-white/10 text-[11px] font-mono text-white/80">
        <button
          type="button"
          onClick={() => setCameraPreset('perspective')}
          className={`px-2 py-0.5 rounded transition-colors ${cameraPreset === 'perspective' ? 'bg-primary text-primary-foreground font-semibold' : 'hover:bg-white/10'}`}
          title="3D Perspective Orbit Mode"
        >
          3D Orbit
        </button>
        <button
          type="button"
          onClick={() => setCameraPreset('top')}
          className={`px-2 py-0.5 rounded transition-colors ${cameraPreset === 'top' ? 'bg-primary text-primary-foreground font-semibold' : 'hover:bg-white/10'}`}
          title="Top Plan Orthographic View (North Up)"
        >
          Top Plan
        </button>
        <button
          type="button"
          onClick={() => setCameraPreset('front')}
          className={`px-2 py-0.5 rounded transition-colors ${cameraPreset === 'front' ? 'bg-primary text-primary-foreground font-semibold' : 'hover:bg-white/10'}`}
          title="Front Orthographic Elevation (South Looking North)"
        >
          Front (S)
        </button>
        <button
          type="button"
          onClick={() => setCameraPreset('back')}
          className={`px-2 py-0.5 rounded transition-colors ${cameraPreset === 'back' ? 'bg-primary text-primary-foreground font-semibold' : 'hover:bg-white/10'}`}
          title="Back Orthographic Elevation (North Looking South)"
        >
          Back (N)
        </button>
        <button
          type="button"
          onClick={() => setCameraPreset('left')}
          className={`px-2 py-0.5 rounded transition-colors ${cameraPreset === 'left' ? 'bg-primary text-primary-foreground font-semibold' : 'hover:bg-white/10'}`}
          title="Left Orthographic Elevation (West Looking East)"
        >
          Left (W)
        </button>
        <button
          type="button"
          onClick={() => setCameraPreset('right')}
          className={`px-2 py-0.5 rounded transition-colors ${cameraPreset === 'right' ? 'bg-primary text-primary-foreground font-semibold' : 'hover:bg-white/10'}`}
          title="Right Orthographic Elevation (East Looking West)"
        >
          Right (E)
        </button>
        <div className="w-[1px] h-3 bg-white/20 mx-0.5" />
        <button
          type="button"
          onClick={() => {
            setResetCount((c) => c + 1)
          }}
          className="px-2 py-0.5 rounded hover:bg-white/10 text-muted-foreground hover:text-white transition-colors"
          title="Reset Camera Framing (Works repeatedly)"
        >
          Fit / Reset
        </button>

        {/* Gizmo Transform Mode Selector when an item is selected */}
        {selectedFeatureId && (
          <>
            <div className="w-[1px] h-3 bg-white/20 mx-0.5" />
            <span className="text-[10px] text-white/50 pl-0.5">Gizmo:</span>
            <button
              type="button"
              onClick={() => handleGizmoMode('translate')}
              className={`px-2 py-0.5 rounded transition-colors ${activeGizmoMode === 'translate' ? 'bg-blue-600 text-white font-semibold' : 'hover:bg-white/10 text-white/70'}`}
              title="Translate / Move Object (X/Z plane)"
            >
              Move
            </button>
            <button
              type="button"
              onClick={() => handleGizmoMode('rotate')}
              className={`px-2 py-0.5 rounded transition-colors ${activeGizmoMode === 'rotate' ? 'bg-blue-600 text-white font-semibold' : 'hover:bg-white/10 text-white/70'}`}
              title="Rotate Object (Azimuth Yaw around Y)"
            >
              Rotate
            </button>
            <button
              type="button"
              onClick={() => handleGizmoMode('scale')}
              className={`px-2 py-0.5 rounded transition-colors ${activeGizmoMode === 'scale' ? 'bg-blue-600 text-white font-semibold' : 'hover:bg-white/10 text-white/70'}`}
              title="Scale / Resize Dimensions"
            >
              Scale
            </button>
          </>
        )}
      </div>

      {/* Legend */}
      <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5 text-[10px] font-mono bg-black/60 rounded-lg p-2.5 backdrop-blur-sm border border-white/10">
        {[
          { color: COLORS.landEdge, label: 'Land boundary' },
          { color: COLORS.houseEdge, label: 'House footprint' },
          { color: COLORS.driveway, label: 'Driveway' },
          { color: COLORS.garageEdge, label: 'Garage' },
          { color: COLORS.gate, label: 'Gate' },
          { color: COLORS.vegetationCanopy, label: 'Vegetation' },
          { color: COLORS.lighting, label: 'Lighting' },
          { color: COLORS.vertical, label: 'Vertical greenery' },
          { color: COLORS.solarPanel, label: 'Solar PV modules' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: color }} />
            <span className="text-white/80">{label}</span>
          </div>
        ))}
      </div>

      {/* Building height status banner */}
      {viewModel && (
        <div className="absolute top-3 right-3 z-10 flex flex-col items-end gap-1 text-[10px] font-mono">
          {viewModel.isHeightEstimated ? (
            <div className="bg-amber-950/80 border border-amber-600/30 text-amber-200 px-2 py-1 rounded-md backdrop-blur-sm">
              Height ~{viewModel.buildingHeightM?.toFixed(1)}m (display estimate)
            </div>
          ) : (
            <div className="bg-emerald-950/80 border border-emerald-600/30 text-emerald-200 px-2 py-1 rounded-md backdrop-blur-sm">
              Height {viewModel.buildingHeightM?.toFixed(1)}m (surveyed)
            </div>
          )}
          {landscape?.generation_mode && (
            <div className="bg-black/60 border border-white/10 text-white/70 px-2 py-1 rounded-md backdrop-blur-sm">
              {landscape.generation_mode}
            </div>
          )}
        </div>
      )}

      {/* Coordinate reference banner */}
      <div className="absolute bottom-3 left-3 z-10 text-[10px] font-mono text-white/50 max-w-[280px] leading-tight">
        Local Cartesian meters · Y up · North clockwise from +Y toward +X
      </div>

      {/* Missing Geometry / Revision Mismatch Overlay */}
      {isMissingGeometry && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/75 backdrop-blur-sm p-6 text-center">
          <div className="max-w-md space-y-3">
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

      <Canvas
        camera={{ position: [14, 20, 14], fov: 45, near: 0.1, far: 600 }}
        shadows
        gl={{ antialias: true, alpha: false }}
        onCreated={({ gl }) => {
          gl.setClearColor('#0a140a')
        }}
      >
        <Suspense fallback={null}>
          <MainScene
            viewModel={viewModel ?? null}
            landscape={landscape}
            cameraPreset={cameraPreset}
            resetCount={resetCount}
            controlsRef={controlsRef}
            selectedFeatureId={selectedFeatureId}
            gizmoMode={activeGizmoMode}
            onFeatureMoved={onFeatureMoved}
            onFeatureRotated={onFeatureRotated}
            onFeatureScaled={onFeatureScaled}
            lockedFeatureIds={lockedFeatureIds}
          />
        </Suspense>
      </Canvas>
    </div>
  )
}
