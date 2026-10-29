'use client';

import React, { useEffect, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import * as THREE from 'three';
import { ViewCameraMode, FloorDTO } from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';

interface CameraControllerProps {
  mode: ViewCameraMode;
  floors: FloorDTO[];
  selectedFloorId: string | null;
  selectedRoomId: string | null;
  resetTrigger?: number;
}

export const CameraController: React.FC<CameraControllerProps> = ({
  mode,
  floors,
  selectedFloorId,
  selectedRoomId,
  resetTrigger = 0,
}) => {
  const { camera } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null);

  // 1. Calculate bounding center and radius of scene or selected room
  const sceneBounds = React.useMemo(() => {
    // If a room is selected, center on that room
    if (selectedRoomId) {
      for (const f of floors) {
        const r = f.rooms.find((rm) => rm.room_id === selectedRoomId);
        if (r && r.polygon && r.polygon.length > 0) {
          const bounds = SceneDataAdapter.computePolygonBounds(r.polygon);
          const elev = f.elevation ?? f.level_index * 3.0;
          return {
            center: [bounds.centerX, elev + 1.4, -bounds.centerY] as [number, number, number],
            radius: Math.max(bounds.width, bounds.height, 4) * 1.5,
          };
        }
      }
    }

    // If a floor is selected, center on that floor
    if (selectedFloorId) {
      const f = floors.find((fl) => fl.floor_id === selectedFloorId);
      if (f && f.rooms.length > 0) {
        const allVerts = f.rooms.flatMap((r) => r.polygon);
        const bounds = SceneDataAdapter.computePolygonBounds(allVerts);
        const elev = f.elevation ?? f.level_index * 3.0;
        return {
          center: [bounds.centerX, elev + 1.4, -bounds.centerY] as [number, number, number],
          radius: Math.max(bounds.width, bounds.height, 8) * 1.5,
        };
      }
    }

    // Entire building center
    const allVerts = floors.flatMap((f) => f.rooms.flatMap((r) => r.polygon));
    if (allVerts.length > 0) {
      const bounds = SceneDataAdapter.computePolygonBounds(allVerts);
      const maxElev = Math.max(...floors.map((f) => (f.elevation ?? f.level_index * 3.0) + 3.0));
      return {
        center: [bounds.centerX, maxElev / 2, -bounds.centerY] as [number, number, number],
        radius: Math.max(bounds.width, bounds.height, maxElev, 10) * 1.6,
      };
    }

    // Default fallback
    return {
      center: [5, 1.5, -5] as [number, number, number],
      radius: 15,
    };
  }, [floors, selectedFloorId, selectedRoomId]);

  // 2. Adjust camera position and target based on mode and selection
  useEffect(() => {
    if (!controlsRef.current || mode === 'walkthrough') return;

    const { center, radius } = sceneBounds;
    const [cx, cy, cz] = center;

    if (mode === 'top_down') {
      camera.position.set(cx, cy + radius * 1.2, cz);
      controlsRef.current.target.set(cx, cy, cz);
      controlsRef.current.maxPolarAngle = 0.05; // Lock strictly top-down
      controlsRef.current.minPolarAngle = 0.0;
    } else if (mode === 'isometric') {
      const isoDist = radius * 0.9;
      camera.position.set(cx + isoDist, cy + isoDist * 0.8, cz + isoDist);
      controlsRef.current.target.set(cx, cy, cz);
      controlsRef.current.maxPolarAngle = Math.PI / 2.2;
      controlsRef.current.minPolarAngle = 0.1;
    } else {
      // Perspective / Room Focus
      const dist = radius * 0.85;
      camera.position.set(cx + dist * 0.7, cy + dist * 0.6, cz + dist * 0.7);
      controlsRef.current.target.set(cx, cy, cz);
      controlsRef.current.maxPolarAngle = Math.PI / 2 - 0.02; // Prevent going beneath ground
      controlsRef.current.minPolarAngle = 0.1;
    }

    controlsRef.current.update();
  }, [mode, sceneBounds, resetTrigger, camera]);

  if (mode === 'walkthrough') {
    return null; // WalkthroughController takes over camera
  }

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      rotateSpeed={0.8}
      zoomSpeed={1.0}
      panSpeed={0.8}
      screenSpacePanning
    />
  );
};
