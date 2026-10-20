'use client';

import React, { useMemo, useState, useRef } from 'react';
import {
  FloorDTO,
  RoomDTO,
  PersistedRoomDesignDTO,
  PlacedAssetPersistedDTO,
  PlacedFixturePointDTO,
  LayerVisibilityState,
} from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';

interface PlanView2DProps {
  floor: FloorDTO;
  savedDesigns: Record<string, PersistedRoomDesignDTO>;
  selectedRoomId: string | null;
  onSelectRoom: (roomId: string) => void;
  selectedAssetId: string | null;
  onSelectAsset: (asset: PlacedAssetPersistedDTO) => void;
  selectedFixtureId: string | null;
  onSelectFixture: (fixture: PlacedFixturePointDTO) => void;
  layers: LayerVisibilityState;
  // Phase 7 Customization additions
  editMode?: 'select' | 'move' | 'rotate';
  draftDesign?: PersistedRoomDesignDTO | null;
  onMoveAsset?: (instanceId: string, x: number, y: number) => void;
  onRotateAsset?: (instanceId: string, deg: number) => void;
}

export const PlanView2D: React.FC<PlanView2DProps> = ({
  floor,
  savedDesigns,
  selectedRoomId,
  onSelectRoom,
  selectedAssetId,
  onSelectAsset,
  selectedFixtureId,
  onSelectFixture,
  layers,
  editMode = 'select',
  draftDesign,
  onMoveAsset,
  onRotateAsset,
}) => {
  const containerRef = useRef<SVGSVGElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const [draggingAssetId, setDraggingAssetId] = useState<string | null>(null);
  const startPan = useRef({ x: 0, y: 0 });

  // 1. Calculate bounding box of the floor in plan meters
  const bounds = useMemo(() => {
    const allVerts = floor.rooms.flatMap((r) => r.polygon);
    if (allVerts.length === 0) return { minX: 0, minY: 0, maxX: 10, maxY: 10, width: 10, height: 10 };
    return SceneDataAdapter.computePolygonBounds(allVerts);
  }, [floor.rooms]);

  // SVG viewBox calculation with margin
  const margin = 1.0;
  const vbX = bounds.minX - margin;
  const vbY = bounds.minY - margin;
  const vbW = bounds.width + margin * 2;
  const vbH = bounds.height + margin * 2;

  const getSvgCoordinates = (e: React.MouseEvent) => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const pt = containerRef.current.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = containerRef.current.getScreenCTM();
    if (ctm) {
      const transformed = pt.matrixTransform(ctm.inverse());
      return { x: transformed.x, y: transformed.y };
    }
    return { x: 0, y: 0 };
  };

  // Pan and Zoom interaction
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    setZoom((z) => Math.max(0.4, Math.min(4.0, z * factor)));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0 && !draggingAssetId) {
      setIsPanning(true);
      startPan.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingAssetId && onMoveAsset) {
      const pt = getSvgCoordinates(e);
      const snapX = Math.round(pt.x * 20) / 20;
      const snapY = Math.round(pt.y * 20) / 20;
      onMoveAsset(draggingAssetId, snapX, snapY);
      return;
    }
    if (isPanning) {
      setPan({
        x: e.clientX - startPan.current.x,
        y: e.clientY - startPan.current.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
    setDraggingAssetId(null);
  };

  return (
    <div
      className="relative w-full h-full bg-slate-950 overflow-hidden select-none cursor-grab active:cursor-grabbing"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {/* 2D HUD Controls */}
      <div className="absolute top-3 left-3 z-10 flex items-center gap-2 bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-800 text-xs text-slate-300">
        <span className="font-semibold text-slate-200">2D Plan</span>
        <span>•</span>
        <span>{floor.floor_name}</span>
        <span>•</span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          className="hover:text-cyan-400 text-[11px] underline ml-2"
        >
          Reset View
        </button>
      </div>

      <svg
        ref={containerRef}
        className="w-full h-full"
        viewBox={`${vbX} ${vbY} ${vbW} ${vbH}`}
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: 'center center',
          transition: isPanning ? 'none' : 'transform 0.1s ease-out',
        }}
      >
        <defs>
          <pattern id="grid2d" width="1" height="1" patternUnits="userSpaceOnUse">
            <path d="M 1 0 L 0 0 0 1" fill="none" stroke="#1e293b" strokeWidth="0.04" />
          </pattern>
        </defs>

        {/* 1m Grid background */}
        <rect
          x={vbX - 50}
          y={vbY - 50}
          width={vbW + 100}
          height={vbH + 100}
          fill="url(#grid2d)"
        />

        {/* ── Floor Rooms ──────────────────────────────────────────────────────── */}
        {floor.rooms.map((room) => {
          const isSelected = selectedRoomId === room.room_id;
          const pointsStr = (room.polygon || []).map((v) => `${v.x},${v.y}`).join(' ');
          const activeDesign =
            selectedRoomId === room.room_id && draftDesign ? draftDesign : savedDesigns[room.room_id];
          const center = SceneDataAdapter.computePolygonCenter(room.polygon || []);
          const walls = room.walls || floor.walls || [];
          const assets = activeDesign?.placed_assets || [
            ...(activeDesign?.furniture || []),
            ...(activeDesign?.cabinetry || []),
            ...(activeDesign?.appliances || []),
            ...(activeDesign?.sanitary_fixtures || []),
          ];
          const fixtures = activeDesign?.fixtures || [
            ...(activeDesign?.lighting || []),
            ...(activeDesign?.electrical_points || []),
            ...(activeDesign?.plumbing_requirements || []),
          ];

          return (
            <g key={room.room_id} onClick={() => onSelectRoom(room.room_id)}>
              {/* Room polygon floor */}
              <polygon
                points={pointsStr}
                fill={isSelected ? '#0e7490' : '#1e293b'}
                fillOpacity={isSelected ? 0.35 : 0.2}
                stroke={isSelected ? '#06b6d4' : '#475569'}
                strokeWidth={isSelected ? 0.12 : 0.06}
                className="cursor-pointer transition-colors hover:fill-opacity-40"
              />

              {/* ── Room Walls ────────────────────────────────────────────────── */}
              {layers.walls && walls.map((w) => (
                <line
                  key={w.id}
                  x1={w.start.x}
                  y1={w.start.y}
                  x2={w.end.x}
                  y2={w.end.y}
                  stroke="#94a3b8"
                  strokeWidth={w.thickness || 0.2}
                  strokeLinecap="round"
                />
              ))}

              {/* ── Placed Furniture Footprints ───────────────────────────────── */}
              {layers.furniture && assets.length > 0 && (
                <g name="placed_furniture">
                  {assets.map((asset) => {
                    const isAssetSelected = selectedAssetId === asset.instance_id;
                    const isLocked = !!(asset.is_locked || asset.is_user_locked);
                    const { width, depth } = asset.dimensions;
                    const rot = asset.rotation_deg;

                    return (
                      <g
                        key={asset.instance_id}
                        transform={`translate(${asset.position.x}, ${asset.position.y}) rotate(${rot})`}
                        onMouseDown={(e) => {
                          if (editMode === 'move' && !isLocked) {
                            e.stopPropagation();
                            onSelectAsset(asset);
                            setDraggingAssetId(asset.instance_id);
                          }
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectAsset(asset);
                          if (editMode === 'rotate' && onRotateAsset && !isLocked) {
                            onRotateAsset(asset.instance_id, (rot + 90) % 360);
                          }
                        }}
                        className={`cursor-pointer ${
                          editMode === 'move' && !isLocked
                            ? 'cursor-move'
                            : editMode === 'rotate' && !isLocked
                            ? 'cursor-alias'
                            : ''
                        }`}
                      >
                        {/* Furniture boundary rectangle */}
                        <rect
                          x={-width / 2}
                          y={-depth / 2}
                          width={width}
                          height={depth}
                          fill={isAssetSelected ? '#06b6d4' : isLocked ? '#475569' : '#334155'}
                          fillOpacity={isAssetSelected ? 0.85 : 0.6}
                          stroke={isAssetSelected ? '#ffffff' : isLocked ? '#f59e0b' : '#64748b'}
                          strokeWidth={isAssetSelected ? 0.05 : 0.02}
                          rx={0.05}
                        />

                        {/* Front orientation notch/arrow */}
                        <line
                          x1={0}
                          y1={-depth / 2}
                          x2={0}
                          y2={-depth / 2 + 0.15}
                          stroke={isAssetSelected ? '#ffffff' : '#cbd5e1'}
                          strokeWidth={0.03}
                        />

                        {/* Lock indicator */}
                        {isLocked && (
                          <text
                            x={width / 2 - 0.2}
                            y={-depth / 2 + 0.2}
                            fontSize={0.25}
                            textAnchor="middle"
                            dominantBaseline="central"
                            className="pointer-events-none select-none"
                            transform={`rotate(${-rot})`}
                          >
                            🔒
                          </text>
                        )}

                        {/* Text label */}
                        <text
                          x={0}
                          y={0}
                          fill="#f8fafc"
                          fontSize={0.25}
                          textAnchor="middle"
                          dominantBaseline="central"
                          className="pointer-events-none select-none font-medium"
                          transform={`rotate(${-rot})`}
                        >
                          {asset.asset_name.split(' ')[0]}
                        </text>
                      </g>
                    );
                  })}
                </g>
              )}

              {/* ── Service Points ────────────────────────────────────────────── */}
              {layers.servicePoints && fixtures.length > 0 && (
                <g name="service_points">
                  {fixtures.map((fixture) => {
                    const fixId = fixture.fixture_id || fixture.point_id || '';
                    const isFixSelected = selectedFixtureId === fixId;
                    return (
                      <circle
                        key={fixId}
                        cx={fixture.position.x}
                        cy={fixture.position.y}
                        r={0.12}
                        fill={isFixSelected ? '#06b6d4' : '#f59e0b'}
                        stroke="#ffffff"
                        strokeWidth={0.02}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectFixture(fixture);
                        }}
                        className="cursor-pointer hover:r-0.16 transition-all"
                      />
                    );
                  })}
                </g>
              )}

              {/* Room Label */}
              {layers.roomLabels && (
                <text
                  x={center.x}
                  y={center.y}
                  fill="#94a3b8"
                  fontSize={0.4}
                  textAnchor="middle"
                  dominantBaseline="central"
                  className="pointer-events-none select-none font-semibold"
                >
                  {room.name}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};
