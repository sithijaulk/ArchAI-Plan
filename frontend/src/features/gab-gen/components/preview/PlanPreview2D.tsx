"use client";

import React, { useState } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, Compass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GabGenMasterJson, Point2D, FloorPlan } from '../../types';

interface PlanPreview2DProps {
  data: GabGenMasterJson | null;
  selectedFloorIndex: number | 'all';
}

export const PlanPreview2D: React.FC<PlanPreview2DProps> = ({ data, selectedFloorIndex }) => {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const [showLand, setShowLand] = useState(true);
  const [showBuildable, setShowBuildable] = useState(true);
  const [showDimensions, setShowDimensions] = useState(true);

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

  // Canonical North-up SVG coordinate transformation (Invert Y so +Y North points upwards)
  const viewBox = `${minX - padding} ${-(maxY + padding)} ${width + padding * 2} ${height + padding * 2}`;

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
      <div className="absolute top-3 left-3 z-10 flex gap-1.5 bg-background/80 backdrop-blur-md p-1.5 rounded-lg border border-border shadow-md">
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0"
          onClick={() => setZoom((z) => Math.min(z + 0.2, 3))}
          title="Zoom In"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0"
          onClick={() => setZoom((z) => Math.max(z - 0.2, 0.5))}
          title="Zoom Out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0"
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          title="Reset View"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </Button>
        <div className="h-4 w-[1px] bg-border my-auto mx-1" />
        <Button
          size="sm"
          variant={showLand ? 'secondary' : 'ghost'}
          className="h-7 px-2 text-[11px]"
          onClick={() => setShowLand(!showLand)}
        >
          Land Boundary
        </Button>
        <Button
          size="sm"
          variant={showBuildable ? 'secondary' : 'ghost'}
          className="h-7 px-2 text-[11px]"
          onClick={() => setShowBuildable(!showBuildable)}
        >
          Buildable Line
        </Button>
        <Button
          size="sm"
          variant={showDimensions ? 'secondary' : 'ghost'}
          className="h-7 px-2 text-[11px]"
          onClick={() => setShowDimensions(!showDimensions)}
        >
          Dimensions
        </Button>
      </div>

      {/* North Indicator */}
      <div className="absolute top-3 right-3 z-10 bg-background/80 backdrop-blur-md px-2.5 py-1 rounded-lg border border-border flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground shadow-md">
        <Compass className="w-3.5 h-3.5 text-primary" />
        <span>+Y North (+X East)</span>
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
            activeFloor.rooms.map((rm) => (
              <g key={rm.room_id}>
                <polygon
                  points={rm.polygon.map((p) => `${p.x},${-p.y}`).join(' ')}
                  fill={
                    rm.is_structural_stair
                      ? 'rgba(234, 179, 8, 0.28)'
                      : 'rgba(99, 102, 241, 0.16)'
                  }
                  stroke={rm.is_structural_stair ? '#eab308' : '#818cf8'}
                  strokeWidth="0.1"
                />
                <text
                  x={rm.center.x}
                  y={-rm.center.y - 0.2}
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
                  y={-rm.center.y + 0.4}
                  fontSize="0.34"
                  fill="#94a3b8"
                  textAnchor="middle"
                  className="pointer-events-none select-none"
                >
                  {rm.area.toFixed(1)} m²
                </text>
              </g>
            ))}

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

          {/* 5. Edge Dimensions */}
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
        </svg>
      </div>

      {/* Legend */}
      <div className="absolute bottom-3 right-3 z-10 flex gap-3 text-[11px] bg-background/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-border shadow-md">
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
      </div>
    </div>
  );
};
