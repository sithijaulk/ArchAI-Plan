"use client"
/**
 * ExteriorSceneViewer — Three.js / R3F scene for ELIA exterior_landscape data.
 *
 * Renders:
 *   - Land boundary (extruded ground plane)
 *   - House footprint (opaque building box)
 *   - Driveway polygon (flat grey)
 *   - Gate position (vertical orange post)
 *   - Garage polygon (flat navy)
 *   - Vegetation nodes (green cylinders scaled by trunk_diameter / canopy)
 *   - Outdoor lighting nodes (yellow cone + pole)
 *   - Vertical greenery elements (teal flat plane on wall)
 *   - Outdoor elements (small grey boxes)
 *   - North arrow (red arrow in XZ plane)
 *
 * Coordinate system:
 *   ELIA uses flat XY (meters). Three.js uses XZY (Y up).
 *   Conversion: elia(x,y) → three(x, 0, -y).
 *   The scene is normalised so the land fits roughly in a 20-unit cube.
 */
import React, { useMemo, useRef, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid, Text, Html } from '@react-three/drei'
import * as THREE from 'three'
import type { ExteriorFeature, ExteriorLandscape } from '@/types/elia'
import {
  ringToFlatGeometry, ringToLinePoints, ringBBox, normScale,
  featureCenter, polygonRing, ringFromGeometry, eliaToThree,
} from '@/lib/eliaGeometry'

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------
const COLORS = {
  ground: '#1a2a1a',
  groundWire: '#2e4a2e',
  land: '#1e3a1e',
  landEdge: '#4ade80',
  house: '#334155',
  houseEdge: '#94a3b8',
  driveway: '#374151',
  driveWay: '#6b7280',
  garage: '#1e3a5f',
  garageEdge: '#60a5fa',
  gate: '#f97316',
  vegetation: '#16a34a',
  vegetationCanopy: '#22c55e',
  lighting: '#fbbf24',
  lightingPole: '#d97706',
  vertical: '#0d9488',
  outdoor: '#6b7280',
  north: '#ef4444',
} as const

// ---------------------------------------------------------------------------
// Helper: get dimensions from feature
// ---------------------------------------------------------------------------
function featureDims(f: ExteriorFeature): { w: number; h: number; d: number } {
  const dims = f.dimensions ?? {}
  const w = dims.width_m ?? dims.width ?? dims.diameter_m ?? 1
  const h = dims.height_m ?? dims.height ?? 0.5
  const d = dims.depth_m ?? dims.depth ?? dims.diameter_m ?? w
  return { w, h, d }
}

// ---------------------------------------------------------------------------
// Scene content
// ---------------------------------------------------------------------------
interface SceneProps {
  landscape: ExteriorLandscape
  scale: number
  offset: [number, number]
}

function LandPolygon({ landscape, scale, offset }: SceneProps) {
  const geo = useMemo(() => {
    const landGeo = landscape.land ?? (landscape.site_analysis as any)?.land_polygon
    if (!landGeo) return null
    const ring = ringFromGeometry(landGeo as any)
    if (!ring || ring.length < 3) return null
    // normalise & offset
    const normRing = ring.map(([x, y]) => [(x - offset[0]) * scale, (y - offset[1]) * scale] as [number, number])
    return { ring: normRing, linePoints: ringToLinePoints(normRing, 0) }
  }, [landscape, scale, offset])

  if (!geo) return null
  return (
    <group>
      {/* Ground fill */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <primitive object={ringToFlatGeometry(geo.ring)} attach="geometry" />
        <meshStandardMaterial color={COLORS.land} side={THREE.DoubleSide} />
      </mesh>
      {/* Boundary line */}
      <line>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[new Float32Array(geo.linePoints.flatMap(v => [v.x, v.y, v.z])), 3]}
          />
        </bufferGeometry>
        <lineBasicMaterial color={COLORS.landEdge} linewidth={2} />
      </line>
    </group>
  )
}

function HouseBlock({ landscape, scale, offset }: SceneProps) {
  const geo = useMemo(() => {
    const houseGeo = landscape.house_exterior ?? (landscape.site_analysis as any)?.house_polygon
    if (!houseGeo) return null
    const ring = ringFromGeometry(houseGeo as any)
    if (!ring || ring.length < 3) return null
    const normRing = ring.map(([x, y]) => [(x - offset[0]) * scale, (y - offset[1]) * scale] as [number, number])
    return normRing
  }, [landscape, scale, offset])

  const height = 3 * scale // approximate 3 m building height normalised

  if (!geo) return null
  return (
    <group position={[0, 0, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <primitive object={ringToFlatGeometry(geo, height)} attach="geometry" />
        <meshStandardMaterial color={COLORS.house} />
      </mesh>
    </group>
  )
}

function DriveWay({ landscape, scale, offset }: SceneProps) {
  const driveway = landscape.access?.driveway
  const geo = useMemo(() => {
    if (!driveway) return null
    const ring = polygonRing(driveway)
    if (!ring || ring.length < 3) return null
    const normRing = ring.map(([x, y]) => [(x - offset[0]) * scale, (y - offset[1]) * scale] as [number, number])
    return normRing
  }, [driveway, scale, offset])

  if (!geo) return null
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
      <primitive object={ringToFlatGeometry(geo)} attach="geometry" />
      <meshStandardMaterial color={COLORS.driveway} />
    </mesh>
  )
}

function GarageBlock({ landscape, scale, offset }: SceneProps) {
  const garage = landscape.access?.garage
  const geo = useMemo(() => {
    if (!garage) return null
    const ring = polygonRing(garage)
    if (!ring || ring.length < 3) return null
    const normRing = ring.map(([x, y]) => [(x - offset[0]) * scale, (y - offset[1]) * scale] as [number, number])
    return normRing
  }, [garage, scale, offset])

  const height = 2.5 * scale

  if (!geo) return null
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
      <primitive object={ringToFlatGeometry(geo, height)} attach="geometry" />
      <meshStandardMaterial color={COLORS.garage} />
    </mesh>
  )
}

function GatePost({ landscape, scale, offset }: SceneProps) {
  const gates = useMemo(() => {
    const all: ExteriorFeature[] = []
    if (landscape.access?.gate) all.push(landscape.access.gate)
    if (landscape.access?.gates?.length) all.push(...landscape.access.gates)
    return all
  }, [landscape])

  return (
    <>
      {gates.map((gate) => {
        const c = featureCenter(gate)
        if (!c) return null
        const x = (c[0] - offset[0]) * scale
        const z = -(c[1] - offset[1]) * scale
        return (
          <group key={gate.json_id} position={[x, 0, z]}>
            {/* Pole */}
            <mesh position={[0, scale, 0]}>
              <cylinderGeometry args={[0.04 * scale, 0.04 * scale, 2 * scale, 8]} />
              <meshStandardMaterial color={COLORS.gate} />
            </mesh>
            {/* Cap sphere */}
            <mesh position={[0, 2 * scale, 0]}>
              <sphereGeometry args={[0.08 * scale, 8, 8]} />
              <meshStandardMaterial color={COLORS.gate} emissive={COLORS.gate} emissiveIntensity={0.4} />
            </mesh>
          </group>
        )
      })}
    </>
  )
}

function VegetationNodes({ landscape, scale, offset }: SceneProps) {
  return (
    <>
      {landscape.vegetation_nodes?.map((node) => {
        const c = featureCenter(node)
        if (!c) return null
        const x = (c[0] - offset[0]) * scale
        const z = -(c[1] - offset[1]) * scale
        const dims = featureDims(node)
        const r = Math.max(0.3, (dims.w / 2)) * scale
        const h = Math.max(0.5, dims.h) * scale
        return (
          <group key={node.json_id} position={[x, 0, z]}>
            {/* Trunk */}
            <mesh position={[0, h * 0.3, 0]}>
              <cylinderGeometry args={[r * 0.12, r * 0.15, h * 0.6, 6]} />
              <meshStandardMaterial color="#713f12" />
            </mesh>
            {/* Canopy */}
            <mesh position={[0, h * 0.75, 0]}>
              <sphereGeometry args={[r, 6, 6]} />
              <meshStandardMaterial color={COLORS.vegetationCanopy} roughness={0.8} />
            </mesh>
          </group>
        )
      })}
    </>
  )
}

function LightingNodes({ landscape, scale, offset }: SceneProps) {
  return (
    <>
      {landscape.outdoor_lighting?.nodes?.map((node) => {
        const c = featureCenter(node)
        if (!c) return null
        const x = (c[0] - offset[0]) * scale
        const z = -(c[1] - offset[1]) * scale
        const poleH = 3 * scale
        return (
          <group key={node.json_id} position={[x, 0, z]}>
            {/* Pole */}
            <mesh position={[0, poleH / 2, 0]}>
              <cylinderGeometry args={[0.03 * scale, 0.04 * scale, poleH, 6]} />
              <meshStandardMaterial color={COLORS.lightingPole} />
            </mesh>
            {/* Lamp cone */}
            <mesh position={[0, poleH, 0]} rotation={[Math.PI, 0, 0]}>
              <coneGeometry args={[0.15 * scale, 0.25 * scale, 8]} />
              <meshStandardMaterial color={COLORS.lighting} emissive={COLORS.lighting} emissiveIntensity={0.6} />
            </mesh>
            {/* Point light */}
            <pointLight position={[0, poleH, 0]} intensity={1.5} color={COLORS.lighting} distance={8 * scale} decay={2} />
          </group>
        )
      })}
    </>
  )
}

function OutdoorElements({ landscape, scale, offset }: SceneProps) {
  return (
    <>
      {landscape.outdoor_elements?.map((el) => {
        const c = featureCenter(el)
        if (!c) return null
        const x = (c[0] - offset[0]) * scale
        const z = -(c[1] - offset[1]) * scale
        const dims = featureDims(el)
        return (
          <mesh key={el.json_id} position={[x, dims.h * scale * 0.5, z]}>
            <boxGeometry args={[dims.w * scale, dims.h * scale, dims.d * scale]} />
            <meshStandardMaterial color={COLORS.outdoor} roughness={0.9} />
          </mesh>
        )
      })}
    </>
  )
}

function NorthArrow({ northAngle }: { northAngle: number }) {
  // northAngle is degrees CW from local +Y toward +X (ELIA convention)
  // In three.js XZ plane: angle from +Z toward +X.
  const rad = (northAngle * Math.PI) / 180
  const len = 2
  const tip = new THREE.Vector3(Math.sin(rad) * len, 0.1, -Math.cos(rad) * len)
  const base = new THREE.Vector3(0, 0.1, 0)
  const points = [base, tip]
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
      <mesh position={[tip.x, tip.y, tip.z]} rotation={[0, -rad, 0]}>
        <coneGeometry args={[0.15, 0.4, 6]} />
        <meshStandardMaterial color={COLORS.north} />
      </mesh>
    </group>
  )
}

function CameraRig({ center }: { center: THREE.Vector3 }) {
  return (
    <OrbitControls
      target={center}
      enableZoom
      enablePan
      maxPolarAngle={Math.PI / 2 - 0.05}
      minDistance={2}
      maxDistance={60}
    />
  )
}

// ---------------------------------------------------------------------------
// Main scene wrapper
// ---------------------------------------------------------------------------
function SceneContent({ landscape }: { landscape: ExteriorLandscape }) {
  // Compute normalisation from land polygon
  const { scale, offset } = useMemo(() => {
    const landGeo = landscape.land ?? (landscape.site_analysis as any)?.land_polygon
    const ring = landGeo ? ringFromGeometry(landGeo as any) : null
    if (ring && ring.length >= 3) {
      const bbox = ringBBox(ring)
      const s = normScale(bbox, 20)
      return { scale: s, offset: [bbox.cx, bbox.cy] as [number, number] }
    }
    return { scale: 1, offset: [0, 0] as [number, number] }
  }, [landscape])

  const northAngle = landscape.environment?.north_angle ?? 0
  const sceneCenter = new THREE.Vector3(0, 0, 0)

  const props: SceneProps = { landscape, scale, offset }

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 20, 10]} intensity={1.2} castShadow />
      <directionalLight position={[-8, 15, -8]} intensity={0.4} color="#8080ff" />

      {/* Ground grid */}
      <Grid
        infiniteGrid
        fadeDistance={40}
        sectionColor="#1a3a1a"
        cellColor="#0f1f0f"
        position={[0, -0.015, 0]}
      />

      {/* Scene objects */}
      <LandPolygon {...props} />
      <HouseBlock {...props} />
      <DriveWay {...props} />
      <GarageBlock {...props} />
      <GatePost {...props} />
      <VegetationNodes {...props} />
      <LightingNodes {...props} />
      <OutdoorElements {...props} />

      {/* North indicator */}
      <NorthArrow northAngle={northAngle} />

      <CameraRig center={sceneCenter} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Empty / loading states
// ---------------------------------------------------------------------------
function EmptyScene() {
  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} color="#00f0ff" />
      <Grid infiniteGrid fadeDistance={20} sectionColor="#1a2a1a" cellColor="#0f1a0f" />
      <OrbitControls autoRotate autoRotateSpeed={0.3} maxPolarAngle={Math.PI / 2 - 0.05} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------
interface ExteriorSceneViewerProps {
  landscape?: ExteriorLandscape | null
}

export default function ExteriorSceneViewer({ landscape }: ExteriorSceneViewerProps) {
  return (
    <div className="w-full h-full min-h-[480px] relative rounded-lg overflow-hidden bg-[#0a140a]">
      {/* Legend */}
      <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5 text-[10px] font-mono bg-black/50 rounded-lg p-2 backdrop-blur-sm">
        {[
          { color: COLORS.landEdge, label: 'Land boundary' },
          { color: COLORS.houseEdge, label: 'House' },
          { color: COLORS.garageEdge, label: 'Garage' },
          { color: COLORS.gate, label: 'Gate' },
          { color: COLORS.vegetationCanopy, label: 'Vegetation' },
          { color: COLORS.lighting, label: 'Lighting' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: color }} />
            <span className="text-white/70">{label}</span>
          </div>
        ))}
      </div>

      {/* Coordinate reference */}
      {landscape && (
        <div className="absolute bottom-3 left-3 z-10 text-[10px] font-mono text-white/40 max-w-[200px] leading-tight">
          {landscape.coordinate_reference}
        </div>
      )}

      {/* Run mode badge */}
      {landscape?.generation_mode && (
        <div className="absolute top-3 right-3 z-10 text-[10px] font-mono bg-black/50 text-white/60 px-2 py-1 rounded-md backdrop-blur-sm">
          {landscape.generation_mode}
        </div>
      )}

      <Canvas
        camera={{ position: [12, 18, 12], fov: 45, near: 0.1, far: 500 }}
        shadows
        gl={{ antialias: true, alpha: false }}
        onCreated={({ gl }) => { gl.setClearColor('#0a140a') }}
      >
        <Suspense fallback={null}>
          {landscape ? (
            <SceneContent landscape={landscape} />
          ) : (
            <EmptyScene />
          )}
        </Suspense>
      </Canvas>
    </div>
  )
}
