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
import React, { useMemo, Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import * as THREE from 'three'
import type {
  ExteriorFeature,
  ExteriorLandscape,
  EliaViewModel,
  GeoJsonPolygon,
} from '@/types/elia'
import {
  sourceToScene,
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
        const [x, , z] = sourceToScene(c[0], c[1], 0, offset, scale)
        const dims = el.dimensions ?? {}
        const w = (dims.width_m ?? dims.width ?? 1) * scale
        const h = (dims.height_m ?? dims.height ?? 0.5) * scale
        const d = (dims.depth_m ?? dims.depth ?? w) * scale

        return (
          <mesh key={el.json_id} position={[x, h / 2, z]}>
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
// 9. Scene Assembler
// ---------------------------------------------------------------------------
interface ViewerProps {
  viewModel?: EliaViewModel | null
  landscape?: ExteriorLandscape | null
}

function MainScene({
  viewModel,
  landscape,
}: {
  viewModel: EliaViewModel | null
  landscape: ExteriorLandscape | null
}) {
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
  const { scale, offset } = useMemo(() => {
    if (landCoords && landCoords.length > 0) {
      const bbox = polygonBBox(landCoords)
      const s = normScale(bbox, 22)
      return { scale: s, offset: [bbox.cx, bbox.cy] as [number, number] }
    }
    return { scale: 1, offset: [0, 0] as [number, number] }
  }, [landCoords])

  const northAngle = landscape?.environment?.north_angle ?? 0
  const transformProps: SceneTransformProps = { scale, offset }

  return (
    <>
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

      {/* Upstream Base Geometry */}
      <LandPolygonMesh polygon={viewModel?.landPolygon ?? (landCoords ? { type: 'Polygon', coordinates: landCoords } : null)} {...transformProps} />
      <HouseBlockMesh polygon={housePolygon} buildingHeightM={buildingHeightM} {...transformProps} />

      {/* ELIA Proposed Exterior Features */}
      {landscape && (
        <>
          <DrivewayMesh feature={landscape.access?.driveway} {...transformProps} />
          <GarageMesh feature={landscape.access?.garage} {...transformProps} />
          <GatesMesh access={landscape.access} {...transformProps} />
          <VegetationNodesMesh nodes={landscape.vegetation_nodes} {...transformProps} />
          <LightingNodesMesh nodes={landscape.outdoor_lighting?.nodes} {...transformProps} />
          <OutdoorElementsMesh elements={landscape.outdoor_elements} {...transformProps} />
          <VerticalGreeneryMesh elements={landscape.vertical_greenery?.elements} {...transformProps} />
        </>
      )}

      {/* True North Orientation */}
      <NorthIndicator northAngle={northAngle} />

      <OrbitControls
        target={[0, 0, 0]}
        enableZoom
        enablePan
        maxPolarAngle={Math.PI / 2 - 0.05}
        minDistance={2}
        maxDistance={65}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// 10. Public Component Export
// ---------------------------------------------------------------------------
export default function ExteriorSceneViewer({
  viewModel,
  landscape: directLandscape,
}: ViewerProps) {
  const landscape = viewModel?.landscape ?? directLandscape ?? null

  // Check geometry state
  const isMissingGeometry =
    viewModel &&
    (viewModel.geometryState === 'missing_all' ||
      viewModel.geometryState === 'missing_land' ||
      viewModel.geometryState === 'revision_mismatch')

  return (
    <div className="w-full h-full min-h-[480px] relative rounded-lg overflow-hidden bg-[#0a140a]">
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
          <MainScene viewModel={viewModel ?? null} landscape={landscape} />
        </Suspense>
      </Canvas>
    </div>
  )
}
