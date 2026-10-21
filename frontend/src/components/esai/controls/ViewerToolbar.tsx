'use client';

import React from 'react';
import { FloorDTO, RoomDTO, ViewCameraMode } from '@/types/esai';

interface ViewerToolbarProps {
  floors: FloorDTO[];
  selectedFloorId: string | null;
  onSelectFloor: (floorId: string | null) => void;
  selectedRoomId: string | null;
  onSelectRoom: (roomId: string | null) => void;
  viewMode: '3d' | '2d' | 'split';
  onChangeViewMode: (mode: '3d' | '2d' | 'split') => void;
  cameraMode: ViewCameraMode;
  onChangeCameraMode: (mode: ViewCameraMode) => void;
  isolateFloor: boolean;
  onToggleIsolateFloor: () => void;
  explodedView: boolean;
  onToggleExplodedView: () => void;
  onResetCamera: () => void;
  onOpenExport?: () => void;
}

export const ViewerToolbar: React.FC<ViewerToolbarProps> = ({
  floors,
  selectedFloorId,
  onSelectFloor,
  selectedRoomId,
  onSelectRoom,
  viewMode,
  onChangeViewMode,
  cameraMode,
  onChangeCameraMode,
  isolateFloor,
  onToggleIsolateFloor,
  explodedView,
  onToggleExplodedView,
  onResetCamera,
  onOpenExport,
}) => {
  // Available rooms for selected floor or all floors
  const availableRooms: RoomDTO[] = React.useMemo(() => {
    if (selectedFloorId) {
      const f = floors.find((fl) => fl.floor_id === selectedFloorId);
      return f ? f.rooms : [];
    }
    return floors.flatMap((f) => f.rooms);
  }, [floors, selectedFloorId]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/90 backdrop-blur-md px-4 py-2.5 rounded-xl border border-slate-800 shadow-xl text-xs text-slate-200">
      {/* ── Floor & Room Navigation ────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <label className="text-slate-400 font-medium">Floor:</label>
        <select
          value={selectedFloorId || ''}
          onChange={(e) => {
            const val = e.target.value || null;
            onSelectFloor(val);
            onSelectRoom(null);
          }}
          className="bg-slate-800 text-white rounded-lg px-2.5 py-1.5 border border-slate-700 focus:outline-none focus:ring-1 focus:ring-cyan-500 font-medium"
        >
          <option value="">All Floors ({floors.length})</option>
          {floors.map((f) => (
            <option key={f.floor_id} value={f.floor_id}>
              {f.floor_name} (L{f.level_index})
            </option>
          ))}
        </select>

        <label className="text-slate-400 font-medium ml-2">Room:</label>
        <select
          value={selectedRoomId || ''}
          onChange={(e) => onSelectRoom(e.target.value || null)}
          className="bg-slate-800 text-white rounded-lg px-2.5 py-1.5 border border-slate-700 focus:outline-none focus:ring-1 focus:ring-cyan-500 font-medium max-w-[180px] truncate"
        >
          <option value="">All Rooms ({availableRooms.length})</option>
          {availableRooms.map((r) => (
            <option key={r.room_id} value={r.room_id}>
              {r.name} ({r.area_sqm.toFixed(1)}m²)
            </option>
          ))}
        </select>
      </div>

      {/* ── 2D / 3D / Split Display Mode ───────────────────────────────────── */}
      <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-800">
        <button
          onClick={() => onChangeViewMode('3d')}
          className={`px-3 py-1 rounded-md font-medium transition-all ${
            viewMode === '3d'
              ? 'bg-cyan-500 text-white shadow-sm'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          3D Scene
        </button>
        <button
          onClick={() => onChangeViewMode('2d')}
          className={`px-3 py-1 rounded-md font-medium transition-all ${
            viewMode === '2d'
              ? 'bg-cyan-500 text-white shadow-sm'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          2D Plan
        </button>
        <button
          onClick={() => onChangeViewMode('split')}
          className={`px-3 py-1 rounded-md font-medium transition-all ${
            viewMode === 'split'
              ? 'bg-cyan-500 text-white shadow-sm'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Split View
        </button>
      </div>

      {/* ── Camera Modes (Only relevant in 3D / Split) ─────────────────────── */}
      {viewMode !== '2d' && (
        <div className="flex items-center gap-1 bg-slate-950 p-0.5 rounded-lg border border-slate-800">
          {(
            [
              { id: 'perspective', label: 'Perspective' },
              { id: 'top_down', label: 'Top-Down' },
              { id: 'isometric', label: 'Isometric' },
              { id: 'walkthrough', label: 'Walkthrough' },
            ] as const
          ).map((mode) => (
            <button
              key={mode.id}
              onClick={() => onChangeCameraMode(mode.id)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                cameraMode === mode.id
                  ? 'bg-slate-800 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>
      )}

      {/* ── Building Inspection Toggles & Camera Reset ─────────────────────── */}
      <div className="flex items-center gap-2">
        {selectedFloorId && (
          <button
            onClick={onToggleIsolateFloor}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              isolateFloor
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
            }`}
            title="Show only selected floor"
          >
            {isolateFloor ? '✓ Floor Isolated' : 'Isolate Floor'}
          </button>
        )}

        {floors.length > 1 && (
          <button
            onClick={onToggleExplodedView}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              explodedView
                ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
            }`}
            title="Vertically separate floors for interior inspection"
          >
            {explodedView ? '✓ Exploded' : 'Explode Floors'}
          </button>
        )}

        <button
          onClick={onResetCamera}
          className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs font-medium transition-all"
          title="Reset camera target and zoom"
        >
          Reset Camera
        </button>

        {onOpenExport && (
          <button
            onClick={onOpenExport}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium shadow-md shadow-cyan-900/40 text-xs transition-all"
            title="Export Professional PDF Report & Schedules"
          >
            <span>📄</span>
            <span>Export Report</span>
          </button>
        )}
      </div>
    </div>
  );
};
