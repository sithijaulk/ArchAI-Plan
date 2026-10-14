"use client";

import React, { useRef, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
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
  const landPoly = data.land_info?.source_land_polygon || [];
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
      {/* 1. Ground Land Base */}
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
                        { depth: 2.8, bevelEnabled: false },
                      ]}
                    />
                    <meshStandardMaterial
                      color={roomColor}
                      transparent
                      opacity={0.35}
                      roughness={0.4}
                    />
                  </mesh>
                </group>
              );
            })}

            {/* 3. Walls */}
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
          </group>
        );
      })}
    </group>
  );
};

export const PlanPreview3D: React.FC<PlanPreview3DProps> = ({
  data,
  selectedFloorIndex,
  explodedMode = false,
}) => {
  if (!data) {
    return (
      <div className="h-[480px] flex items-center justify-center text-muted-foreground text-xs">
        No 3D blueprint data generated yet. Click "Generate Blueprint" to begin.
      </div>
    );
  }

  return (
    <div className="w-full h-[480px] rounded-xl overflow-hidden border border-border relative bg-slate-950">
      <Canvas shadows>
        <PerspectiveCamera makeDefault position={[18, 22, 25]} fov={45} />
        <ambientLight intensity={0.7} />
        <directionalLight position={[15, 30, 20]} intensity={1.2} castShadow />
        <directionalLight position={[-15, -10, -10]} intensity={0.4} />

        <BuildingScene
          data={data}
          selectedFloorIndex={selectedFloorIndex}
          explodedMode={explodedMode}
        />

        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.08}
          minDistance={5}
          maxDistance={80}
        />
        <gridHelper args={[40, 40, '#475569', '#1e293b']} position={[0, -0.2, 0]} />
      </Canvas>

      <div className="absolute top-3 left-3 bg-background/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-border text-[11px] text-muted-foreground flex items-center gap-3">
        <span className="font-semibold text-foreground">3D Viewport Controls:</span>
        <span>Left Click: Orbit</span>
        <span>Right Click: Pan</span>
        <span>Scroll: Zoom</span>
      </div>
    </div>
  );
};
