'use client';

import React, { useMemo, useState, useRef, useEffect } from 'react';
import {
  FloorDTO,
  RoomDTO,
  PersistedRoomDesignDTO,
  PlacedAssetPersistedDTO,
  PlacedFixturePointDTO,
  LayerVisibilityState,
} from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';
import { Download, Camera, ZoomIn, ZoomOut, RotateCcw, Compass, Layers, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface PlanView2DProps {
  floor: FloorDTO;
  savedDesigns: Record<string, PersistedRoomDesignDTO>;
  selectedRoomId: string | null;
  isRoomIsolated?: boolean;
  onSelectRoom: (roomId: string | null) => void;
  selectedAssetId: string | null;
  onSelectAsset: (asset: PlacedAssetPersistedDTO) => void;
  selectedFixtureId: string | null;
  onSelectFixture: (fixture: PlacedFixturePointDTO) => void;
  layers: LayerVisibilityState;
  editMode?: 'select' | 'move' | 'rotate';
  draftDesign?: PersistedRoomDesignDTO | null;
  onMoveAsset?: (instanceId: string, x: number, y: number) => void;
  onRotateAsset?: (instanceId: string, deg: number) => void;
  projectName?: string;
}

export const PlanView2D: React.FC<PlanView2DProps> = ({
  floor,
  savedDesigns,
  selectedRoomId,
  isRoomIsolated = false,
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
  projectName = 'ArchAI-Plan Project',
}) => {
  const containerRef = useRef<SVGSVGElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const [draggingAssetId, setDraggingAssetId] = useState<string | null>(null);
  const startPan = useRef({ x: 0, y: 0 });

  // 1. Calculate floor bounding box in meters
  const floorBounds = useMemo(() => {
    const allVerts = floor.rooms.flatMap((r) => r.polygon);
    if (allVerts.length === 0) return { minX: 0, minY: 0, maxX: 10, maxY: 10, width: 10, height: 10 };
    return SceneDataAdapter.computePolygonBounds(allVerts);
  }, [floor.rooms]);

  // If a room is selected, calculate its focused bounding box
  const focusedBounds = useMemo(() => {
    if (!selectedRoomId) return floorBounds;
    const room = floor.rooms.find((r) => r.room_id === selectedRoomId);
    if (!room || !room.polygon || room.polygon.length === 0) return floorBounds;
    return SceneDataAdapter.computePolygonBounds(room.polygon);
  }, [floor.rooms, selectedRoomId, floorBounds]);

  // Selected room object
  const activeRoom = useMemo(() => {
    return floor.rooms.find((r) => r.room_id === selectedRoomId) || null;
  }, [floor.rooms, selectedRoomId]);

  // SVG viewBox calculation with margin
  const margin = selectedRoomId ? (isRoomIsolated ? 1.0 : 1.8) : 2.5;
  const targetBounds = selectedRoomId ? focusedBounds : floorBounds;
  const vbX = targetBounds.minX - margin;
  const vbY = targetBounds.minY - margin;
  const vbW = targetBounds.width + margin * 2;
  const vbH = targetBounds.height + margin * 2;

  // Auto-reset pan when isolated room changes
  useEffect(() => {
    setPan({ x: 0, y: 0 });
    setZoom(1);
  }, [selectedRoomId, isRoomIsolated]);

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

  // ── Render Authentic CAD Block Symbol ───────────────────────────────────────
  const renderCadFurnitureBlock = (
    asset: PlacedAssetPersistedDTO,
    width: number,
    depth: number,
    isAssetSelected: boolean,
    isLocked: boolean
  ) => {
    const name = (asset.asset_name || asset.instance_id || '').toLowerCase();
    const cat = ((asset as any).category || (asset as any).asset_type || '').toLowerCase();
    const isBed = name.includes('bed') || cat.includes('bed');
    const isSofa = name.includes('sofa') || name.includes('couch') || cat.includes('seating') || cat.includes('living');
    const isChair = (name.includes('chair') || name.includes('armchair')) && !isSofa;
    const isDining = name.includes('dining') || cat.includes('dining');
    const isCoffeeTable = name.includes('coffee') || name.includes('center') || name.includes('tea_table');
    const isTv = name.includes('tv') || name.includes('media') || name.includes('entertainment');
    const isKitchen = name.includes('kitchen') || name.includes('cook') || name.includes('stove') || name.includes('sink') || cat.includes('kitchen') || cat.includes('cabinet');
    const isFridge = name.includes('fridge') || name.includes('refrigerator');
    const isWc = name.includes('wc') || name.includes('toilet') || name.includes('commode') || cat.includes('sanitary');
    const isVanity = name.includes('vanity') || name.includes('washbasin') || name.includes('basin');
    const isShower = name.includes('shower') || name.includes('bath') || name.includes('tub');
    const isWardrobe = name.includes('wardrobe') || name.includes('closet') || name.includes('cupboard') || cat.includes('storage');
    const isBalcony = name.includes('balcony') || name.includes('outdoor') || name.includes('patio');

    const primaryColor = isAssetSelected ? '#06b6d4' : isLocked ? '#eab308' : '#38bdf8';
    const fillBg = isAssetSelected ? 'rgba(6, 182, 212, 0.35)' : isLocked ? 'rgba(234, 179, 8, 0.2)' : 'rgba(30, 41, 59, 0.75)';

    // 1. BED CAD BLOCK
    if (isBed) {
      const pillowW = width * 0.36;
      const pillowH = depth * 0.24;
      return (
        <g>
          {/* Mattress Base */}
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.08} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Headboard */}
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth * 0.14} rx={0.03} fill={primaryColor} fillOpacity={0.6} stroke={primaryColor} strokeWidth={0.02} />
          {/* Pillows */}
          <rect x={-width / 2 + width * 0.08} y={-depth / 2 + depth * 0.18} width={pillowW} height={pillowH} rx={0.05} fill="#ffffff" fillOpacity={0.8} stroke={primaryColor} strokeWidth={0.02} />
          <rect x={width / 2 - width * 0.08 - pillowW} y={-depth / 2 + depth * 0.18} width={pillowW} height={pillowH} rx={0.05} fill="#ffffff" fillOpacity={0.8} stroke={primaryColor} strokeWidth={0.02} />
          {/* Folded Duvet / Sheet Line */}
          <line x1={-width / 2 + 0.05} y1={-depth / 2 + depth * 0.48} x2={width / 2 - 0.05} y2={-depth / 2 + depth * 0.48} stroke={primaryColor} strokeWidth={0.03} strokeDasharray="0.1, 0.05" />
          <path d={`M ${-width / 2 + 0.1} ${depth / 2 - 0.08} Q 0 ${depth / 2 - 0.25} ${width / 2 - 0.1} ${depth / 2 - 0.08}`} fill="none" stroke={primaryColor} strokeWidth={0.025} />
        </g>
      );
    }

    // 2. SOFA / COUCH CAD BLOCK
    if (isSofa) {
      const armW = Math.max(0.12, width * 0.14);
      const backD = Math.max(0.14, depth * 0.22);
      return (
        <g>
          {/* Sofa Outer Body */}
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.06} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Backrest Cushion */}
          <rect x={-width / 2 + armW} y={-depth / 2} width={width - armW * 2} height={backD} fill={primaryColor} fillOpacity={0.5} stroke={primaryColor} strokeWidth={0.02} />
          {/* Left Armrest */}
          <rect x={-width / 2} y={-depth / 2} width={armW} height={depth} rx={0.04} fill={primaryColor} fillOpacity={0.4} stroke={primaryColor} strokeWidth={0.02} />
          {/* Right Armrest */}
          <rect x={width / 2 - armW} y={-depth / 2} width={armW} height={depth} rx={0.04} fill={primaryColor} fillOpacity={0.4} stroke={primaryColor} strokeWidth={0.02} />
          {/* Seat Cushion Divider Line */}
          <line x1={0} y1={-depth / 2 + backD} x2={0} y2={depth / 2 - 0.04} stroke={primaryColor} strokeWidth={0.025} />
        </g>
      );
    }

    // 3. DINING TABLE CAD BLOCK (Table + Surrounding Chairs)
    if (isDining) {
      return (
        <g>
          {/* Main Tabletop */}
          <rect x={-width * 0.4} y={-depth * 0.35} width={width * 0.8} height={depth * 0.7} rx={0.06} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Table Placemats */}
          <rect x={-width * 0.3} y={-depth * 0.28} width={width * 0.25} height={depth * 0.22} fill="rgba(255,255,255,0.15)" stroke={primaryColor} strokeWidth={0.015} />
          <rect x={width * 0.05} y={-depth * 0.28} width={width * 0.25} height={depth * 0.22} fill="rgba(255,255,255,0.15)" stroke={primaryColor} strokeWidth={0.015} />
          {/* Top Chairs */}
          <rect x={-width * 0.3} y={-depth / 2} width={width * 0.25} height={depth * 0.12} rx={0.03} fill={primaryColor} fillOpacity={0.4} stroke={primaryColor} strokeWidth={0.02} />
          <rect x={width * 0.05} y={-depth / 2} width={width * 0.25} height={depth * 0.12} rx={0.03} fill={primaryColor} fillOpacity={0.4} stroke={primaryColor} strokeWidth={0.02} />
          {/* Bottom Chairs */}
          <rect x={-width * 0.3} y={depth / 2 - depth * 0.12} width={width * 0.25} height={depth * 0.12} rx={0.03} fill={primaryColor} fillOpacity={0.4} stroke={primaryColor} strokeWidth={0.02} />
          <rect x={width * 0.05} y={depth / 2 - depth * 0.12} width={width * 0.25} height={depth * 0.12} rx={0.03} fill={primaryColor} fillOpacity={0.4} stroke={primaryColor} strokeWidth={0.02} />
        </g>
      );
    }

    // 4. COFFEE TABLE CAD BLOCK
    if (isCoffeeTable) {
      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.08} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          <rect x={-width / 2 + 0.08} y={-depth / 2 + 0.08} width={width - 0.16} height={depth - 0.16} rx={0.04} fill="none" stroke={primaryColor} strokeWidth={0.02} strokeDasharray="0.1, 0.05" />
          <line x1={-width * 0.2} y1={-depth * 0.2} x2={width * 0.2} y2={depth * 0.2} stroke="rgba(255,255,255,0.3)" strokeWidth={0.02} />
        </g>
      );
    }

    // 5. TV MEDIA UNIT CAD BLOCK
    if (isTv) {
      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.04} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Slim TV Screen Profile */}
          <rect x={-width * 0.4} y={-0.04} width={width * 0.8} height={0.08} fill="#ffffff" stroke="#000000" strokeWidth={0.02} />
          {/* TV Stand Base */}
          <polygon points={`${-width * 0.12},0.04 ${width * 0.12},0.04 ${width * 0.08},0.12 ${-width * 0.08},0.12`} fill={primaryColor} />
        </g>
      );
    }

    // 6. KITCHEN COUNTER / SINK / STOVE CAD BLOCK
    if (isKitchen) {
      const isSink = name.includes('sink');
      const isStove = name.includes('stove') || name.includes('cook') || name.includes('hob');

      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.04} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Sink Graphics */}
          {isSink && (
            <g>
              <rect x={-width * 0.35} y={-depth * 0.35} width={width * 0.7} height={depth * 0.7} rx={0.06} fill="rgba(56, 189, 248, 0.25)" stroke="#38bdf8" strokeWidth={0.025} />
              <circle cx={0} cy={-depth * 0.38} r={0.06} fill="#ffffff" />
              <line x1={0} y1={-depth * 0.38} x2={0} y2={-depth * 0.15} stroke="#ffffff" strokeWidth={0.03} />
            </g>
          )}
          {/* 4-Burner Stove Graphics */}
          {isStove && (
            <g>
              <circle cx={-width * 0.22} cy={-depth * 0.2} r={Math.min(width, depth) * 0.16} fill="none" stroke="#f97316" strokeWidth={0.025} />
              <circle cx={width * 0.22} cy={-depth * 0.2} r={Math.min(width, depth) * 0.14} fill="none" stroke="#f97316" strokeWidth={0.025} />
              <circle cx={-width * 0.22} cy={depth * 0.2} r={Math.min(width, depth) * 0.14} fill="none" stroke="#f97316" strokeWidth={0.025} />
              <circle cx={width * 0.22} cy={depth * 0.2} r={Math.min(width, depth) * 0.18} fill="none" stroke="#f97316" strokeWidth={0.025} />
            </g>
          )}
          {!isSink && !isStove && (
            <line x1={-width / 2 + 0.06} y1={depth / 2 - 0.08} x2={width / 2 - 0.06} y2={depth / 2 - 0.08} stroke={primaryColor} strokeWidth={0.02} strokeDasharray="0.1, 0.05" />
          )}
        </g>
      );
    }

    // 7. REFRIGERATOR CAD BLOCK
    if (isFridge) {
      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.04} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Split door line */}
          <line x1={-width / 2} y1={depth / 2 - 0.08} x2={width / 2} y2={depth / 2 - 0.08} stroke={primaryColor} strokeWidth={0.03} />
          <line x1={0} y1={depth / 2 - 0.08} x2={0} y2={depth / 2} stroke={primaryColor} strokeWidth={0.03} />
          <text x={0} y={-0.05} fontSize={0.22} fill="#38bdf8" textAnchor="middle" className="font-bold">FRIDGE</text>
        </g>
      );
    }

    // 8. BATHROOM WC / TOILET COMMODE CAD BLOCK
    if (isWc) {
      const tankD = depth * 0.32;
      return (
        <g>
          {/* Water Cistern Tank at back */}
          <rect x={-width * 0.45} y={-depth / 2} width={width * 0.9} height={tankD} rx={0.04} fill="rgba(20, 184, 166, 0.4)" stroke="#14b8a6" strokeWidth={0.03} />
          <circle cx={0} cy={-depth / 2 + tankD / 2} r={0.04} fill="#ffffff" />
          {/* Toilet Bowl Rim (Oval) */}
          <ellipse cx={0} cy={-depth / 2 + tankD + (depth - tankD) / 2} rx={width * 0.38} ry={(depth - tankD) * 0.48} fill="rgba(20, 184, 166, 0.2)" stroke="#14b8a6" strokeWidth={0.03} />
          {/* Inner Bowl Opening */}
          <ellipse cx={0} cy={-depth / 2 + tankD + (depth - tankD) * 0.55} rx={width * 0.24} ry={(depth - tankD) * 0.32} fill="#ffffff" fillOpacity={0.3} stroke="#14b8a6" strokeWidth={0.02} />
        </g>
      );
    }

    // 9. BATHROOM VANITY / WASHBASIN CAD BLOCK
    if (isVanity) {
      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.04} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Washbasin Oval Bowl */}
          <ellipse cx={0} cy={0} rx={width * 0.36} ry={depth * 0.34} fill="rgba(255,255,255,0.4)" stroke="#14b8a6" strokeWidth={0.025} />
          {/* Tap Faucet */}
          <circle cx={0} cy={-depth * 0.28} r={0.05} fill="#14b8a6" />
          <line x1={0} y1={-depth * 0.28} x2={0} y2={-depth * 0.12} stroke="#14b8a6" strokeWidth={0.03} />
        </g>
      );
    }

    // 10. SHOWER CUBICLE CAD BLOCK
    if (isShower) {
      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.06} fill="rgba(14, 165, 233, 0.15)" stroke="#0284c7" strokeWidth={0.03} />
          {/* Floor Drain Slanted Hatching */}
          <line x1={-width / 2} y1={-depth / 2} x2={width / 2} y2={depth / 2} stroke="#0284c7" strokeWidth={0.02} strokeDasharray="0.1, 0.05" />
          <line x1={-width / 2} y1={depth / 2} x2={width / 2} y2={-depth / 2} stroke="#0284c7" strokeWidth={0.02} strokeDasharray="0.1, 0.05" />
          <circle cx={0} cy={0} r={0.08} fill="#38bdf8" stroke="#ffffff" strokeWidth={0.02} />
        </g>
      );
    }

    // 11. WARDROBE / CLOSET CAD BLOCK
    if (isWardrobe) {
      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.04} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
          {/* Sliding Door Tracks */}
          <line x1={-width / 2} y1={depth / 2 - 0.06} x2={0.05} y2={depth / 2 - 0.06} stroke={primaryColor} strokeWidth={0.03} />
          <line x1={-0.05} y1={depth / 2 - 0.12} x2={width / 2} y2={depth / 2 - 0.12} stroke={primaryColor} strokeWidth={0.03} />
          {/* Clothes Hanger Diagonal Tick Line */}
          <line x1={-width / 2 + 0.1} y1={-depth / 2 + 0.1} x2={width / 2 - 0.1} y2={depth / 2 - 0.2} stroke="rgba(255,255,255,0.2)" strokeWidth={0.02} strokeDasharray="0.15, 0.1" />
        </g>
      );
    }

    // 12. BALCONY / RAILING
    if (isBalcony) {
      return (
        <g>
          <rect x={-width / 2} y={-depth / 2} width={width} height={depth} fill="rgba(16, 185, 129, 0.1)" stroke="#10b981" strokeWidth={0.03} />
          {/* Balustrade Pickets */}
          {Array.from({ length: 6 }).map((_, i) => (
            <line key={`picket_${i}`} x1={-width / 2 + (width / 7) * (i + 1)} y1={-depth / 2} x2={-width / 2 + (width / 7) * (i + 1)} y2={depth / 2} stroke="#10b981" strokeWidth={0.02} strokeDasharray="0.05, 0.05" />
          ))}
        </g>
      );
    }

    // DEFAULT FALLBACK ARCHITECTURAL BLOCK
    return (
      <g>
        <rect x={-width / 2} y={-depth / 2} width={width} height={depth} rx={0.05} fill={fillBg} stroke={primaryColor} strokeWidth={0.03} />
        <line x1={-width / 2} y1={-depth / 2} x2={width / 2} y2={depth / 2} stroke={primaryColor} strokeWidth={0.015} strokeOpacity={0.4} />
      </g>
    );
  };

  return (
    <div
      className="relative w-full h-full bg-[#0a1120] overflow-hidden select-none cursor-grab active:cursor-grabbing flex flex-col"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {/* ── 2D CAD Top Floating Toolbar ──────────────────────────────────── */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-2 bg-slate-900/95 backdrop-blur-md px-3.5 py-1.5 rounded-xl border border-slate-700 shadow-xl text-xs text-slate-200">
        <div className="flex items-center gap-1.5 font-bold text-cyan-400">
          <Layers className="w-3.5 h-3.5" />
          <span>2D CAD Drafting</span>
        </div>
        <span>•</span>
        <span className="font-semibold">{floor.floor_name}</span>
        {activeRoom ? (
          <>
            <span>•</span>
            <span className={`font-bold px-2 py-0.5 rounded border ${isRoomIsolated ? 'bg-indigo-500/25 text-indigo-300 border-indigo-500/50' : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'}`}>
              {isRoomIsolated ? 'Isolated Room:' : 'Focused:'} {activeRoom.name} ({activeRoom.area_sqm.toFixed(1)}m²)
            </span>
            <button
              onClick={() => onSelectRoom(null)}
              className="text-[11px] text-muted-foreground hover:text-white underline ml-1 cursor-pointer"
            >
              Reset to Full Floor
            </button>
          </>
        ) : (
          <span className="text-muted-foreground text-[11px]">(Full Floor View)</span>
        )}

        <div className="h-3.5 w-[1px] bg-slate-700 mx-1" />

        {/* Zoom Controls */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            setZoom((z) => Math.min(z + 0.25, 4));
          }}
          className="p-1 hover:text-cyan-400 text-slate-300"
          title="Zoom In"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setZoom((z) => Math.max(z - 0.25, 0.4));
          }}
          className="p-1 hover:text-cyan-400 text-slate-300"
          title="Zoom Out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          className="p-1 hover:text-cyan-400 text-slate-300"
          title="Reset View"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── SVG Viewport Canvas ─────────────────────────────────────────── */}
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
          {/* Engineering CAD Grid */}
          <pattern id="cad-grid-major-esai" width="5" height="5" patternUnits="userSpaceOnUse">
            <path d="M 5 0 L 0 0 0 5" fill="none" stroke="rgba(56, 189, 248, 0.08)" strokeWidth="0.08" />
          </pattern>
          <pattern id="cad-grid-minor-esai" width="1" height="1" patternUnits="userSpaceOnUse">
            <path d="M 1 0 L 0 0 0 1" fill="none" stroke="rgba(56, 189, 248, 0.04)" strokeWidth="0.03" />
          </pattern>
        </defs>

        {/* Background Grid */}
        <rect x={vbX - 100} y={vbY - 100} width={vbW + 200} height={vbH + 200} fill="url(#cad-grid-minor-esai)" />
        <rect x={vbX - 100} y={vbY - 100} width={vbW + 200} height={vbH + 200} fill="url(#cad-grid-major-esai)" />

        {/* ── Floor Rooms & CAD Furniture Blocks ───────────────────────────── */}
        {floor.rooms.map((room) => {
          const isSelected = selectedRoomId === room.room_id;
          const isOtherDimmed = selectedRoomId && !isSelected;
          const pointsStr = (room.polygon || []).map((v) => `${v.x},${v.y}`).join(' ');
          const activeDesign = selectedRoomId === room.room_id && draftDesign ? draftDesign : savedDesigns[room.room_id];
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
            <g
              key={room.room_id}
              onClick={() => onSelectRoom(room.room_id)}
              opacity={isOtherDimmed ? (isRoomIsolated ? 0.12 : 0.28) : 1.0}
              className="transition-opacity duration-300"
            >
              {/* Room Floor Boundary */}
              <polygon
                points={pointsStr}
                fill={isSelected ? '#0e7490' : '#1e293b'}
                fillOpacity={isSelected ? 0.45 : 0.22}
                stroke={isSelected ? '#06b6d4' : '#64748b'}
                strokeWidth={isSelected ? 0.16 : 0.08}
                className="cursor-pointer transition-colors hover:fill-opacity-50"
              />

              {/* ── Double Architectural Walls ────────────────────────────── */}
              {layers.walls &&
                walls.map((w) => (
                  <line
                    key={w.id}
                    x1={w.start.x}
                    y1={w.start.y}
                    x2={w.end.x}
                    y2={w.end.y}
                    stroke={isSelected ? '#38bdf8' : '#94a3b8'}
                    strokeWidth={w.thickness || 0.22}
                    strokeLinecap="square"
                  />
                ))}

              {/* ── Realistic CAD Architectural Furniture Blocks ───────────── */}
              {layers.furniture && assets.length > 0 && (
                <g name="cad_furniture_blocks">
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
                        {/* Authentic CAD Symbol */}
                        {renderCadFurnitureBlock(asset, width, depth, isAssetSelected, isLocked)}

                        {/* Front orientation notch/arrow */}
                        <line
                          x1={0}
                          y1={-depth / 2}
                          x2={0}
                          y2={-depth / 2 + 0.15}
                          stroke={isAssetSelected ? '#ffffff' : '#38bdf8'}
                          strokeWidth={0.03}
                        />

                        {/* Lock indicator */}
                        {isLocked && (
                          <text
                            x={width / 2 - 0.2}
                            y={-depth / 2 + 0.2}
                            fontSize={0.24}
                            textAnchor="middle"
                            dominantBaseline="central"
                            className="pointer-events-none select-none"
                            transform={`rotate(${-rot})`}
                          >
                            🔒
                          </text>
                        )}

                        {/* CAD Text Label */}
                        <text
                          x={0}
                          y={depth / 2 + 0.22}
                          fill="#f8fafc"
                          fontSize={0.22}
                          textAnchor="middle"
                          dominantBaseline="central"
                          className="pointer-events-none select-none font-mono font-bold"
                          transform={`rotate(${-rot})`}
                        >
                          {asset.asset_name.split(' ')[0].toUpperCase()}
                        </text>
                      </g>
                    );
                  })}
                </g>
              )}

              {/* ── Electrical & Plumbing Service Fixtures ─────────────────── */}
              {layers.servicePoints && fixtures.length > 0 && (
                <g name="cad_service_fixtures">
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
                        strokeWidth={0.03}
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

              {/* ── Room Name & Area Tag ──────────────────────────────────── */}
              {layers.roomLabels && (
                <g className="pointer-events-none select-none">
                  <rect
                    x={center.x - 1.4}
                    y={center.y - 0.55}
                    width={2.8}
                    height={1.1}
                    rx={0.12}
                    fill="rgba(15, 23, 42, 0.88)"
                    stroke={isSelected ? '#06b6d4' : '#475569'}
                    strokeWidth={0.04}
                  />
                  <text
                    x={center.x}
                    y={center.y - 0.2}
                    fill="#f8fafc"
                    fontSize={0.32}
                    textAnchor="middle"
                    className="font-bold tracking-wide"
                  >
                    {room.name.toUpperCase()}
                  </text>
                  <text
                    x={center.x}
                    y={center.y + 0.22}
                    fill="#38bdf8"
                    fontSize={0.26}
                    textAnchor="middle"
                    className="font-mono"
                  >
                    {room.area_sqm.toFixed(1)} m² ({(room.area_sqm * 10.7639).toFixed(0)} sqft)
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>

      {/* ── Architectural Drawing Title Block (Bottom Right) ─────────────── */}
      <div className="absolute bottom-3 right-3 z-10 bg-slate-900/95 backdrop-blur-md px-3.5 py-2 rounded-xl border border-cyan-500/30 shadow-2xl flex flex-col gap-1 text-[11px] min-w-[230px] text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-800 pb-1">
          <span className="font-mono font-bold text-cyan-400 text-xs">ARCHAI • ESAI 2D BLUEPRINT</span>
          <span className="bg-cyan-500/20 text-cyan-300 font-mono text-[10px] px-1.5 py-0.5 rounded">CAD V2</span>
        </div>
        <div className="grid grid-cols-2 gap-x-2 text-[10px]">
          <div>
            <span className="text-muted-foreground block">LEVEL:</span>
            <strong className="text-white">{floor.floor_name}</strong>
          </div>
          <div>
            <span className="text-muted-foreground block">SCOPE:</span>
            <strong className="text-cyan-300">{activeRoom ? activeRoom.name : 'ALL ROOMS'}</strong>
          </div>
          <div>
            <span className="text-muted-foreground block">SCALE:</span>
            <strong className="text-white font-mono">{activeRoom ? '1:50 @ A3' : '1:100 @ A3'}</strong>
          </div>
          <div>
            <span className="text-muted-foreground block">STATUS:</span>
            <strong className="text-emerald-400">DETAILED INTERIOR</strong>
          </div>
        </div>
      </div>
    </div>
  );
};
