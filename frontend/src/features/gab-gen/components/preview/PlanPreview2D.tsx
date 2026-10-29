"use client";

import React, { useState, useMemo } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, Compass, Layers, Maximize2, Palette } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GabGenMasterJson, Point2D, FloorPlan } from '../../types';

interface PlanPreview2DProps {
  data: GabGenMasterJson | null;
  selectedFloorIndex: number | 'all';
  selectedRoomId?: string | null;
  onSelectRoom?: (roomId: string) => void;
}

type CadTheme = 'blueprint' | 'dark' | 'paper';

export const PlanPreview2D: React.FC<PlanPreview2DProps> = ({
  data,
  selectedFloorIndex,
  selectedRoomId,
  onSelectRoom,
}) => {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // 3 Authoritative Projections for Component 1:
  // - 'plan': සැලැස්ම (Floor Plan)
  // - 'front': ඉදිරි පෙනුම (Front Elevation)
  // - 'side': පැති පෙනුම (Side Elevation)
  const [viewMode, setViewMode] = useState<'plan' | 'front' | 'side'>('plan');
  const [theme, setTheme] = useState<CadTheme>('blueprint');
  const [showLand, setShowLand] = useState(true);
  const [showBuildable, setShowBuildable] = useState(true);
  const [showDimensions, setShowDimensions] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showGrid, setShowGrid] = useState(true);

  const floors = data?.floor_plan?.floors || [];
  const activeFloor = selectedFloorIndex === 'all'
    ? (floors[0] || null)
    : (floors.find((f) => f.floor_index === selectedFloorIndex) || null);

  // Compute column points (corners of all room polygons) - Hook must be called unconditionally
  const structuralColumns = useMemo(() => {
    if (!activeFloor) return [];
    const corners: { x: number; y: number }[] = [];
    const seen = new Set<string>();

    activeFloor.rooms.forEach((rm) => {
      rm.polygon?.forEach((pt) => {
        const key = `${pt.x.toFixed(2)},${pt.y.toFixed(2)}`;
        if (!seen.has(key)) {
          seen.add(key);
          corners.push(pt);
        }
      });
    });
    return corners;
  }, [activeFloor]);

  if (!data) {
    return (
      <div className="h-[520px] flex items-center justify-center text-muted-foreground text-xs bg-slate-950 rounded-xl border border-border">
        No blueprint data generated yet. Click &quot;Generate Blueprint&quot; to begin.
      </div>
    );
  }

  const landPoly = data.land_info?.source_land_polygon || [];
  const buildablePoly = data.buildable_footprint?.polygon || [];

  // Active floors to render
  const isMultiFloor = floors.length > 1;

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
  const padding = 5;

  // Elevation Heights
  const floorHeight = 3.0;
  const plinthHeight = 0.45;
  const totalLevels = Math.max(1, floors.length);
  const topWallZ = plinthHeight + totalLevels * floorHeight;
  const roofHeight = data.roof_geometry?.max_height_m || 1.6;
  const totalBuildingHeight = topWallZ + roofHeight;
  const roofType = data.roof_geometry?.roof_type || 'gable';

  // SVG Coordinate ViewBoxes
  const viewBox = viewMode === 'plan'
    ? `${minX - padding} ${-(maxY + padding)} ${width + padding * 2} ${height + padding * 2}`
    : viewMode === 'front'
    ? `${minX - padding} -${totalBuildingHeight + 2.5} ${width + padding * 2} ${totalBuildingHeight + 4.5}`
    : `${minY - padding} -${totalBuildingHeight + 2.5} ${height + padding * 2} ${totalBuildingHeight + 4.5}`;

  // Theme styling definitions
  const themeStyles = {
    blueprint: {
      bg: 'bg-[#091b2e]',
      gridStroke: 'rgba(56, 189, 248, 0.08)',
      wallStroke: '#38bdf8',
      wallFill: 'rgba(14, 116, 144, 0.25)',
      innerWallStroke: '#0284c7',
      dimLine: '#0ea5e9',
      dimText: '#7dd3fc',
      labelPrimary: '#f8fafc',
      labelSecondary: '#93c5fd',
      columnFill: '#38bdf8',
      doorStroke: '#34d399',
      windowStroke: '#38bdf8',
      titleBlockBg: 'rgba(15, 23, 42, 0.92)',
      titleBlockBorder: '#0284c7',
    },
    dark: {
      bg: 'bg-[#0b0f17]',
      gridStroke: 'rgba(255, 255, 255, 0.05)',
      wallStroke: '#f1f5f9',
      wallFill: 'rgba(30, 41, 59, 0.45)',
      innerWallStroke: '#94a3b8',
      dimLine: '#64748b',
      dimText: '#cbd5e1',
      labelPrimary: '#ffffff',
      labelSecondary: '#94a3b8',
      columnFill: '#ffffff',
      doorStroke: '#10b981',
      windowStroke: '#38bdf8',
      titleBlockBg: 'rgba(15, 23, 42, 0.95)',
      titleBlockBorder: '#334155',
    },
    paper: {
      bg: 'bg-[#fcfbf9]',
      gridStroke: 'rgba(0, 0, 0, 0.05)',
      wallStroke: '#0f172a',
      wallFill: 'rgba(226, 232, 240, 0.65)',
      innerWallStroke: '#334155',
      dimLine: '#475569',
      dimText: '#0f172a',
      labelPrimary: '#020617',
      labelSecondary: '#475569',
      columnFill: '#0f172a',
      doorStroke: '#059669',
      windowStroke: '#0284c7',
      titleBlockBg: 'rgba(255, 255, 255, 0.96)',
      titleBlockBorder: '#cbd5e1',
    },
  }[theme];

  // Mouse pan handlers
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
    <div className={`relative w-full h-[520px] ${themeStyles.bg} rounded-xl overflow-hidden border border-border flex flex-col select-none transition-colors duration-200`}>
      {/* ── Top CAD Control Bar ────────────────────────────────────────── */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-1.5 bg-background/95 backdrop-blur-md p-1.5 rounded-lg border border-border shadow-lg max-w-[calc(100%-190px)]">
        {/* Projection Mode Switcher */}
        <div className="flex items-center gap-0.5 bg-muted/60 p-0.5 rounded-md">
          <Button
            size="sm"
            variant={viewMode === 'plan' ? 'default' : 'ghost'}
            className="h-6 px-2.5 text-[11px] font-semibold"
            onClick={() => setViewMode('plan')}
          >
            සැලැස්ම (Plan)
          </Button>
          <Button
            size="sm"
            variant={viewMode === 'front' ? 'default' : 'ghost'}
            className="h-6 px-2.5 text-[11px] font-semibold"
            onClick={() => setViewMode('front')}
          >
            ඉදිරි පෙනුම (Front)
          </Button>
          <Button
            size="sm"
            variant={viewMode === 'side' ? 'default' : 'ghost'}
            className="h-6 px-2.5 text-[11px] font-semibold"
            onClick={() => setViewMode('side')}
          >
            පැති පෙනුම (Side)
          </Button>
        </div>

        <div className="h-4 w-[1px] bg-border my-auto mx-0.5" />

        {/* CAD Canvas Theme Switcher */}
        <div className="flex items-center gap-0.5 bg-muted/40 p-0.5 rounded-md">
          <button
            onClick={() => setTheme('blueprint')}
            className={`px-1.5 py-0.5 text-[10px] rounded font-medium ${theme === 'blueprint' ? 'bg-sky-600 text-white font-bold' : 'text-muted-foreground hover:text-foreground'}`}
            title="Blueprint CAD View"
          >
            Blueprint
          </button>
          <button
            onClick={() => setTheme('dark')}
            className={`px-1.5 py-0.5 text-[10px] rounded font-medium ${theme === 'dark' ? 'bg-slate-700 text-white font-bold' : 'text-muted-foreground hover:text-foreground'}`}
            title="Dark CAD Slate"
          >
            Dark Slate
          </button>
          <button
            onClick={() => setTheme('paper')}
            className={`px-1.5 py-0.5 text-[10px] rounded font-medium ${theme === 'paper' ? 'bg-amber-100 text-slate-900 font-bold border border-amber-300' : 'text-muted-foreground hover:text-foreground'}`}
            title="Architectural Paper Sheet"
          >
            Drafting Sheet
          </button>
        </div>

        <div className="h-4 w-[1px] bg-border my-auto mx-0.5" />

        {/* Zoom & Pan Tools */}
        <Button
          size="sm"
          variant="ghost"
          className="h-6 w-6 p-0"
          onClick={() => setZoom((z) => Math.min(z + 0.25, 4))}
          title="Zoom In"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 w-6 p-0"
          onClick={() => setZoom((z) => Math.max(z - 0.25, 0.4))}
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
              Setbacks
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
              Room Tags
            </Button>
            <Button
              size="sm"
              variant={showGrid ? 'secondary' : 'ghost'}
              className="h-6 px-1.5 text-[10px]"
              onClick={() => setShowGrid(!showGrid)}
            >
              CAD Grid
            </Button>
          </>
        )}
      </div>

      {/* ── Top-Right CAD North & Status Indicator ────────────────────── */}
      <div className="absolute top-3 right-3 z-10 bg-background/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-border flex items-center gap-2 text-xs font-mono shadow-md">
        <div className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 border border-primary/30">
          <Compass className="w-4 h-4 text-primary animate-pulse" />
        </div>
        <div className="flex flex-col text-right">
          <span className="font-bold text-foreground">
            {viewMode === 'plan' ? 'NORTH UP (0° Azimuth)' : viewMode === 'front' ? 'FRONT ELEVATION' : 'SIDE ELEVATION'}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {viewMode === 'plan' ? `Scale 1:100 • ${activeFloor?.name || 'Floor Plan'}` : `Scale 1:100 • Orthographic`}
          </span>
        </div>
      </div>

      {/* ── SVG Drafting Viewport ─────────────────────────────────────── */}
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
            {/* Architectural Grid pattern */}
            <pattern id="cad-grid-major" width="5" height="5" patternUnits="userSpaceOnUse">
              <path d="M 5 0 L 0 0 0 5" fill="none" stroke={themeStyles.gridStroke} strokeWidth="0.12" />
            </pattern>
            <pattern id="cad-grid-minor" width="1" height="1" patternUnits="userSpaceOnUse">
              <path d="M 1 0 L 0 0 0 1" fill="none" stroke={themeStyles.gridStroke} strokeWidth="0.04" />
            </pattern>

            {/* Earth hatching for ground section */}
            <pattern id="earth-hatch" width="1.2" height="1.2" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
              <line x1="0" y1="0" x2="0" y2="1.2" stroke="#475569" strokeWidth="0.1" />
            </pattern>

            {/* Concrete / Wall masonry hatching */}
            <pattern id="wall-hatch" width="0.8" height="0.8" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
              <line x1="0" y1="0" x2="0" y2="0.8" stroke={themeStyles.wallStroke} strokeWidth="0.05" strokeOpacity="0.3" />
            </pattern>
          </defs>

          {/* Background Grid */}
          {showGrid && (
            <>
              <rect
                x={minX - padding * 3}
                y={-(maxY + padding * 3)}
                width={width + padding * 6}
                height={height + padding * 6}
                fill="url(#cad-grid-minor)"
              />
              <rect
                x={minX - padding * 3}
                y={-(maxY + padding * 3)}
                width={width + padding * 6}
                height={height + padding * 6}
                fill="url(#cad-grid-major)"
              />
            </>
          )}

          {/* ============================================================= */}
          {/* 1. PLAN VIEW (සැලැස්ම)                                        */}
          {/* ============================================================= */}
          {viewMode === 'plan' && (
            <g id="architectural-plan">
              {/* 1.1 Legal Land Boundary Polygon */}
              {showLand && landPoly.length > 2 && (
                <g id="land-boundary">
                  <polygon
                    points={landPoly.map((p) => `${p.x},${-p.y}`).join(' ')}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="0.18"
                    strokeDasharray="0.6, 0.3"
                  />
                  {/* Boundary Corner Pegs */}
                  {landPoly.map((p, idx) => (
                    <circle key={`peg_${idx}`} cx={p.x} cy={-p.y} r="0.16" fill="#3b82f6" stroke="#ffffff" strokeWidth="0.04" />
                  ))}
                  {/* Legal boundary title */}
                  <text
                    x={landPoly[0].x}
                    y={-landPoly[0].y - 0.4}
                    fontSize="0.32"
                    fill="#3b82f6"
                    className="font-mono font-bold"
                  >
                    SURVEY BOUNDARY (Deed Scale)
                  </text>
                </g>
              )}

              {/* 1.2 Buildable Footprint Setback Line */}
              {showBuildable && buildablePoly.length > 2 && (
                <polygon
                  points={buildablePoly.map((p) => `${p.x},${-p.y}`).join(' ')}
                  fill="rgba(16, 185, 129, 0.04)"
                  stroke="#10b981"
                  strokeWidth="0.12"
                  strokeDasharray="0.4, 0.2"
                />
              )}

              {/* 1.3 Double-Line Architectural Wall Hatching & Rooms */}
              {activeFloor &&
                activeFloor.rooms.map((rm) => {
                  const isSelected = selectedRoomId === rm.room_id;
                  const xs = rm.polygon.map((p) => p.x);
                  const ys = rm.polygon.map((p) => p.y);
                  const rW = rm.width_m ?? (Math.max(...xs) - Math.min(...xs));
                  const rL = rm.length_m ?? (Math.max(...ys) - Math.min(...ys));

                  return (
                    <g
                      key={rm.room_id}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onSelectRoom) onSelectRoom(rm.room_id);
                      }}
                      className="cursor-pointer"
                    >
                      {/* Room boundary fill */}
                      <polygon
                        points={rm.polygon.map((p) => `${p.x},${-p.y}`).join(' ')}
                        fill={
                          isSelected
                            ? 'rgba(236, 72, 153, 0.35)'
                            : rm.is_structural_stair
                            ? 'rgba(234, 179, 8, 0.2)'
                            : themeStyles.wallFill
                        }
                        stroke={isSelected ? '#ec4899' : themeStyles.wallStroke}
                        strokeWidth={isSelected ? '0.28' : '0.18'}
                        strokeLinejoin="miter"
                      />

                      {/* Staircase Treads Graphic if stair core */}
                      {rm.is_structural_stair && (
                        <g>
                          {Array.from({ length: 9 }).map((_, i) => {
                            const stepY = Math.min(...ys) + (rL / 10) * (i + 1);
                            return (
                              <line
                                key={`stair_tread_${i}`}
                                x1={Math.min(...xs)}
                                y1={-stepY}
                                x2={Math.max(...xs)}
                                y2={-stepY}
                                stroke="#eab308"
                                strokeWidth="0.08"
                                strokeDasharray="0.2, 0.1"
                              />
                            );
                          })}
                          <text
                            x={rm.center.x}
                            y={-rm.center.y - 0.2}
                            fontSize="0.28"
                            fill="#fef08a"
                            textAnchor="middle"
                            className="font-bold pointer-events-none"
                          >
                            UP →
                          </text>
                        </g>
                      )}

                      {/* Room Text Tags: Name, Dimensions, Area */}
                      {showLabels && (
                        <g className="pointer-events-none select-none">
                          {/* Room Category Box */}
                          <rect
                            x={rm.center.x - 1.6}
                            y={-rm.center.y - 0.75}
                            width="3.2"
                            height="1.5"
                            rx="0.15"
                            fill={theme === 'paper' ? 'rgba(255,255,255,0.85)' : 'rgba(15,23,42,0.85)'}
                            stroke={themeStyles.innerWallStroke}
                            strokeWidth="0.04"
                          />
                          <text
                            x={rm.center.x}
                            y={-rm.center.y - 0.35}
                            fontSize="0.36"
                            fill={themeStyles.labelPrimary}
                            textAnchor="middle"
                            fontWeight="700"
                            letterSpacing="0.04em"
                          >
                            {rm.name.toUpperCase()}
                          </text>
                          <text
                            x={rm.center.x}
                            y={-rm.center.y + 0.05}
                            fontSize="0.28"
                            fill={themeStyles.labelSecondary}
                            textAnchor="middle"
                            className="font-mono"
                          >
                            {rW.toFixed(1)}m × {rL.toFixed(1)}m
                          </text>
                          <text
                            x={rm.center.x}
                            y={-rm.center.y + 0.45}
                            fontSize="0.26"
                            fill="#38bdf8"
                            textAnchor="middle"
                            className="font-mono font-bold"
                          >
                            {rm.area.toFixed(1)} m² ({(rm.area * 10.7639).toFixed(0)} sqft)
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}

              {/* 1.4 Architectural Wall Linework (Double Lines) */}
              {activeFloor &&
                activeFloor.walls.map((w) => (
                  <line
                    key={w.wall_id}
                    x1={w.start.x}
                    y1={-w.start.y}
                    x2={w.end.x}
                    y2={-w.end.y}
                    stroke={w.wall_type === 'exterior' ? themeStyles.wallStroke : themeStyles.innerWallStroke}
                    strokeWidth={w.wall_type === 'exterior' ? '0.24' : '0.14'}
                    strokeLinecap="square"
                  />
                ))}

              {/* 1.5 Structural Column Markers at Corners */}
              {structuralColumns.map((col, idx) => (
                <rect
                  key={`col_${idx}`}
                  x={col.x - 0.16}
                  y={-col.y - 0.16}
                  width="0.32"
                  height="0.32"
                  fill={themeStyles.columnFill}
                  stroke="#ffffff"
                  strokeWidth="0.04"
                />
              ))}

              {/* 1.6 Architectural Swing Doors (90° Arc + Leaf) */}
              {activeFloor &&
                activeFloor.doors &&
                activeFloor.doors.map((d) => {
                  const r = (d as any).width_m ?? (d as any).width ?? 0.9;
                  const dx = d.position.x;
                  const dy = -d.position.y;
                  const isMain = d.is_external_entrance;

                  return (
                    <g key={d.door_id} className="pointer-events-none">
                      {/* Door hinge point */}
                      <circle cx={dx} cy={dy} r="0.08" fill={isMain ? '#22c55e' : '#f59e0b'} />
                      {/* Door leaf line */}
                      <line
                        x1={dx}
                        y1={dy}
                        x2={dx + r}
                        y2={dy}
                        stroke={isMain ? '#22c55e' : themeStyles.doorStroke}
                        strokeWidth="0.1"
                      />
                      {/* Door swing arc */}
                      <path
                        d={`M ${dx + r} ${dy} A ${r} ${r} 0 0 0 ${dx} ${dy - r}`}
                        fill="none"
                        stroke={isMain ? '#22c55e' : themeStyles.doorStroke}
                        strokeWidth="0.06"
                        strokeDasharray="0.15, 0.08"
                      />
                      {/* Door label */}
                      {showLabels && (
                        <text
                          x={dx + r / 2}
                          y={dy - r - 0.15}
                          fontSize="0.22"
                          fill={isMain ? '#4ade80' : '#fbbf24'}
                          textAnchor="middle"
                          className="font-bold"
                        >
                          {isMain ? 'MAIN ENTRY (D1)' : 'DOOR'}
                        </text>
                      )}
                    </g>
                  );
                })}

              {/* 1.7 Architectural Window Symbols (Double glass lines + frame) */}
              {activeFloor &&
                activeFloor.windows &&
                activeFloor.windows.map((w) => {
                  const wx = w.position.x;
                  const wy = -w.position.y;
                  const wLen = (w as any).width_m ?? (w as any).width ?? 1.2;

                  return (
                    <g key={w.window_id} className="pointer-events-none">
                      {/* Outer Window Sill */}
                      <rect
                        x={wx - wLen / 2}
                        y={wy - 0.14}
                        width={wLen}
                        height="0.28"
                        fill="none"
                        stroke={themeStyles.windowStroke}
                        strokeWidth="0.08"
                      />
                      {/* Inner Glazing Double Lines */}
                      <line
                        x1={wx - wLen / 2}
                        y1={wy - 0.04}
                        x2={wx + wLen / 2}
                        y2={wy - 0.04}
                        stroke="#38bdf8"
                        strokeWidth="0.04"
                      />
                      <line
                        x1={wx - wLen / 2}
                        y1={wy + 0.04}
                        x2={wx + wLen / 2}
                        y2={wy + 0.04}
                        stroke="#38bdf8"
                        strokeWidth="0.04"
                      />
                      {showLabels && (
                        <text
                          x={wx}
                          y={wy - 0.25}
                          fontSize="0.2"
                          fill="#38bdf8"
                          textAnchor="middle"
                          className="font-mono font-semibold"
                        >
                          W ({wLen.toFixed(1)}m)
                        </text>
                      )}
                    </g>
                  );
                })}

              {/* 1.8 Architectural Dimension Chains */}
              {showDimensions && landPoly.length > 2 && (
                <g id="dimension-chains" className="pointer-events-none">
                  {landPoly.map((p, idx) => {
                    const nextP = landPoly[(idx + 1) % landPoly.length];
                    const midX = (p.x + nextP.x) / 2;
                    const midY = (p.y + nextP.y) / 2;
                    const dist = Math.hypot(nextP.x - p.x, nextP.y - p.y);

                    return (
                      <g key={`dim_chain_${idx}`}>
                        <text
                          x={midX}
                          y={-midY - 0.25}
                          fontSize="0.32"
                          fill={themeStyles.dimText}
                          textAnchor="middle"
                          className="font-mono font-bold"
                        >
                          {dist.toFixed(2)}m ({(dist * 3.28084).toFixed(1)}ft)
                        </text>
                      </g>
                    );
                  })}
                </g>
              )}

              {/* 1.9 Graphic Scale Bar */}
              <g transform={`translate(${minX}, ${-(minY - 1.5)})`}>
                <line x1="0" y1="0" x2="5" y2="0" stroke={themeStyles.dimLine} strokeWidth="0.12" />
                <line x1="0" y1="-0.2" x2="0" y2="0.2" stroke={themeStyles.dimLine} strokeWidth="0.12" />
                <line x1="2.5" y1="-0.15" x2="2.5" y2="0.15" stroke={themeStyles.dimLine} strokeWidth="0.08" />
                <line x1="5" y1="-0.2" x2="5" y2="0.2" stroke={themeStyles.dimLine} strokeWidth="0.12" />
                <text x="0" y="0.5" fontSize="0.24" fill={themeStyles.dimText} textAnchor="middle" className="font-mono">0m</text>
                <text x="2.5" y="0.5" fontSize="0.24" fill={themeStyles.dimText} textAnchor="middle" className="font-mono">2.5m</text>
                <text x="5" y="0.5" fontSize="0.24" fill={themeStyles.dimText} textAnchor="middle" className="font-mono">5.0m</text>
              </g>
            </g>
          )}

          {/* ============================================================= */}
          {/* 2. FRONT ELEVATION VIEW (ඉදිරි පෙනුම - Front Facade)          */}
          {/* ============================================================= */}
          {viewMode === 'front' && (
            <g id="front-elevation">
              {/* Earth Hatch Ground Foundation */}
              <rect
                x={minX - 4}
                y="0"
                width={width + 8}
                height="1.5"
                fill="url(#earth-hatch)"
                stroke="#334155"
                strokeWidth="0.1"
              />
              <line x1={minX - 4} y1="0" x2={maxX + 4} y2="0" stroke="#475569" strokeWidth="0.3" />
              <text x={minX - 3.8} y="0.45" fontSize="0.28" fill="#64748b" className="font-mono font-bold">
                GL ±0.00m (NATURAL GROUND LEVEL)
              </text>

              {/* Plinth Level */}
              <line x1={minX - 2} y1={-plinthHeight} x2={maxX + 2} y2={-plinthHeight} stroke="#94a3b8" strokeWidth="0.15" />
              <text x={maxX + 0.8} y={-plinthHeight + 0.08} fontSize="0.24" fill="#94a3b8" className="font-mono">
                PL +0.45m (PLINTH)
              </text>

              {/* Multi-Storey Exterior Facade Volumes */}
              {floors.map((fl, fIdx) => {
                const baseZ = plinthHeight + fIdx * floorHeight;
                const topZ = baseZ + floorHeight;

                return (
                  <g key={`front_fl_${fl.floor_id}`}>
                    {/* Floor Level Datum Line & Indicator */}
                    <line x1={minX - 3} y1={-baseZ} x2={maxX + 3} y2={-baseZ} stroke={themeStyles.dimLine} strokeWidth="0.1" strokeDasharray="0.6, 0.3" />
                    <circle cx={minX - 3} cy={-baseZ} r="0.2" fill="none" stroke="#38bdf8" strokeWidth="0.06" />
                    <text x={maxX + 0.8} y={-baseZ + 0.1} fontSize="0.26" fill="#38bdf8" className="font-mono font-bold">
                      ⌖ {fl.name} F.F.L. (+{baseZ.toFixed(2)}m)
                    </text>

                    {/* Exterior Facade Walls */}
                    {fl.rooms.map((rm) => {
                      const xs = rm.polygon.map((p) => p.x);
                      const rMinX = Math.min(...xs);
                      const rMaxX = Math.max(...xs);
                      const rW = rMaxX - rMinX;

                      return (
                        <g key={`front_facade_rm_${rm.room_id}`}>
                          <rect
                            x={rMinX}
                            y={-topZ}
                            width={rW}
                            height={floorHeight}
                            fill={theme === 'paper' ? '#f1f5f9' : 'rgba(30, 41, 59, 0.55)'}
                            stroke={themeStyles.wallStroke}
                            strokeWidth="0.16"
                          />
                          {/* Facade stringcourses */}
                          <line x1={rMinX} y1={-topZ} x2={rMaxX} y2={-topZ} stroke={themeStyles.innerWallStroke} strokeWidth="0.08" />
                          <text
                            x={rMinX + rW / 2}
                            y={-baseZ - floorHeight / 2}
                            fontSize="0.32"
                            fill={themeStyles.labelSecondary}
                            textAnchor="middle"
                            className="font-bold select-none opacity-60"
                          >
                            {rm.name.toUpperCase()}
                          </text>
                        </g>
                      );
                    })}

                    {/* Front Elevation Windows with Framing & Glazing */}
                    {fl.windows &&
                      fl.windows.map((w) => {
                        const winW = (w as any).width_m ?? (w as any).width ?? 1.4;
                        const winH = 1.2;
                        const winBottomZ = baseZ + 0.9; // Sill height 900mm

                        return (
                          <g key={`front_win_elev_${w.window_id}`}>
                            {/* Window Opening & Outer Casing */}
                            <rect
                              x={w.position.x - winW / 2}
                              y={-(winBottomZ + winH)}
                              width={winW}
                              height={winH}
                              fill="rgba(56, 189, 248, 0.25)"
                              stroke="#0284c7"
                              strokeWidth="0.12"
                            />
                            {/* Window Sill Line */}
                            <line
                              x1={w.position.x - winW / 2 - 0.15}
                              y1={-winBottomZ}
                              x2={w.position.x + winW / 2 + 0.15}
                              y2={-winBottomZ}
                              stroke="#0284c7"
                              strokeWidth="0.14"
                            />
                            {/* Mullion & Transom Divider */}
                            <line
                              x1={w.position.x}
                              y1={-(winBottomZ + winH)}
                              x2={w.position.x}
                              y2={-winBottomZ}
                              stroke="#38bdf8"
                              strokeWidth="0.06"
                            />
                            {/* Glass reflection line */}
                            <line
                              x1={w.position.x - winW / 2 + 0.2}
                              y1={-(winBottomZ + winH - 0.2)}
                              x2={w.position.x - 0.1}
                              y2={-(winBottomZ + 0.3)}
                              stroke="rgba(255,255,255,0.4)"
                              strokeWidth="0.04"
                            />
                          </g>
                        );
                      })}

                    {/* Front Entrance Door on Ground Level */}
                    {fIdx === 0 &&
                      fl.doors &&
                      fl.doors
                        .filter((d) => d.is_external_entrance)
                        .map((d) => {
                          const doorW = (d as any).width_m ?? (d as any).width ?? 1.1;
                          const doorH = 2.1;
                          const doorBottomZ = plinthHeight;

                          return (
                            <g key={`front_door_elev_${d.door_id}`}>
                              {/* Door Frame */}
                              <rect
                                x={d.position.x - doorW / 2}
                                y={-(doorBottomZ + doorH)}
                                width={doorW}
                                height={doorH}
                                fill="rgba(34, 197, 94, 0.2)"
                                stroke="#16a34a"
                                strokeWidth="0.14"
                              />
                              {/* Door Panels */}
                              <rect
                                x={d.position.x - doorW / 2 + 0.1}
                                y={-(doorBottomZ + doorH - 0.1)}
                                width={doorW - 0.2}
                                height={doorH / 2 - 0.15}
                                fill="none"
                                stroke="#22c55e"
                                strokeWidth="0.06"
                              />
                              <rect
                                x={d.position.x - doorW / 2 + 0.1}
                                y={-(doorBottomZ + doorH / 2 - 0.05)}
                                width={doorW - 0.2}
                                height={doorH / 2 - 0.15}
                                fill="none"
                                stroke="#22c55e"
                                strokeWidth="0.06"
                              />
                              {/* Door Handle */}
                              <circle cx={d.position.x + doorW / 2 - 0.18} cy={-(doorBottomZ + 1.0)} r="0.06" fill="#facc15" />
                              <text
                                x={d.position.x}
                                y={-(doorBottomZ + doorH + 0.2)}
                                fontSize="0.24"
                                fill="#22c55e"
                                textAnchor="middle"
                                className="font-bold"
                              >
                                MAIN ENTRANCE
                              </text>
                            </g>
                          );
                        })}
                  </g>
                );
              })}

              {/* Roof Facade Profiles (Gable, Hip, Flat Terrace) */}
              {(() => {
                const midX = (minX + maxX) / 2;
                const overhang = 0.6;

                if (roofType === 'gable') {
                  return (
                    <g id="roof-gable">
                      <polygon
                        points={`${minX - overhang},-${topWallZ} ${midX},-${topWallZ + roofHeight} ${maxX + overhang},-${topWallZ}`}
                        fill="rgba(234, 88, 12, 0.35)"
                        stroke="#ea580c"
                        strokeWidth="0.22"
                      />
                      {/* Ridge line */}
                      <line x1={midX} y1={-(topWallZ + roofHeight)} x2={midX} y2={-topWallZ} stroke="#f97316" strokeWidth="0.08" strokeDasharray="0.3, 0.15" />
                      {/* Ridge datum */}
                      <text x={midX} y={-(topWallZ + roofHeight + 0.3)} fontSize="0.28" fill="#fdba74" textAnchor="middle" className="font-mono font-bold">
                        ▲ RIDGE LEVEL (+{(topWallZ + roofHeight).toFixed(2)}m)
                      </text>
                    </g>
                  );
                }

                if (roofType === 'hip') {
                  const hipInset = (maxX - minX) * 0.2;
                  return (
                    <g id="roof-hip">
                      <polygon
                        points={`${minX - overhang},-${topWallZ} ${minX + hipInset},-${topWallZ + roofHeight} ${maxX - hipInset},-${topWallZ + roofHeight} ${maxX + overhang},-${topWallZ}`}
                        fill="rgba(234, 88, 12, 0.35)"
                        stroke="#ea580c"
                        strokeWidth="0.22"
                      />
                      <line x1={minX + hipInset} y1={-(topWallZ + roofHeight)} x2={maxX - hipInset} y2={-(topWallZ + roofHeight)} stroke="#fdba74" strokeWidth="0.12" />
                    </g>
                  );
                }

                // Flat slab / Accessible rooftop parapet
                return (
                  <g id="roof-flat">
                    <rect
                      x={minX - 0.2}
                      y={-(topWallZ + 1.0)}
                      width={width + 0.4}
                      height="1.0"
                      fill="rgba(100, 116, 139, 0.3)"
                      stroke="#64748b"
                      strokeWidth="0.16"
                    />
                    <text x={midX} y={-(topWallZ + 0.4)} fontSize="0.28" fill="#94a3b8" textAnchor="middle" className="font-mono font-bold">
                      PARAPET LEVEL (+{(topWallZ + 1.0).toFixed(2)}m)
                    </text>
                  </g>
                );
              })()}

              {/* Total Height Dimension String on Left Side */}
              <g id="elevation-height-dimension">
                <line x1={minX - 2.5} y1="0" x2={minX - 2.5} y2={-totalBuildingHeight} stroke={themeStyles.dimLine} strokeWidth="0.1" />
                <line x1={minX - 2.8} y1="0" x2={minX - 2.2} y2="0" stroke={themeStyles.dimLine} strokeWidth="0.12" />
                <line x1={minX - 2.8} y1={-totalBuildingHeight} x2={minX - 2.2} y2={-totalBuildingHeight} stroke={themeStyles.dimLine} strokeWidth="0.12" />
                <text
                  x={minX - 2.7}
                  y={-totalBuildingHeight / 2}
                  fontSize="0.32"
                  fill="#38bdf8"
                  textAnchor="middle"
                  className="font-mono font-bold"
                  transform={`rotate(-90 ${minX - 2.7} ${-totalBuildingHeight / 2})`}
                >
                  TOTAL HEIGHT {totalBuildingHeight.toFixed(2)}m
                </text>
              </g>
            </g>
          )}

          {/* ============================================================= */}
          {/* 3. SIDE ELEVATION VIEW (පැති පෙනුම - Side Facade)              */}
          {/* ============================================================= */}
          {viewMode === 'side' && (
            <g id="side-elevation">
              {/* Earth Foundation Ground */}
              <rect
                x={minY - 4}
                y="0"
                width={height + 8}
                height="1.5"
                fill="url(#earth-hatch)"
                stroke="#334155"
                strokeWidth="0.1"
              />
              <line x1={minY - 4} y1="0" x2={maxY + 4} y2="0" stroke="#475569" strokeWidth="0.3" />
              <text x={minY - 3.8} y="0.45" fontSize="0.28" fill="#64748b" className="font-mono font-bold">
                GL ±0.00m (NATURAL GROUND LEVEL)
              </text>

              {/* Plinth Level */}
              <line x1={minY - 2} y1={-plinthHeight} x2={maxY + 2} y2={-plinthHeight} stroke="#94a3b8" strokeWidth="0.15" />
              <text x={maxY + 0.8} y={-plinthHeight + 0.08} fontSize="0.24" fill="#94a3b8" className="font-mono">
                PL +0.45m (PLINTH)
              </text>

              {/* Multi-Storey Side Volumes along Building Depth */}
              {floors.map((fl, fIdx) => {
                const baseZ = plinthHeight + fIdx * floorHeight;
                const topZ = baseZ + floorHeight;

                return (
                  <g key={`side_fl_${fl.floor_id}`}>
                    <line x1={minY - 3} y1={-baseZ} x2={maxY + 3} y2={-baseZ} stroke={themeStyles.dimLine} strokeWidth="0.1" strokeDasharray="0.6, 0.3" />
                    <text x={maxY + 0.8} y={-baseZ + 0.1} fontSize="0.26" fill="#38bdf8" className="font-mono font-bold">
                      ⌖ {fl.name} F.F.L. (+{baseZ.toFixed(2)}m)
                    </text>

                    {/* Side Room Facade Extrusions */}
                    {fl.rooms.map((rm) => {
                      const ys = rm.polygon.map((p) => p.y);
                      const rMinY = Math.min(...ys);
                      const rMaxY = Math.max(...ys);
                      const rDepth = rMaxY - rMinY;

                      return (
                        <g key={`side_facade_rm_${rm.room_id}`}>
                          <rect
                            x={rMinY}
                            y={-topZ}
                            width={rDepth}
                            height={floorHeight}
                            fill={theme === 'paper' ? '#f1f5f9' : 'rgba(30, 41, 59, 0.55)'}
                            stroke={themeStyles.wallStroke}
                            strokeWidth="0.16"
                          />
                          <text
                            x={rMinY + rDepth / 2}
                            y={-baseZ - floorHeight / 2}
                            fontSize="0.32"
                            fill={themeStyles.labelSecondary}
                            textAnchor="middle"
                            className="font-bold select-none opacity-60"
                          >
                            {rm.name.toUpperCase()}
                          </text>
                        </g>
                      );
                    })}

                    {/* Side Elevation Windows */}
                    {fl.windows &&
                      fl.windows.map((w) => {
                        const winW = (w as any).width_m ?? (w as any).width ?? 1.2;
                        const winH = 1.2;
                        const winBottomZ = baseZ + 0.9;

                        return (
                          <g key={`side_win_elev_${w.window_id}`}>
                            <rect
                              x={w.position.y - winW / 2}
                              y={-(winBottomZ + winH)}
                              width={winW}
                              height={winH}
                              fill="rgba(56, 189, 248, 0.25)"
                              stroke="#0284c7"
                              strokeWidth="0.12"
                            />
                            <line
                              x1={w.position.y}
                              y1={-(winBottomZ + winH)}
                              x2={w.position.y}
                              y2={-winBottomZ}
                              stroke="#38bdf8"
                              strokeWidth="0.06"
                            />
                          </g>
                        );
                      })}
                  </g>
                );
              })}

              {/* Roof Profile along Side Pitch */}
              {(() => {
                const midY = (minY + maxY) / 2;
                const overhang = 0.6;

                return (
                  <g id="side-roof-profile">
                    <polygon
                      points={`${minY - overhang},-${topWallZ} ${midY},-${topWallZ + roofHeight} ${maxY + overhang},-${topWallZ}`}
                      fill="rgba(234, 88, 12, 0.35)"
                      stroke="#ea580c"
                      strokeWidth="0.22"
                    />
                    <text x={midY} y={-(topWallZ + roofHeight + 0.3)} fontSize="0.28" fill="#fdba74" textAnchor="middle" className="font-mono font-bold">
                      ▲ SIDE ROOF SLOPE (+{(topWallZ + roofHeight).toFixed(2)}m)
                    </text>
                  </g>
                );
              })()}
            </g>
          )}
        </svg>
      </div>

      {/* ── Architectural Drawing Title Block (Bottom Right) ───────────── */}
      <div className={`absolute bottom-3 right-3 z-10 ${themeStyles.titleBlockBg} backdrop-blur-md px-3.5 py-2.5 rounded-lg border ${themeStyles.titleBlockBorder} shadow-2xl flex flex-col gap-1 text-[11px] min-w-[240px]`}>
        <div className="flex items-center justify-between border-b border-border/60 pb-1">
          <span className="font-mono font-black text-primary tracking-wider uppercase text-xs">
            ARCHAI • GAB-GEN BLUEPRINT
          </span>
          <span className="text-[10px] font-mono bg-primary/20 text-primary px-1.5 py-0.5 rounded">
            REV {data.project_revision || 1}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-2 text-[10px]">
          <div>
            <span className="text-muted-foreground block">DRAWING:</span>
            <strong className="text-foreground">
              {viewMode === 'plan' ? 'FLOOR PLAN (සැලැස්ම)' : viewMode === 'front' ? 'FRONT ELEVATION (ඉදිරි)' : 'SIDE ELEVATION (පැති)'}
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground block">SCALE:</span>
            <strong className="text-foreground font-mono">1:100 @ A3</strong>
          </div>
          <div>
            <span className="text-muted-foreground block">STATUS:</span>
            <strong className="text-emerald-400">APPROVED MASTER</strong>
          </div>
          <div>
            <span className="text-muted-foreground block">DATE:</span>
            <strong className="text-foreground font-mono">2026-10-23</strong>
          </div>
        </div>
      </div>
    </div>
  );
};
