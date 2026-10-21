'use client';

import React, { useMemo } from 'react';
import * as THREE from 'three';
import { Html } from '@react-three/drei';
import {
  RoomDTO,
  PersistedRoomDesignDTO,
  PlacedAssetPersistedDTO,
  PlacedFixturePointDTO,
  LayerVisibilityState,
  Coordinate2D,
} from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';
import { MaterialResolver } from './MaterialResolver';
import { FurnitureRenderer } from './FurnitureRenderer';
import { LightingRenderer } from './LightingRenderer';
import { ServicePointRenderer } from './ServicePointRenderer';

interface RoomSceneProps {
  room: RoomDTO;
  floorElevation?: number;
  savedDesign?: PersistedRoomDesignDTO;
  isSelected?: boolean;
  onSelectRoom?: (roomId: string) => void;
  selectedAssetId?: string | null;
  onSelectAsset?: (asset: PlacedAssetPersistedDTO) => void;
  selectedFixtureId?: string | null;
  onSelectFixture?: (fixture: PlacedFixturePointDTO) => void;
  layers: LayerVisibilityState;
}

export const RoomScene: React.FC<RoomSceneProps> = ({
  room,
  floorElevation = 0,
  savedDesign,
  isSelected = false,
  onSelectRoom,
  selectedAssetId,
  onSelectAsset,
  selectedFixtureId,
  onSelectFixture,
  layers,
}) => {
  const roomHeight = room.ceiling_height ?? room.height_m ?? 2.8;
  const poly = room.polygon || [];

  // 1. Floor shape and geometry from authoritative polygon
  const floorShape = useMemo(() => {
    return SceneDataAdapter.createPolygonShape(poly);
  }, [poly]);

  const floorFinishStr =
    savedDesign?.floor_finish ||
    (savedDesign?.floor_finishes ? JSON.stringify(savedDesign.floor_finishes) : undefined);

  const floorMaterial = useMemo(() => {
    return MaterialResolver.resolveFloorMaterial(
      floorFinishStr,
      room.room_type,
      layers.wireframe
    );
  }, [floorFinishStr, room.room_type, layers.wireframe]);

  // 2. Room center for label and camera focus
  const center = useMemo(() => {
    return SceneDataAdapter.computePolygonCenter(poly);
  }, [poly]);

  // 3. Walls computation
  const wallSegments = useMemo(() => {
    if (room.walls && room.walls.length > 0) {
      return room.walls.flatMap((w) =>
        SceneDataAdapter.computeWallSegments(w, floorElevation, room.doors || [], room.windows || [])
      );
    }
    return SceneDataAdapter.computePolygonBoundaryWalls(
      poly,
      floorElevation,
      roomHeight,
      0.15
    );
  }, [room.walls, poly, floorElevation, room.doors, room.windows, roomHeight]);

  // 4. Wall material
  const wallMaterial = useMemo(() => {
    return MaterialResolver.resolveWallMaterial(
      'interior',
      savedDesign?.wall_color,
      layers.wireframe
    );
  }, [savedDesign?.wall_color, layers.wireframe]);

  // 5. Ceiling material (cutaway transparency)
  const ceilingMaterial = useMemo(() => {
    return MaterialResolver.resolveCeilingMaterial(true, layers.wireframe);
  }, [layers.wireframe]);

  // 6. Split fixtures into lighting vs service points
  const { lightingFixtures, serviceFixtures } = useMemo(() => {
    const allFixtures: PlacedFixturePointDTO[] =
      savedDesign?.fixtures || [
        ...(savedDesign?.lighting || []),
        ...(savedDesign?.electrical_points || []),
        ...(savedDesign?.plumbing_requirements || []),
      ];

    const lighting: PlacedFixturePointDTO[] = [];
    const service: PlacedFixturePointDTO[] = [];

    allFixtures.forEach((f) => {
      const type = (f.fixture_type || f.point_type || '').toLowerCase();
      if (
        type.includes('light') ||
        type.includes('downlight') ||
        type.includes('pendant') ||
        type.includes('sconce') ||
        type.includes('chandelier')
      ) {
        lighting.push(f);
      } else {
        service.push(f);
      }
    });

    return { lightingFixtures: lighting, serviceFixtures: service };
  }, [savedDesign]);

  // 7. Filter placed assets by category layer toggles
  const visibleAssets = useMemo(() => {
    const assets: PlacedAssetPersistedDTO[] =
      savedDesign?.placed_assets || [
        ...(savedDesign?.furniture || []),
        ...(savedDesign?.cabinetry || []),
        ...(savedDesign?.appliances || []),
        ...(savedDesign?.sanitary_fixtures || []),
        ...(savedDesign?.decorations || []),
      ];

    return assets.filter((asset) => {
      const cat = (asset.category || '').toLowerCase();
      if (cat === 'cabinetry' && !layers.cabinetry) return false;
      if (cat === 'appliances' && !layers.appliances) return false;
      if (cat === 'sanitary_fixtures' && !layers.sanitary) return false;
      if (['bed', 'sofa', 'table', 'chair', 'desk', 'storage', 'coffee_table', 'armchair', 'wardrobe'].includes(cat)) {
        if (!layers.furniture) return false;
      }
      return true;
    });
  }, [savedDesign, layers]);

  return (
    <group
      name={`room_${room.room_id}`}
      onClick={(e) => {
        e.stopPropagation();
        onSelectRoom?.(room.room_id);
      }}
    >
      {/* ── Room Floor ────────────────────────────────────────────────────────── */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, floorElevation + 0.005, 0]}
        receiveShadow
      >
        <shapeGeometry args={[floorShape]} />
        <primitive object={floorMaterial} attach="material" />
      </mesh>

      {/* Selected Room Highlight Outline on Floor */}
      {isSelected && (
        <lineSegments position={[0, floorElevation + 0.015, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <edgesGeometry args={[new THREE.ShapeGeometry(floorShape)]} />
          <lineBasicMaterial color="#06b6d4" linewidth={3} />
        </lineSegments>
      )}

      {/* ── Room Walls ────────────────────────────────────────────────────────── */}
      {layers.walls && (
        <group name="walls">
          {wallSegments.map((seg) => (
            <mesh
              key={seg.id}
              position={seg.position}
              rotation={seg.rotation}
              castShadow
              receiveShadow
            >
              <boxGeometry args={seg.dimensions} />
              <primitive object={wallMaterial} attach="material" />
            </mesh>
          ))}
        </group>
      )}

      {/* ── Openings (Doors & Windows) ───────────────────────────────────────── */}
      {layers.walls && room.doors && room.doors.length > 0 && (
        <group name="doors">
          {room.doors.map((door) => {
            const midX = door.position ? door.position.x : (door.start.x + door.end.x) / 2;
            const midY = door.position ? door.position.y : (door.start.y + door.end.y) / 2;
            const doorH = door.height || 2.1;
            const doorW = door.width || door.leaf_width || 0.9;
            const rotY = door.rotation_deg !== undefined
              ? (door.rotation_deg * Math.PI) / 180
              : Math.atan2(-(door.end.y - door.start.y), door.end.x - door.start.x);

            const pos = SceneDataAdapter.to3DPosition(midX, midY, floorElevation, doorH / 2);
            return (
              <group key={door.id} position={pos} rotation={[0, rotY, 0]}>
                {/* Door Frame */}
                <mesh castShadow>
                  <boxGeometry args={[doorW, doorH, 0.08]} />
                  <meshStandardMaterial color="#78350f" roughness={0.4} />
                </mesh>
              </group>
            );
          })}
        </group>
      )}

      {layers.walls && room.windows && room.windows.length > 0 && (
        <group name="windows">
          {room.windows.map((win) => {
            const midX = win.position ? win.position.x : (win.start.x + win.end.x) / 2;
            const midY = win.position ? win.position.y : (win.start.y + win.end.y) / 2;
            const sillHeight = win.sill_height || 0.9;
            const winH = win.height || 1.2;
            const winW = win.width || win.length || 1.2;
            const rotY = win.rotation_deg !== undefined
              ? (win.rotation_deg * Math.PI) / 180
              : Math.atan2(-(win.end.y - win.start.y), win.end.x - win.start.x);

            const pos = SceneDataAdapter.to3DPosition(midX, midY, floorElevation, sillHeight + winH / 2);
            return (
              <group key={win.id} position={pos} rotation={[0, rotY, 0]}>
                {/* Window Frame */}
                <mesh castShadow>
                  <boxGeometry args={[winW, winH, 0.06]} />
                  <primitive object={MaterialResolver.getGlassMaterial()} attach="material" />
                </mesh>
              </group>
            );
          })}
        </group>
      )}

      {/* ── Room Ceiling (Cutaway inspection) ─────────────────────────────────── */}
      {layers.ceiling && (
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, floorElevation + roomHeight, 0]}
        >
          <shapeGeometry args={[floorShape]} />
          <primitive object={ceilingMaterial} attach="material" />
        </mesh>
      )}

      {/* ── Furniture & Placed Assets ─────────────────────────────────────────── */}
      <group name="placed_assets">
        {visibleAssets.map((asset) => (
          <FurnitureRenderer
            key={asset.instance_id}
            asset={asset}
            elevation={floorElevation}
            isSelected={selectedAssetId === asset.instance_id}
            wireframe={layers.wireframe}
            onClick={(a) => onSelectAsset?.(a)}
          />
        ))}
      </group>

      {/* ── Lighting Fixtures & Simulation ────────────────────────────────────── */}
      <LightingRenderer
        fixtures={lightingFixtures}
        elevation={floorElevation}
        ceilingHeight={roomHeight}
        enabled={layers.lighting}
      />

      {/* ── Service Points & Outlets ──────────────────────────────────────────── */}
      <ServicePointRenderer
        fixtures={serviceFixtures}
        floorElevation={floorElevation}
        selectedFixtureId={selectedFixtureId}
        onSelectFixture={onSelectFixture}
        visible={layers.servicePoints}
      />

      {/* ── Room Badge / Label ───────────────────────────────────────────────── */}
      {layers.roomLabels && (
        <Html
          position={[center.x, floorElevation + 1.2, -center.y]}
          center
          distanceFactor={18}
        >
          <div
            onClick={(e) => {
              e.stopPropagation();
              onSelectRoom?.(room.room_id);
            }}
            className={`px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer shadow-md transition-all select-none backdrop-blur-md border ${
              isSelected
                ? 'bg-cyan-500/90 text-white border-cyan-300 ring-2 ring-cyan-400'
                : 'bg-slate-900/80 text-slate-200 border-slate-700 hover:bg-slate-800'
            }`}
          >
            <div className="font-semibold text-[11px]">{room.name}</div>
            <div className="text-[9px] text-slate-300">
              {room.area_sqm.toFixed(1)} m² • {room.room_type.replace('_', ' ')}
            </div>
            {savedDesign && (
              <div className="flex items-center gap-1 mt-0.5 text-[8px] text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                <span>{visibleAssets.length} items</span>
              </div>
            )}
          </div>
        </Html>
      )}
    </group>
  );
};
