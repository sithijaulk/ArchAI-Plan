'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { FloorDTO } from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';

interface WalkthroughControllerProps {
  active: boolean;
  floors: FloorDTO[];
  selectedFloorId: string | null;
  selectedRoomId: string | null;
  onExit?: () => void;
}

export const WalkthroughController: React.FC<WalkthroughControllerProps> = ({
  active,
  floors,
  selectedFloorId,
  selectedRoomId,
  onExit,
}) => {
  const { camera, gl } = useThree();
  const keys = useRef<{ [key: string]: boolean }>({});
  const moveSpeed = 3.5; // meters per second
  const eyeHeight = 1.6; // average eye level in meters

  const [mouseLook, setMouseLook] = useState({ yaw: 0, pitch: 0 });
  const isDragging = useRef(false);
  const prevMouse = useRef({ x: 0, y: 0 });

  // 1. Determine spawn position from selected room or floor
  const spawnPosition = React.useMemo<[number, number, number]>(() => {
    for (const f of floors) {
      if (selectedFloorId && f.floor_id !== selectedFloorId) continue;
      for (const r of f.rooms) {
        if (!selectedRoomId || r.room_id === selectedRoomId) {
          if (r.polygon && r.polygon.length > 0) {
            const center = SceneDataAdapter.computePolygonCenter(r.polygon);
            const elev = f.elevation ?? f.level_index * 3.0;
            return [center.x, elev + eyeHeight, -center.y];
          }
        }
      }
    }
    return [0, eyeHeight, 0];
  }, [floors, selectedFloorId, selectedRoomId]);

  // 2. Set camera to spawn position upon activation
  useEffect(() => {
    if (active) {
      camera.position.set(spawnPosition[0], spawnPosition[1], spawnPosition[2]);
      setMouseLook({ yaw: 0, pitch: 0 });
    }
  }, [active, spawnPosition, camera]);

  // 3. Keyboard input listeners
  useEffect(() => {
    if (!active) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      keys.current[e.code] = true;
      if (e.code === 'Escape') {
        onExit?.();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      keys.current[e.code] = false;
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      keys.current = {};
    };
  }, [active, onExit]);

  // 4. Mouse look handlers
  useEffect(() => {
    if (!active) return;
    const domElement = gl.domElement;

    const handleMouseDown = (e: MouseEvent) => {
      if (e.button === 0) {
        isDragging.current = true;
        prevMouse.current = { x: e.clientX, y: e.clientY };
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const dx = e.clientX - prevMouse.current.x;
      const dy = e.clientY - prevMouse.current.y;
      prevMouse.current = { x: e.clientX, y: e.clientY };

      const SENSITIVITY = 0.0025;
      setMouseLook((prev) => ({
        yaw: prev.yaw - dx * SENSITIVITY,
        pitch: Math.max(-Math.PI / 2.5, Math.min(Math.PI / 2.5, prev.pitch - dy * SENSITIVITY)),
      }));
    };

    const handleMouseUp = () => {
      isDragging.current = false;
    };

    domElement.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      domElement.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [active, gl.domElement]);

  // 5. Frame loop for smooth movement and collision checking
  useFrame((_, delta) => {
    if (!active) return;

    // Apply rotation
    const euler = new THREE.Euler(mouseLook.pitch, mouseLook.yaw, 0, 'YXZ');
    camera.quaternion.setFromEuler(euler);

    // Compute forward & right direction vectors
    const forward = new THREE.Vector3(0, 0, -1).applyEuler(new THREE.Euler(0, mouseLook.yaw, 0));
    const right = new THREE.Vector3(1, 0, 0).applyEuler(new THREE.Euler(0, mouseLook.yaw, 0));

    const moveVector = new THREE.Vector3(0, 0, 0);

    if (keys.current['KeyW'] || keys.current['ArrowUp']) moveVector.add(forward);
    if (keys.current['KeyS'] || keys.current['ArrowDown']) moveVector.sub(forward);
    if (keys.current['KeyD'] || keys.current['ArrowRight']) moveVector.add(right);
    if (keys.current['KeyA'] || keys.current['ArrowLeft']) moveVector.sub(right);

    if (moveVector.lengthSq() > 0) {
      moveVector.normalize().multiplyScalar(moveSpeed * delta);
      const nextPos = camera.position.clone().add(moveVector);

      // Keep eye level locked to floor elevation
      nextPos.y = spawnPosition[1];
      camera.position.copy(nextPos);
    }
  });

  return null;
};
