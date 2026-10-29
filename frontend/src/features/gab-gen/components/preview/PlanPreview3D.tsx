"use client";

import React, { useRef, useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Html } from '@react-three/drei';
import * as THREE from 'three';
import { Eye, RotateCcw, RotateCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { WebGLErrorBoundary } from '@/components/visualization/WebGLErrorBoundary';
import { GabGenMasterJson, Point2D, FloorPlan } from '../../types';

interface PlanPreview3DProps {
  data: GabGenMasterJson | null;
  selectedFloorIndex: number | 'all';
  explodedMode?: boolean;
}

const BuildingScene: React.FC<{
  data: GabGenMasterJson;
  selectedFloorIndex: number | 'all';
  explodedMode: boolean;
}> = ({ data, selectedFloorIndex, explodedMode }) => {
  const landPoly = useMemo(() => data.land_info?.source_land_polygon || [], [data.land_info?.source_land_polygon]);
  const floors = data.floor_plan?.floors || [];

  // Center coordinates around (0,0) for clean Three.js framing
  const { centerX, centerY } = useMemo(() => {
    if (landPoly.length === 0) return { centerX: 0, centerY: 0 };
    const xs = landPoly.map((p) => p.x);
    const ys = landPoly.map((p) => p.y);
    return {
      centerX: (Math.min(...xs) + Math.max(...xs)) / 2,
      centerY: (Math.min(...ys) + Math.max(...ys)) / 2,
    };
  }, [landPoly]);

  // Create Land Base Extrusion
  const landShape = useMemo(() => {
    if (landPoly.length < 3) return null;
    const shape = new THREE.Shape();
    shape.moveTo(landPoly[0].x - centerX, landPoly[0].y - centerY);
    for (let i = 1; i < landPoly.length; i++) {
      shape.lineTo(landPoly[i].x - centerX, landPoly[i].y - centerY);
    }
    shape.closePath();
    return shape;
  }, [landPoly, centerX, centerY]);

  const activeFloors: FloorPlan[] =
    selectedFloorIndex === 'all'
      ? floors
      : floors.filter((f) => f.floor_index === selectedFloorIndex);

  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      {/* 1. Ground Land Base in Canonical Coordinates */}
      {landShape && (
        <mesh position={[0, 0, -0.2]}>
          <extrudeGeometry
            args={[
              landShape,
              { depth: 0.2, bevelEnabled: false },
            ]}
          />
          <meshStandardMaterial color="#1e293b" roughness={0.8} metalness={0.1} />
        </mesh>
      )}

      {/* 2. Multi-Storey Floors */}
      {activeFloors.map((fl) => {
        const floorBaseZ = explodedMode
          ? fl.floor_index * 5.0
          : fl.elevation;

        return (
          <group key={fl.floor_id} position={[0, 0, floorBaseZ]}>
            {/* Floor Slab and Room Volumes */}
            {fl.rooms.map((rm) => {
              const pts = rm.polygon;
              if (pts.length < 3) return null;

              const roomShape = new THREE.Shape();
              roomShape.moveTo(pts[0].x - centerX, pts[0].y - centerY);
              for (let i = 1; i < pts.length; i++) {
                roomShape.lineTo(pts[i].x - centerX, pts[i].y - centerY);
              }
              roomShape.closePath();

              const roomColor = rm.is_structural_stair
                ? '#eab308'
                : fl.floor_index === 0
                ? '#38bdf8'
                : '#818cf8';

              return (
                <group key={rm.room_id}>
                  {/* Floor tile slab */}
                  <mesh position={[0, 0, 0]}>
                    <extrudeGeometry
                      args={[
                        roomShape,
                        { depth: 0.1, bevelEnabled: false },
                      ]}
                    />
                    <meshStandardMaterial
                      color="#334155"
                      roughness={0.6}
                      metalness={0.2}
                    />
                  </mesh>

                  {/* Room architectural volume wireframe / transparent volume */}
                  <mesh position={[0, 0, 0.1]}>
                    <extrudeGeometry
                      args={[
                        roomShape,
                        { depth: 2.7, bevelEnabled: false },
                      ]}
                    />
                    <meshStandardMaterial
                      color={roomColor}
                      transparent
                      opacity={rm.is_structural_stair ? 0.5 : 0.3}
                      roughness={0.4}
                    />
                  </mesh>

                  {/* 3D Room Floating Label */}
                  <Html
                    position={[rm.center.x - centerX, rm.center.y - centerY, 2.8]}
                    center
                    distanceFactor={22}
                    className="pointer-events-none select-none"
                  >
                    <div className="bg-slate-900/90 text-slate-100 px-2 py-0.5 rounded border border-indigo-500/50 text-[10px] whitespace-nowrap shadow-md flex items-center gap-1">
                      <span className="font-bold">{rm.name}</span>
                      <span className="text-slate-400 font-mono">({rm.area.toFixed(1)}m²)</span>
                    </div>
                  </Html>
                </group>
              );
            })}

            {/* 3. Wall Segments from JSON */}
            {fl.walls.map((w) => {
              const p1 = new THREE.Vector3(w.start.x - centerX, w.start.y - centerY, 0.1);
              const p2 = new THREE.Vector3(w.end.x - centerX, w.end.y - centerY, 0.1);
              const length = p1.distanceTo(p2);
              const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
              const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

              return (
                <mesh
                  key={w.wall_id}
                  position={[mid.x, mid.y, 1.45]}
                  rotation={[0, 0, angle]}
                >
                  <boxGeometry args={[length, w.thickness, 2.7]} />
                  <meshStandardMaterial
                    color={w.wall_type === 'exterior' ? '#f8fafc' : '#cbd5e1'}
                    roughness={0.7}
                  />
                </mesh>
              );
            })}

            {/* 4. Physical 3D Doors & Entrances with 3D Labels */}
            {fl.doors && fl.doors.map((d) => (
              <group key={d.door_id} position={[d.position.x - centerX, d.position.y - centerY, 1.1]}>
                <mesh>
                  <boxGeometry args={[d.width_m, 0.35, 2.1]} />
                  <meshStandardMaterial
                    color={d.is_external_entrance ? '#22c55e' : '#f59e0b'}
                    roughness={0.4}
                  />
                </mesh>
                <Html position={[0, 0, 1.3]} center distanceFactor={24} className="pointer-events-none select-none">
                  <div className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider text-white shadow ${d.is_external_entrance ? 'bg-emerald-600/90' : 'bg-amber-600/90'}`}>
                    {d.is_external_entrance ? 'Entrance' : 'Door'}
                  </div>
                </Html>
              </group>
            ))}

            {/* 5. Physical 3D Windows with 3D Labels */}
            {fl.windows && fl.windows.map((w) => (
              <group key={w.window_id} position={[w.position.x - centerX, w.position.y - centerY, 1.5]}>
                <mesh>
                  <boxGeometry args={[w.width_m, 0.32, w.height_m || 1.2]} />
                  <meshStandardMaterial
                    color="#38bdf8"
                    transparent
                    opacity={0.65}
                    roughness={0.1}
                    metalness={0.8}
                  />
                </mesh>
                <Html position={[0, 0, 0.8]} center distanceFactor={26} className="pointer-events-none select-none">
                  <div className="bg-sky-700/90 text-white px-1 py-0.2 rounded text-[7px] font-bold uppercase">
                    Win ({w.width_m.toFixed(1)}m)
                  </div>
                </Html>
              </group>
            ))}
          </group>
        );
      })}


      {/* 3. Roof Structure Extrusion / Pitch Modeling */}
      {data.roof_geometry && activeFloors.length > 0 && (() => {
        const topFloor = floors[floors.length - 1];
        if (!topFloor) return null;
        const roofZ = explodedMode ? (floors.length - 1) * 5.0 + 2.8 : topFloor.elevation + 2.8;
        const eavePts = data.roof_geometry.eave_polygon || [];
        if (eavePts.length < 3) return null;

        const roofShape = new THREE.Shape();
        roofShape.moveTo(eavePts[0].x - centerX, eavePts[0].y - centerY);
        for (let i = 1; i < eavePts.length; i++) {
          roofShape.lineTo(eavePts[i].x - centerX, eavePts[i].y - centerY);
        }
        roofShape.closePath();

        const roofType = data.roof_geometry.roof_type;
        const roofHeight = Math.max(0.4, data.roof_geometry.max_height_m || 1.2);
        const roofColor = roofType === 'accessible_rooftop'
          ? '#64748b'
          : roofType === 'flat_slab'
          ? '#475569'
          : '#ea580c'; // Clay / tile terracotta orange

        return (
          <group position={[0, 0, roofZ]}>
            {/* Base Roof Ceiling/Slab */}
            <mesh position={[0, 0, 0]}>
              <extrudeGeometry args={[roofShape, { depth: 0.15, bevelEnabled: false }]} />
              <meshStandardMaterial color="#334155" roughness={0.7} />
            </mesh>

            {/* Sloped Roof Mesh or Parapet */}
            {roofType === 'accessible_rooftop' ? (
              // Parapet Safety Wall Around Perimeter
              <mesh position={[0, 0, 0.15]}>
                <extrudeGeometry args={[roofShape, { depth: 0.9, bevelEnabled: false }]} />
                <meshStandardMaterial color="#94a3b8" transparent opacity={0.4} wireframe />
              </mesh>
            ) : roofType === 'flat_slab' ? (
              // Parapet Curb
              <mesh position={[0, 0, 0.15]}>
                <extrudeGeometry args={[roofShape, { depth: 0.3, bevelEnabled: false }]} />
                <meshStandardMaterial color="#475569" roughness={0.8} />
              </mesh>
            ) : (
              // Pitched/Gable/Hip/Mono Roof Cap
              <mesh position={[0, 0, 0.15]}>
                <extrudeGeometry
                  args={[
                    roofShape,
                    {
                      depth: roofHeight,
                      bevelEnabled: true,
                      bevelThickness: 0.2,
                      bevelSize: 0.3,
                      bevelSegments: 2,
                    },
                  ]}
                />
                <meshStandardMaterial
                  color={roofColor}
                  roughness={0.5}
                  metalness={0.1}
                />
              </mesh>
            )}
          </group>
        );
      })()}
    </group>
  );
};

export const PlanPreview3D: React.FC<PlanPreview3DProps> = ({
  data,
  selectedFloorIndex,
  explodedMode = false,
}) => {
  const controlsRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);

  const rotateCamera = (angleDeltaRad: number) => {
    if (!cameraRef.current || !controlsRef.current) return;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const offset = new THREE.Vector3().subVectors(camera.position, controls.target);
    const radius = Math.sqrt(offset.x * offset.x + offset.z * offset.z);
    const currentAngle = Math.atan2(offset.z, offset.x);
    const newAngle = currentAngle + angleDeltaRad;
    camera.position.x = controls.target.x + radius * Math.cos(newAngle);
    camera.position.z = controls.target.z + radius * Math.sin(newAngle);
    controls.update();
  };

  const setCameraPreset = (type: 'perspective' | 'top' | 'front' | 'side' | 'rear') => {
    if (!controlsRef.current || !cameraRef.current) return;
    const controls = controlsRef.current;
    const camera = cameraRef.current;

    if (type === 'perspective') {
      camera.position.set(18, 22, 25);
      controls.target.set(0, 0, 0);
    } else if (type === 'top') {
      camera.position.set(0, 40, 0.01);
      controls.target.set(0, 0, 0);
    } else if (type === 'front') {
      camera.position.set(0, 5, 35);
      controls.target.set(0, 3, 0);
    } else if (type === 'side') {
      camera.position.set(35, 5, 0);
      controls.target.set(0, 3, 0);
    } else if (type === 'rear') {
      camera.position.set(0, 5, -35);
      controls.target.set(0, 3, 0);
    }
    controls.update();
  };

  if (!data) {
    return (
      <div className="h-[480px] flex items-center justify-center text-muted-foreground text-xs">
        No 3D blueprint data generated yet. Click &quot;Generate Blueprint&quot; to begin.
      </div>
    );
  }

  return (
    <div className="w-full h-[480px] rounded-xl overflow-hidden border border-border relative bg-slate-950">
      <WebGLErrorBoundary title="GAB-Gen 3D Blueprint Viewport Unavailable">
        <Canvas
          id="gab-3d-canvas"
          shadows
          gl={{
            preserveDrawingBuffer: true,
            powerPreference: 'default',
            failIfMajorPerformanceCaveat: false,
          }}
        >
          <PerspectiveCamera ref={cameraRef} makeDefault position={[18, 22, 25]} fov={45} />
          <ambientLight intensity={0.75} />
          <directionalLight position={[15, 30, 20]} intensity={1.3} castShadow />
          <directionalLight position={[-15, -10, -10]} intensity={0.4} />

          <BuildingScene
            data={data}
            selectedFloorIndex={selectedFloorIndex}
            explodedMode={explodedMode}
          />

          <OrbitControls
            ref={controlsRef}
            makeDefault
            enableDamping
            dampingFactor={0.08}
            minDistance={5}
            maxDistance={90}
          />
          <gridHelper args={[40, 40, '#475569', '#1e293b']} position={[0, -0.2, 0]} />
        </Canvas>
      </WebGLErrorBoundary>

      {/* Camera Presets & Rotation Toolbar */}
      <div className="absolute top-3 right-3 flex flex-wrap items-center gap-1 bg-background/90 backdrop-blur-md p-1.5 rounded-lg border border-border shadow-md text-xs">
        {/* Quick Rotation Buttons */}
        <Button
          size="sm"
          variant="outline"
          className="h-6 w-6 p-0"
          onClick={() => rotateCamera(-Math.PI / 8)}
          title="Rotate Left 22.5°"
        >
          <RotateCcw className="w-3 h-3" />
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-6 w-6 p-0"
          onClick={() => rotateCamera(Math.PI / 8)}
          title="Rotate Right 22.5°"
        >
          <RotateCw className="w-3 h-3" />
        </Button>

        <div className="h-3.5 w-[1px] bg-border mx-0.5" />

        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-[10px]"
          onClick={() => setCameraPreset('perspective')}
        >
          Perspective
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-[10px]"
          onClick={() => setCameraPreset('top')}
        >
          Top Plan
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-[10px]"
          onClick={() => setCameraPreset('front')}
        >
          Front View
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-[10px]"
          onClick={() => setCameraPreset('side')}
        >
          Side View
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-[10px]"
          onClick={() => setCameraPreset('rear')}
        >
          Rear View
        </Button>
      </div>

      <div className="absolute top-3 left-3 bg-background/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-border text-[11px] text-muted-foreground flex items-center gap-2.5">
        <span className="font-semibold text-foreground">3D Controls:</span>
        <span>Left Click: Orbit</span>
        <span>Right Click: Pan</span>
        <span>Scroll: Zoom</span>
      </div>
    </div>
  );
};
