'use client';

import React, { useMemo } from 'react';
import {
  FloorDTO,
  PersistedRoomDesignDTO,
  PlacedAssetPersistedDTO,
  PlacedFixturePointDTO,
  LayerVisibilityState,
} from '@/types/esai';
import { RoomScene } from './RoomScene';
import { SceneDataAdapter } from './SceneDataAdapter';
import { MaterialResolver } from './MaterialResolver';

interface FloorSceneProps {
  floor: FloorDTO;
  savedDesigns: Record<string, PersistedRoomDesignDTO>;
  selectedRoomId: string | null;
  onSelectRoom: (roomId: string) => void;
  selectedAssetId: string | null;
  onSelectAsset: (asset: PlacedAssetPersistedDTO) => void;
  selectedFixtureId: string | null;
  onSelectFixture: (fixture: PlacedFixturePointDTO) => void;
  layers: LayerVisibilityState;
  isolatedRoomId?: string | null;
  elevationOffset?: number;
}

export const FloorScene: React.FC<FloorSceneProps> = ({
  floor,
  savedDesigns,
  selectedRoomId,
  onSelectRoom,
  selectedAssetId,
  onSelectAsset,
  selectedFixtureId,
  onSelectFixture,
  layers,
  isolatedRoomId = null,
  elevationOffset = 0,
}) => {
  // Authoritative elevation (defaults to level_index * 3.0m if elevation_m not provided)
  const baseElevation = floor.elevation_m ?? floor.level_index * 3.0;
  const effectiveElevation = baseElevation + elevationOffset;

  // Structural wall segments at floor level (outside room boundaries)
  const structuralWalls = useMemo(() => {
    if (!floor.walls || floor.walls.length === 0) return [];
    return floor.walls.flatMap((w) =>
      SceneDataAdapter.computeWallSegments(w, effectiveElevation)
    );
  }, [floor.walls, effectiveElevation]);

  const structuralWallMaterial = useMemo(() => {
    return MaterialResolver.resolveWallMaterial('exterior', undefined, layers.wireframe);
  }, [layers.wireframe]);

  // Filter rooms if isolatedRoomId is specified
  const roomsToRender = useMemo(() => {
    if (!isolatedRoomId) return floor.rooms;
    return floor.rooms.filter((r) => r.room_id === isolatedRoomId);
  }, [floor.rooms, isolatedRoomId]);

  return (
    <group name={`floor_${floor.floor_id}`}>
      {/* ── Floor Level Structural Walls (if present in authoritative geometry) ── */}
      {layers.walls && structuralWalls.length > 0 && (
        <group name="floor_structural_walls">
          {structuralWalls.map((seg) => (
            <mesh
              key={seg.id}
              position={seg.position}
              rotation={seg.rotation}
              castShadow
              receiveShadow
            >
              <boxGeometry args={seg.dimensions} />
              <primitive object={structuralWallMaterial} attach="material" />
            </mesh>
          ))}
        </group>
      )}

      {/* ── Rooms in Floor ────────────────────────────────────────────────────── */}
      {roomsToRender.map((room) => {
        const savedDesign = savedDesigns[room.room_id];
        const isSelected = selectedRoomId === room.room_id;

        return (
          <RoomScene
            key={room.room_id}
            room={room}
            floorElevation={effectiveElevation}
            savedDesign={savedDesign}
            isSelected={isSelected}
            onSelectRoom={onSelectRoom}
            selectedAssetId={selectedAssetId}
            onSelectAsset={onSelectAsset}
            selectedFixtureId={selectedFixtureId}
            onSelectFixture={onSelectFixture}
            layers={layers}
          />
        );
      })}
    </group>
  );
};
