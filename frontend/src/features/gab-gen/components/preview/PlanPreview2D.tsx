"use client";

import React, { useState } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, Compass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GabGenMasterJson, Point2D, FloorPlan } from '../../types';

interface PlanPreview2DProps {
  data: GabGenMasterJson | null;
  selectedFloorIndex: number | 'all';
  selectedRoomId?: string | null;
  onSelectRoom?: (roomId: string) => void;
}

export const PlanPreview2D: React.FC<PlanPreview2DProps> = ({
  data,
  selectedFloorIndex,
  selectedRoomId,
  onSelectRoom
}) => {

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const [viewMode, setViewMode] = useState<'plan' | 'front' | 'side'>('plan');
  const [showLand, setShowLand] = useState(true);
  const [showBuildable, setShowBuildable] = useState(true);
  const [showDimensions, setShowDimensions] = useState(true);
  const [showLabels, setShowLabels] = useState(true);

  if (!data) {
    return (
      <div className="h-[450px] flex items-center justify-center text-muted-foreground text-xs">
        No blueprint data generated yet. Click &quot;Generate Blueprint&quot; to begin.
      </div>
    );
  }

  const landPoly = data.land_info?.source_land_polygon || [];
  const buildablePoly = data.buildable_footprint?.polygon || [];
  const floors = data.floor_plan?.floors || [];

  // Active floors to render (for 'all' on 2D, we show floor cards or pick floor 0 to prevent unreadable overlay)
  const isMultiFloor = floors.length > 1;
  const activeFloor = selectedFloorIndex === 'all'
    ? (floors[0] || null)
    : (floors.find((f) => f.floor_index === selectedFloorIndex) || null);

  // Compute canonical bounding box
  const allPts: Point2D[] = [...landPoly, ...buildablePoly];
  if (activeFloor) {
    activeFloor.rooms.forEach((r) => allPts.push(...r.polygon));
  }

  const minX = allPts.length > 0 ? Math.min(...allPts.map((p) => p.x)) : 0;
  const maxX = allPts.length > 0 ? Math.max(...allPts.map((p) => p.x)) : 20;
  const minY = allPts.length > 0 ? Math.min(...allPts.map((p) => p.y)) : 0;
  const maxY = allPts.length > 0 ? Math.max(...allPts.map((p) => p.y)) : 20;

  const width = Math.max(1, maxX - minX);
  const height = Math.max(1, maxY - minY);
  const padding = 4;

  // Total building elevation height
  const totalBuildingHeight = Math.max(3.5, floors.length * 3.0 + 1.5);
  const elevationViewBox = `${minX - padding} -${totalBuildingHeight + 2} ${width + padding * 2} ${totalBuildingHeight + 4}`;

  // Canonical North-up SVG coordinate transformation (Invert Y so +Y North points upwards)
  const viewBox = viewMode === 'plan' 
    ? `${minX - padding} ${-(maxY + padding)} ${width + padding * 2} ${height + padding * 2}`
    : (viewMode === 'front' 
        ? `${minX - padding} -${totalBuildingHeight + 2} ${width + padding * 2} ${totalBuildingHeight + 4}`
        : `${minY - padding} -${totalBuildingHeight + 2} ${height + padding * 2} ${totalBuildingHeight + 4}`);

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    }
  };

  const handleMouseUp = () => setIsDragging(false);

  return (
    <div className="relative w-full h-[480px] bg-card/60 rounded-xl overflow-hidden border border-border flex flex-col">
      {/* 2D Controls Bar */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-1.5 bg-background/90 backdrop-blur-md p-1.5 rounded-lg border border-border shadow-md max-w-[calc(100%-160px)]">
        {/* Projection Mode Switcher */}
        <div className="flex items-center gap-0.5 bg-muted/60 p-0.5 rounded-md">
          <Button
            size="sm"
            variant={viewMode === 'plan' ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px]"
            onClick={() => setViewMode('plan')}
          >
            Plan View
          </Button>
          <Button
            size="sm"
            variant={viewMode === 'front' ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px]"
            onClick={() => setViewMode('front')}
          >
            Front View
          </Button>
          <Button
            size="sm"
            variant={viewMode === 'side' ? 'default' : 'ghost'}
            className="h-6 px-2 text-[10px]"
            onClick={() => setViewMode('side')}
          >
            Side View
          </Button>
        </div>

        <div className="h-4 w-[1px] bg-border my-auto mx-0.5" />

        <Button
          size="sm"
          variant="ghost"
          className="h-6 w-6 p-0"
          onClick={() => setZoom((z) => Math.min(z + 0.2, 3))}
          title="Zoom In"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 w-6 p-0"
          onClick={() => setZoom((z) => Math.max(z - 0.2, 0.5))}
          title="Zoom Out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 w-6 p-0"
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          title="Reset View"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </Button>

        {viewMode === 'plan' && (
          <>
            <div className="h-4 w-[1px] bg-border my-auto mx-0.5" />
            <Button
              size="sm"
              variant={showLand ? 'secondary' : 'ghost'}
              className="h-6 px-1.5 text-[10px]"
              onClick={() => setShowLand(!showLand)}
            >
              Land
            </Button>
            <Button
              size="sm"
              variant={showBuildable ? 'secondary' : 'ghost'}
              className="h-6 px-1.5 text-[10px]"
              onClick={() => setShowBuildable(!showBuildable)}
            >
              Buildable
            </Button>
            <Button
              size="sm"
              variant={showDimensions ? 'secondary' : 'ghost'}
              className="h-6 px-1.5 text-[10px]"
              onClick={() => setShowDimensions(!showDimensions)}
            >
              Dimensions
            </Button>
            <Button
              size="sm"
              variant={showLabels ? 'secondary' : 'ghost'}
              className="h-6 px-1.5 text-[10px]"
              onClick={() => setShowLabels(!showLabels)}
            >
              Labels
            </Button>
          </>
        )}
      </div>

      {/* North / View Indicator */}
      <div className="absolute top-3 right-3 z-10 bg-background/90 backdrop-blur-md px-2.5 py-1 rounded-lg border border-border flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground shadow-md">
        <Compass className="w-3.5 h-3.5 text-primary" />
        <span>{viewMode === 'plan' ? '+Y North (+X East)' : viewMode === 'front' ? 'Front Elevation (South → North)' : 'Side Elevation (West → East)'}</span>
      </div>

      {/* Notice for All Floors in 2D */}
      {selectedFloorIndex === 'all' && isMultiFloor && (
        <div className="absolute bottom-12 left-3 z-10 bg-background/90 backdrop-blur-md px-2.5 py-1 rounded text-[11px] text-muted-foreground border border-border">
          Showing <strong>Ground Floor (Level 0)</strong>. Select individual floor tabs above to inspect each level.
        </div>
      )}

      {/* SVG Canvas */}
      <div
        className="w-full h-full cursor-grab active:cursor-grabbing flex items-center justify-center"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg
          viewBox={viewBox}
          className="w-full h-full transition-transform duration-75"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: 'center center',
          }}
        >
          <defs>
            <pattern id="grid" width="2" height="2" patternUnits="userSpaceOnUse">
              <path d="M 2 0 L 0 0 0 2" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="0.08" />
            </pattern>
          </defs>
          <rect
            x={minX - padding * 2}
            y={-(maxY + padding * 2)}
            width={width + padding * 4}
            height={height + padding * 4}
            fill="url(#grid)"
          />

          {/* ================= PLAN VIEW ================= */}
          {viewMode === 'plan' && (
            <>
              {/* 1. Legal Land Boundary Polygon (North-up transformed: x, -y) */}
              {showLand && landPoly.length > 2 && (
                <polygon
                  points={landPoly.map((p) => `${p.x},${-p.y}`).join(' ')}
                  fill="rgba(59, 130, 246, 0.05)"
                  stroke="#3b82f6"
                  strokeWidth="0.18"
                  strokeDasharray="0.5, 0.25"
                />
              )}

              {/* 2. Buildable Footprint Polygon */}
              {showBuildable && buildablePoly.length > 2 && (
                <polygon
                  points={buildablePoly.map((p) => `${p.x},${-p.y}`).join(' ')}
                  fill="rgba(16, 185, 129, 0.08)"
                  stroke="#10b981"
                  strokeWidth="0.15"
                />
              )}

              {/* 3. Room Polygons for Active Floor */}
              {activeFloor &&
                activeFloor.rooms.map((rm) => {
                  const isSelected = selectedRoomId === rm.room_id;
                  return (
                    <g
                      key={rm.room_id}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onSelectRoom) onSelectRoom(rm.room_id);
                      }}
                      className="cursor-pointer"
                    >
                      <polygon
                        points={rm.polygon.map((p) => `${p.x},${-p.y}`).join(' ')}
                        fill={
                          isSelected
                            ? 'rgba(236, 72, 153, 0.45)'
                            : rm.is_structural_stair
                            ? 'rgba(234, 179, 8, 0.28)'
                            : 'rgba(99, 102, 241, 0.16)'
                        }
                        stroke={
                          isSelected
                            ? '#ec4899'
                            : rm.is_structural_stair
                            ? '#eab308'
                            : '#818cf8'
                        }
                        strokeWidth={isSelected ? '0.25' : '0.1'}
                      />

                      {showLabels && (
                        <>
                          <text
                            x={rm.center.x}
                            y={-rm.center.y - 0.25}
                            fontSize="0.48"
                            fill="#f8fafc"
                            textAnchor="middle"
                            fontWeight="600"
                            className="pointer-events-none select-none"
                          >
                            {rm.name}
                          </text>
                          <text
                            x={rm.center.x}
                            y={-rm.center.y + 0.3}
                            fontSize="0.34"
                            fill="#94a3b8"
                            textAnchor="middle"
                            className="pointer-events-none select-none"
                          >
                            {rm.area.toFixed(1)} m²
                          </text>
                          {(() => {
                            const xs = rm.polygon.map(p => p.x);
                            const ys = rm.polygon.map(p => p.y);
                            const w = rm.width_m ?? (Math.max(...xs) - Math.min(...xs));
                            const l = rm.length_m ?? (Math.max(...ys) - Math.min(...ys));
                            return (
                              <text
                                x={rm.center.x}
                                y={-rm.center.y + 0.75}
                                fontSize="0.26"
                                fill="#38bdf8"
                                textAnchor="middle"
                                className="pointer-events-none select-none font-mono"
                              >
                                {w.toFixed(1)}m × {l.toFixed(1)}m
                              </text>
                            );
                          })()}
                        </>
                      )}
                    </g>
                  );
                })}

              {/* 4. Wall Segments */}
              {activeFloor &&
                activeFloor.walls.map((w) => (
                  <line
                    key={w.wall_id}
                    x1={w.start.x}
                    y1={-w.start.y}
                    x2={w.end.x}
                    y2={-w.end.y}
                    stroke={w.wall_type === 'exterior' ? '#ffffff' : '#94a3b8'}
                    strokeWidth={w.wall_type === 'exterior' ? '0.22' : '0.12'}
                    strokeLinecap="round"
                  />
                ))}

              {/* 5. Explicit Doors & Openings */}
              {activeFloor &&
                activeFloor.doors &&
                activeFloor.doors.map((d) => (
                  <g key={d.door_id}>
                    <circle
                      cx={d.position.x}
                      cy={-d.position.y}
                      r="0.28"
                      fill={d.is_external_entrance ? '#22c55e' : '#f59e0b'}
                      stroke="#ffffff"
                      strokeWidth="0.06"
                    />
                    {showLabels && (
                      <text
                        x={d.position.x}
                        y={-d.position.y - 0.35}
                        fontSize="0.22"
                        fill={d.is_external_entrance ? '#4ade80' : '#fbbf24'}
                        textAnchor="middle"
                        className="pointer-events-none select-none font-bold"
                      >
                        {d.is_external_entrance ? 'ENTRANCE' : 'DOOR'}
                      </text>
                    )}
                  </g>
                ))}

              {/* 6. Explicit Windows */}
              {activeFloor &&
                activeFloor.windows &&
                activeFloor.windows.map((w) => (
                  <g key={w.window_id}>
                    <rect
                      x={w.position.x - 0.25}
                      y={-w.position.y - 0.08}
                      width="0.5"
                      height="0.16"
                      fill="#38bdf8"
                      stroke="#0284c7"
                      strokeWidth="0.04"
                    />
                    {showLabels && (
                      <text
                        x={w.position.x}
                        y={-w.position.y + 0.3}
                        fontSize="0.20"
                        fill="#38bdf8"
                        textAnchor="middle"
                        className="pointer-events-none select-none font-medium"
                      >
                        WINDOW
                      </text>
                    )}
                  </g>
                ))}

              {/* 7. Edge Dimensions */}
              {showDimensions &&
                landPoly.length > 2 &&
                landPoly.map((p, idx) => {
                  const nextP = landPoly[(idx + 1) % landPoly.length];
                  const midX = (p.x + nextP.x) / 2;
                  const midY = (p.y + nextP.y) / 2;
                  const dist = Math.hypot(nextP.x - p.x, nextP.y - p.y);
                  return (
                    <text
                      key={`dim_${idx}`}
                      x={midX}
                      y={-midY - 0.15}
                      fontSize="0.32"
                      fill="#60a5fa"
                      textAnchor="middle"
                      className="pointer-events-none select-none font-mono"
                    >
                      {dist.toFixed(1)}m
                    </text>
                  );
                })}
            </>
          )}

          {/* ================= FRONT ELEVATION VIEW (X vs Elevation Z) ================= */}
          {viewMode === 'front' && (
            <g>
              {/* Ground Line */}
              <line x1={minX - 3} y1="0" x2={maxX + 3} y2="0" stroke="#475569" strokeWidth="0.25" strokeDasharray="0.6, 0.3" />
              <text x={minX - 2.5} y="0.6" fontSize="0.3" fill="#64748b" className="font-mono">GL ±0.00m (Ground Level)</text>

              {/* Multi-Floor Storey Volumes */}
              {floors.map((fl) => {
                const fBaseZ = fl.elevation;
                const fHeight = fl.floor_height || 3.0;

                return (
                  <g key={`front_${fl.floor_id}`}>
                    {/* Floor Slab line */}
                    <line x1={minX} y1={-(fBaseZ)} x2={maxX} y2={-(fBaseZ)} stroke="#38bdf8" strokeWidth="0.15" />
                    <text x={maxX + 0.5} y={-(fBaseZ + 0.1)} fontSize="0.26" fill="#38bdf8" className="font-mono">
                      {fl.name} (+{fBaseZ.toFixed(1)}m)
                    </text>

                    {/* Rooms in Front Elevation projection */}
                    {fl.rooms.map((rm) => {
                      const xs = rm.polygon.map(p => p.x);
                      const rMinX = Math.min(...xs);
                      const rMaxX = Math.max(...xs);
                      const rW = rMaxX - rMinX;

                      return (
                        <g key={`front_rm_${rm.room_id}`}>
                          <rect
                            x={rMinX}
                            y={-(fBaseZ + fHeight)}
                            width={rW}
                            height={fHeight}
                            fill="rgba(99, 102, 241, 0.18)"
                            stroke="#818cf8"
                            strokeWidth="0.1"
                          />
                          <text
                            x={rMinX + rW / 2}
                            y={-(fBaseZ + fHeight / 2)}
                            fontSize="0.32"
                            fill="#f8fafc"
                            textAnchor="middle"
                            fontWeight="600"
                            className="pointer-events-none select-none"
                          >
                            {rm.name}
                          </text>
                        </g>
                      );
                    })}

                    {/* Front Windows */}
                    {fl.windows && fl.windows.map((w) => (
                      <g key={`front_win_${w.window_id}`}>
                        <rect
                          x={w.position.x - 0.4}
                          y={-(fBaseZ + 1.8)}
                          width="0.8"
                          height="1.0"
                          fill="rgba(56, 189, 248, 0.5)"
                          stroke="#0284c7"
                          strokeWidth="0.08"
                        />
                        <text
                          x={w.position.x}
                          y={-(fBaseZ + 1.2)}
                          fontSize="0.2"
                          fill="#38bdf8"
                          textAnchor="middle"
                          className="pointer-events-none select-none font-bold"
                        >
                          WINDOW
                        </text>
                      </g>
                    ))}

                    {/* Front Entrance / Doors on Ground Floor */}
                    {fl.floor_index === 0 && fl.doors && fl.doors.filter(d => d.is_external_entrance).map((d) => (
                      <g key={`front_door_${d.door_id}`}>
                        <rect
                          x={d.position.x - 0.5}
                          y="-2.1"
                          width="1.0"
                          height="2.1"
                          fill="rgba(34, 197, 94, 0.4)"
                          stroke="#22c55e"
                          strokeWidth="0.1"
                        />
                        <text
                          x={d.position.x}
                          y="-1.0"
                          fontSize="0.24"
                          fill="#4ade80"
                          textAnchor="middle"
                          className="pointer-events-none select-none font-bold"
                        >
                          MAIN ENTRANCE
                        </text>
                      </g>
                    ))}
                  </g>
                );
              })}

              {/* Roof Cap in Front Elevation */}
              {(() => {
                const topZ = floors.length * 3.0;
                const roofH = data?.roof_geometry?.max_height_m || 1.4;
                const rType = data?.roof_geometry?.roof_type || 'gable';
                const midX = (minX + maxX) / 2;

                return (
                  <g>
                    <polygon
                      points={`${minX - 0.6},-${topZ} ${midX},-${topZ + roofH} ${maxX + 0.6},-${topZ}`}
                      fill="rgba(234, 88, 12, 0.3)"
                      stroke="#ea580c"
                      strokeWidth="0.18"
                    />
                    <text x={midX} y={-(topZ + roofH / 2)} fontSize="0.32" fill="#fdba74" textAnchor="middle" className="font-semibold">
                      Roof: {rType.toUpperCase()} (+{(topZ + roofH).toFixed(1)}m)
                    </text>
                  </g>
                );
              })()}
            </g>
          )}

          {/* ================= SIDE ELEVATION VIEW (Y vs Elevation Z) ================= */}
          {viewMode === 'side' && (
            <g>
              {/* Ground Line */}
              <line x1={minY - 3} y1="0" x2={maxY + 3} y2="0" stroke="#475569" strokeWidth="0.25" strokeDasharray="0.6, 0.3" />
              <text x={minY - 2.5} y="0.6" fontSize="0.3" fill="#64748b" className="font-mono">GL ±0.00m (Ground Level)</text>

              {/* Multi-Floor Storey Volumes */}
              {floors.map((fl) => {
                const fBaseZ = fl.elevation;
                const fHeight = fl.floor_height || 3.0;

                return (
                  <g key={`side_${fl.floor_id}`}>
                    <line x1={minY} y1={-(fBaseZ)} x2={maxY} y2={-(fBaseZ)} stroke="#38bdf8" strokeWidth="0.15" />
                    <text x={maxY + 0.5} y={-(fBaseZ + 0.1)} fontSize="0.26" fill="#38bdf8" className="font-mono">
                      {fl.name} (+{fBaseZ.toFixed(1)}m)
                    </text>

                    {/* Rooms in Side Elevation projection */}
                    {fl.rooms.map((rm) => {
                      const ys = rm.polygon.map(p => p.y);
                      const rMinY = Math.min(...ys);
                      const rMaxY = Math.max(...ys);
                      const rL = rMaxY - rMinY;

                      return (
                        <g key={`side_rm_${rm.room_id}`}>
                          <rect
                            x={rMinY}
                            y={-(fBaseZ + fHeight)}
                            width={rL}
                            height={fHeight}
                            fill={rm.is_structural_stair ? "rgba(234, 179, 8, 0.25)" : "rgba(99, 102, 241, 0.18)"}
                            stroke={rm.is_structural_stair ? "#eab308" : "#818cf8"}
                            strokeWidth="0.1"
                          />
                          <text
                            x={rMinY + rL / 2}
                            y={-(fBaseZ + fHeight / 2)}
                            fontSize="0.32"
                            fill="#f8fafc"
                            textAnchor="middle"
                            fontWeight="600"
                            className="pointer-events-none select-none"
                          >
                            {rm.name}
                          </text>
                        </g>
                      );
                    })}

                    {/* Side Windows */}
                    {fl.windows && fl.windows.map((w) => (
                      <g key={`side_win_${w.window_id}`}>
                        <rect
                          x={w.position.y - 0.35}
                          y={-(fBaseZ + 1.8)}
                          width="0.7"
                          height="1.0"
                          fill="rgba(56, 189, 248, 0.5)"
                          stroke="#0284c7"
                          strokeWidth="0.08"
                        />
                        <text
                          x={w.position.y}
                          y={-(fBaseZ + 1.2)}
                          fontSize="0.2"
                          fill="#38bdf8"
                          textAnchor="middle"
                          className="pointer-events-none select-none font-bold"
                        >
                          WINDOW
                        </text>
                      </g>
                    ))}
                  </g>
                );
              })}

              {/* Roof Cap in Side Elevation */}
              {(() => {
                const topZ = floors.length * 3.0;
                const roofH = data?.roof_geometry?.max_height_m || 1.4;
                const rType = data?.roof_geometry?.roof_type || 'gable';
                const midY = (minY + maxY) / 2;

                return (
                  <g>
                    <polygon
                      points={`${minY - 0.6},-${topZ} ${midY},-${topZ + roofH} ${maxY + 0.6},-${topZ}`}
                      fill="rgba(234, 88, 12, 0.3)"
                      stroke="#ea580c"
                      strokeWidth="0.18"
                    />
                    <text x={midY} y={-(topZ + roofH / 2)} fontSize="0.32" fill="#fdba74" textAnchor="middle" className="font-semibold">
                      Roof: {rType.toUpperCase()} (+{(topZ + roofH).toFixed(1)}m)
                    </text>
                  </g>
                );
              })()}
            </g>
          )}
        </svg>
      </div>

      {/* Legend */}
      <div className="absolute bottom-3 right-3 z-10 flex flex-wrap gap-2.5 text-[11px] bg-background/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-border shadow-md">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 border border-blue-500 bg-blue-500/20 rounded-sm" />
          <span className="text-muted-foreground">Land Parcel</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 border border-emerald-500 bg-emerald-500/20 rounded-sm" />
          <span className="text-muted-foreground">Buildable Line</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 border border-indigo-400 bg-indigo-500/20 rounded-sm" />
          <span className="text-muted-foreground">Rooms & Walls</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 border border-amber-400 bg-amber-500/30 rounded-sm" />
          <span className="text-muted-foreground">Stair Core</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 border border-emerald-400 bg-emerald-500/30 rounded-sm" />
          <span className="text-muted-foreground">Entrance / Door</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 border border-sky-400 bg-sky-500/30 rounded-sm" />
          <span className="text-muted-foreground">Window</span>
        </div>
      </div>
    </div>
  );
};
