'use client';

import React, { useMemo } from 'react';
import {
  SceneDataResponse,
  PlacedAssetPersistedDTO,
  PlacedFixturePointDTO,
  LayerVisibilityState,
  PersistedRoomDesignDTO,
} from '@/types/esai';
import { FloorScene } from './FloorScene';
import { SceneDataAdapter } from './SceneDataAdapter';

interface BuildingSceneProps {
  sceneData: SceneDataResponse;
  selectedFloorId: string | null;
  selectedRoomId: string | null;
  onSelectRoom: (roomId: string) => void;
  selectedAssetId: string | null;
  onSelectAsset: (asset: PlacedAssetPersistedDTO) => void;
  selectedFixtureId: string | null;
  onSelectFixture: (fixture: PlacedFixturePointDTO) => void;
  layers: LayerVisibilityState;
  isolateFloor?: boolean;
  isolateRoom?: boolean;
  explodedView?: boolean;
  draftDesign?: PersistedRoomDesignDTO | null;
}

export const BuildingScene: React.FC<BuildingSceneProps> = ({
  sceneData,
  selectedFloorId,
  selectedRoomId,
  onSelectRoom,
  selectedAssetId,
  onSelectAsset,
  selectedFixtureId,
  onSelectFixture,
  layers,
  isolateFloor = false,
  isolateRoom = false,
  explodedView = false,
  draftDesign,
}) => {
  // Merge live customization draft into saved_designs
  const effectiveDesigns = useMemo(() => {
    if (selectedRoomId && draftDesign) {
      return {
        ...sceneData.saved_designs,
        [selectedRoomId]: draftDesign,
      };
    }
    return sceneData.saved_designs;
  }, [sceneData.saved_designs, selectedRoomId, draftDesign]);

  // 1. Filter floors depending on isolation mode
  const visibleFloors = useMemo(() => {
    if (isolateFloor && selectedFloorId) {
      return sceneData.floors.filter((f) => f.floor_id === selectedFloorId);
    }
    if (isolateRoom && selectedRoomId) {
      return sceneData.floors.filter((f) =>
        f.rooms.some((r) => r.room_id === selectedRoomId)
      );
    }
    return sceneData.floors;
  }, [sceneData.floors, isolateFloor, selectedFloorId, isolateRoom, selectedRoomId]);

  // 2. Exploded floor spacing factor (extra vertical spacing per level)
  const EXPLODED_SPACING_M = 2.5;

  return (
    <group name="building_scene">
      {/* Soft ground shadow receiver slab */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.05, 0]}
        receiveShadow
      >
        <planeGeometry args={[100, 100]} />
        <shadowMaterial opacity={0.25} />
      </mesh>

      {visibleFloors.map((floor) => {
        // Compute exploded elevation offset
        const elevationOffset = explodedView ? floor.level_index * EXPLODED_SPACING_M : 0;
        const isolatedRoomId = isolateRoom ? selectedRoomId : null;

        return (
          <FloorScene
            key={floor.floor_id}
            floor={floor}
            savedDesigns={effectiveDesigns}
            selectedRoomId={selectedRoomId}
            onSelectRoom={onSelectRoom}
            selectedAssetId={selectedAssetId}
            onSelectAsset={onSelectAsset}
            selectedFixtureId={selectedFixtureId}
            onSelectFixture={onSelectFixture}
            layers={layers}
            isolatedRoomId={isolatedRoomId}
            elevationOffset={elevationOffset}
          />
        );
      })}
    </group>
  );
};
