'use client';

import React from 'react';
import {
  RoomDTO,
  FloorDTO,
  PersistedRoomDesignDTO,
  PlacedAssetPersistedDTO,
  PlacedFixturePointDTO,
  DesignStalenessRoomReportDTO,
  ValidationDiagnosticDTO,
} from '@/types/esai';

interface ObjectInfoPanelProps {
  selectedRoom: RoomDTO | null;
  selectedFloor: FloorDTO | null;
  savedDesign: PersistedRoomDesignDTO | null;
  stalenessReport?: DesignStalenessRoomReportDTO | null;
  selectedAsset: PlacedAssetPersistedDTO | null;
  selectedFixture: PlacedFixturePointDTO | null;
  onClose: () => void;
  // Phase 7 Interactive Customization Props
  onMoveAsset?: (x: number, y: number) => void;
  onRotateAsset?: (deg: number) => void;
  onResizeAsset?: (w: number, d: number, h: number) => void;
  onToggleLock?: () => void;
  onRemoveAsset?: () => void;
  onOpenReplaceModal?: () => void;
  onUpdateMaterial?: (material: string, color?: string) => void;
  diagnostics?: ValidationDiagnosticDTO[];
}

export const ObjectInfoPanel: React.FC<ObjectInfoPanelProps> = ({
  selectedRoom,
  selectedFloor,
  savedDesign,
  stalenessReport,
  selectedAsset,
  selectedFixture,
  onClose,
  onMoveAsset,
  onRotateAsset,
  onResizeAsset,
  onToggleLock,
  onRemoveAsset,
  onOpenReplaceModal,
  onUpdateMaterial,
  diagnostics = [],
}) => {
  // If nothing is selected, do not render panel
  if (!selectedRoom && !selectedAsset && !selectedFixture) return null;

  const isAssetLocked = !!(selectedAsset?.is_locked || selectedAsset?.is_user_locked);
  const assetDiagnostics = diagnostics.filter(
    (d) => !d.instance_id || d.instance_id === selectedAsset?.instance_id
  );

  const roomAssets: PlacedAssetPersistedDTO[] =
    savedDesign?.placed_assets || [
      ...(savedDesign?.furniture || []),
      ...(savedDesign?.cabinetry || []),
      ...(savedDesign?.appliances || []),
      ...(savedDesign?.sanitary_fixtures || []),
      ...(savedDesign?.decorations || []),
    ];

  return (
    <div className="bg-slate-900/95 backdrop-blur-md w-84 max-h-[85vh] overflow-y-auto rounded-xl border border-slate-800 shadow-2xl p-4 text-xs text-slate-300">
      <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-800">
        <span className="font-semibold text-slate-100 flex items-center gap-1.5">
          <span className="text-cyan-400">ℹ</span>
          {selectedAsset
            ? 'Asset Inspector & Customizer'
            : selectedFixture
            ? 'Service Point Inspector'
            : 'Room Inspector'}
        </span>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-slate-800"
        >
          ✕
        </button>
      </div>

      {/* ── Asset Selected Details & Controls ──────────────────────────────── */}
      {selectedAsset && (
        <div className="space-y-3.5">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-cyan-400 uppercase tracking-wider font-semibold">
                {selectedAsset.category.replace('_', ' ')}
              </span>
              <button
                onClick={onToggleLock}
                title={isAssetLocked ? 'Click to Unlock' : 'Click to Lock'}
                className={`text-[10px] px-2 py-0.5 rounded font-semibold border transition-all ${
                  isAssetLocked
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30'
                    : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                }`}
              >
                {isAssetLocked ? '🔒 Locked' : '🔓 Unlocked'}
              </button>
            </div>
            <div className="text-sm font-bold text-white mt-0.5">
              {selectedAsset.asset_name}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              ID: {selectedAsset.instance_id}
            </div>
          </div>

          {/* Asset-specific Diagnostics */}
          {assetDiagnostics.length > 0 && (
            <div className="space-y-1">
              {assetDiagnostics.map((d, i) => (
                <div
                  key={i}
                  className={`p-2 rounded border text-[11px] ${
                    d.severity === 'error'
                      ? 'bg-rose-950/40 text-rose-300 border-rose-800/50'
                      : 'bg-amber-950/40 text-amber-300 border-amber-800/50'
                  }`}
                >
                  <span className="font-semibold block">{d.code}</span>
                  <span>{d.message}</span>
                </div>
              ))}
            </div>
          )}

          {/* Interactive Position Controls */}
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 space-y-2">
            <span className="text-slate-400 block text-[10px] font-semibold uppercase tracking-wider">
              Position Coordinates (Meters)
            </span>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-slate-500 block mb-0.5">X (m)</label>
                <input
                  type="number"
                  step="0.05"
                  disabled={isAssetLocked}
                  value={selectedAsset.position.x}
                  onChange={(e) =>
                    onMoveAsset &&
                    onMoveAsset(parseFloat(e.target.value) || 0, selectedAsset.position.y)
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-xs disabled:opacity-50"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-500 block mb-0.5">Y (m)</label>
                <input
                  type="number"
                  step="0.05"
                  disabled={isAssetLocked}
                  value={selectedAsset.position.y}
                  onChange={(e) =>
                    onMoveAsset &&
                    onMoveAsset(selectedAsset.position.x, parseFloat(e.target.value) || 0)
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-xs disabled:opacity-50"
                />
              </div>
            </div>
          </div>

          {/* Interactive Rotation Controls */}
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 text-[10px] font-semibold uppercase tracking-wider">
                Rotation (Degrees)
              </span>
              <span className="font-mono text-cyan-300 font-semibold">
                {selectedAsset.rotation_deg.toFixed(0)}°
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {[0, 90, 180, 270].map((deg) => (
                <button
                  key={deg}
                  disabled={isAssetLocked}
                  onClick={() => onRotateAsset && onRotateAsset(deg)}
                  className={`flex-1 py-1 rounded border text-[11px] font-medium transition-all ${
                    Math.round(selectedAsset.rotation_deg) === deg
                      ? 'bg-cyan-500 text-white border-cyan-400'
                      : 'bg-slate-900 text-slate-400 border-slate-700 hover:text-white disabled:opacity-40'
                  }`}
                >
                  {deg}°
                </button>
              ))}
            </div>
          </div>

          {/* Dimensions */}
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 space-y-2">
            <span className="text-slate-400 block text-[10px] font-semibold uppercase tracking-wider">
              Dimensions (W × D × H)
            </span>
            <div className="grid grid-cols-3 gap-1.5">
              <div>
                <label className="text-[9px] text-slate-500 block">Width</label>
                <input
                  type="number"
                  step="0.05"
                  disabled={isAssetLocked}
                  value={selectedAsset.dimensions.width}
                  onChange={(e) =>
                    onResizeAsset &&
                    onResizeAsset(
                      parseFloat(e.target.value) || 0.1,
                      selectedAsset.dimensions.depth,
                      selectedAsset.dimensions.height
                    )
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 text-xs disabled:opacity-50"
                />
              </div>
              <div>
                <label className="text-[9px] text-slate-500 block">Depth</label>
                <input
                  type="number"
                  step="0.05"
                  disabled={isAssetLocked}
                  value={selectedAsset.dimensions.depth}
                  onChange={(e) =>
                    onResizeAsset &&
                    onResizeAsset(
                      selectedAsset.dimensions.width,
                      parseFloat(e.target.value) || 0.1,
                      selectedAsset.dimensions.height
                    )
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 text-xs disabled:opacity-50"
                />
              </div>
              <div>
                <label className="text-[9px] text-slate-500 block">Height</label>
                <input
                  type="number"
                  step="0.05"
                  disabled={isAssetLocked}
                  value={selectedAsset.dimensions.height}
                  onChange={(e) =>
                    onResizeAsset &&
                    onResizeAsset(
                      selectedAsset.dimensions.width,
                      selectedAsset.dimensions.depth,
                      parseFloat(e.target.value) || 0.1
                    )
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 text-xs disabled:opacity-50"
                />
              </div>
            </div>
          </div>

          {/* Material & Color Selector */}
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 space-y-2">
            <span className="text-slate-400 block text-[10px] font-semibold uppercase tracking-wider">
              Finish & Material
            </span>
            <div className="flex items-center gap-2">
              <select
                disabled={isAssetLocked}
                value={selectedAsset.material || 'default'}
                onChange={(e) => onUpdateMaterial && onUpdateMaterial(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-xs disabled:opacity-50"
              >
                <option value="default">Default Catalog Finish</option>
                <option value="MAT_OAK_LIGHT">Light Natural Oak</option>
                <option value="MAT_WALNUT_DARK">Dark Walnut</option>
                <option value="MAT_WHITE_LACQUER">Satin White Lacquer</option>
                <option value="MAT_ANTHRACITE_MATTE">Matte Anthracite</option>
                <option value="MAT_BRUSHED_STEEL">Brushed Stainless Steel</option>
                <option value="MAT_MARBLE_CARRARA">Carrara Marble</option>
                <option value="MAT_CERAMIC_WHITE">Glazed White Ceramic</option>
              </select>
              {selectedAsset.color && (
                <div
                  className="w-6 h-6 rounded border border-slate-700 flex-shrink-0"
                  style={{ backgroundColor: selectedAsset.color }}
                  title={`Color: ${selectedAsset.color}`}
                />
              )}
            </div>
          </div>

          {/* Quick Actions (Replace & Delete) */}
          <div className="flex items-center gap-2 pt-1">
            <button
              disabled={isAssetLocked}
              onClick={onOpenReplaceModal}
              className="flex-1 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 font-semibold transition-all disabled:opacity-40"
            >
              🔄 Replace Variant
            </button>
            <button
              disabled={isAssetLocked}
              onClick={onRemoveAsset}
              className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 font-semibold transition-all disabled:opacity-40"
            >
              🗑 Delete
            </button>
          </div>
        </div>
      )}

      {/* ── Service Point Selected Details ─────────────────────────────────── */}
      {!selectedAsset && selectedFixture && (
        <div className="space-y-3">
          <div>
            <div className="text-[10px] text-amber-400 uppercase tracking-wider font-semibold">
              Service Provision
            </div>
            <div className="text-sm font-bold text-white mt-0.5">
              {(selectedFixture.fixture_type || selectedFixture.point_type || 'service_point').replace('_', ' ')}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              ID: {selectedFixture.fixture_id || selectedFixture.point_id}
            </div>
          </div>

          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 space-y-1.5">
            <div className="flex justify-between">
              <span className="text-slate-500 text-[10px]">Purpose</span>
              <span className="text-slate-200 font-medium">
                {selectedFixture.purpose || selectedFixture.description || 'General Provision'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 text-[10px]">Height from Floor</span>
              <span className="text-slate-200 font-medium">
                {(selectedFixture.height_from_floor_m ?? selectedFixture.installation_height_m ?? 0.3).toFixed(2)} m
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 text-[10px]">Coordinates</span>
              <span className="text-slate-200 font-medium">
                ({selectedFixture.position.x.toFixed(2)}, {selectedFixture.position.y.toFixed(2)}) m
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 text-[10px]">Type Status</span>
              <span
                className={`font-semibold ${
                  selectedFixture.is_proposed ?? selectedFixture.status === 'proposed'
                    ? 'text-amber-400'
                    : 'text-emerald-400'
                }`}
              >
                {selectedFixture.is_proposed ?? selectedFixture.status === 'proposed'
                  ? 'Proposed'
                  : 'Verified Existing'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── Room Selected Details (When neither asset nor fixture selected) ─ */}
      {!selectedAsset && !selectedFixture && selectedRoom && (
        <div className="space-y-3">
          <div>
            <div className="text-[10px] text-cyan-400 uppercase tracking-wider font-semibold">
              {selectedRoom.room_type.replace('_', ' ')}
            </div>
            <div className="text-base font-bold text-white mt-0.5">
              {selectedRoom.name}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              ID: {selectedRoom.room_id} {selectedFloor && `• ${selectedFloor.floor_name}`}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
            <div>
              <span className="text-slate-500 block text-[10px]">Floor Area</span>
              <span className="font-semibold text-slate-200">
                {selectedRoom.area_sqm.toFixed(1)} m²
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Ceiling Height</span>
              <span className="font-semibold text-slate-200">
                {(selectedRoom.ceiling_height ?? selectedRoom.height_m ?? 2.8).toFixed(2)} m
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Openings</span>
              <span className="font-semibold text-slate-200">
                {(selectedRoom.doors?.length || 0)} Doors, {(selectedRoom.windows?.length || 0)} Windows
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Design Revision</span>
              <span className="font-semibold text-slate-200">
                v{savedDesign?.design_revision ?? 0}
              </span>
            </div>
          </div>

          {/* Staleness status */}
          {stalenessReport && (
            <div
              className={`p-2 rounded-lg border text-[11px] ${
                stalenessReport.is_stale
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                  : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              }`}
            >
              <div className="font-semibold flex items-center gap-1">
                <span>{stalenessReport.is_stale ? '⚠️ Design Stale' : '✓ Design Up-to-Date'}</span>
              </div>
              {stalenessReport.is_stale && (
                <div className="text-[10px] mt-0.5 text-amber-400">
                  {stalenessReport.reason || 'Geometry or preferences have updated since design was saved.'}
                </div>
              )}
            </div>
          )}

          {/* Surface Finishes */}
          {savedDesign && (
            <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 space-y-1.5">
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">
                Surface Finishes
              </span>
              <div className="flex justify-between">
                <span className="text-slate-500">Floor:</span>
                <span className="text-slate-200 font-medium">
                  {savedDesign.floor_finish ||
                    (savedDesign.floor_finishes ? JSON.stringify(savedDesign.floor_finishes) : 'Default Oak')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Walls:</span>
                <span className="text-slate-200 font-medium">
                  {savedDesign.wall_finish ||
                    (savedDesign.wall_finishes ? JSON.stringify(savedDesign.wall_finishes) : 'Paint')}{' '}
                  {savedDesign.wall_color && `(${savedDesign.wall_color})`}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Ceiling:</span>
                <span className="text-slate-200 font-medium">
                  {savedDesign.ceiling_finish ||
                    (savedDesign.ceiling_finishes ? JSON.stringify(savedDesign.ceiling_finishes) : 'Smooth Plaster')}
                </span>
              </div>
            </div>
          )}

          {/* Inventory Summary */}
          {savedDesign && (
            <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 block text-[10px] font-semibold uppercase mb-1">
                Placed Inventory ({roomAssets.length} items)
              </span>
              <div className="max-h-28 overflow-y-auto space-y-1">
                {roomAssets.map((a) => (
                  <div key={a.instance_id} className="text-[11px] text-slate-300 flex justify-between">
                    <span>{a.asset_name}</span>
                    <span className="text-slate-500 font-mono text-[10px]">
                      {a.dimensions.width.toFixed(1)}×{a.dimensions.depth.toFixed(1)}m
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
