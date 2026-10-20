'use client';

import React, { useState } from 'react';
import { PlacedAssetPersistedDTO, RoomEditValidateResponse } from '@/types/esai';

export type EditInteractionMode = 'select' | 'move' | 'rotate';

interface EditorToolbarProps {
  mode: EditInteractionMode;
  onChangeMode: (mode: EditInteractionMode) => void;
  selectedAsset: PlacedAssetPersistedDTO | null;
  canUndo: boolean;
  canRedo: boolean;
  isDirty: boolean;
  isSaving: boolean;
  isValidating: boolean;
  isRegenerating: boolean;
  validationResult: RoomEditValidateResponse | null;
  errorMessage: string | null;
  onUndo: () => void;
  onRedo: () => void;
  onToggleLock: () => void;
  onRemoveAsset: () => void;
  onOpenCatalog: () => void;
  onSave: () => void;
  onDiscard: () => void;
  onRegenerateUnlocked: () => void;
}

export const EditorToolbar: React.FC<EditorToolbarProps> = ({
  mode,
  onChangeMode,
  selectedAsset,
  canUndo,
  canRedo,
  isDirty,
  isSaving,
  isValidating,
  isRegenerating,
  validationResult,
  errorMessage,
  onUndo,
  onRedo,
  onToggleLock,
  onRemoveAsset,
  onOpenCatalog,
  onSave,
  onDiscard,
  onRegenerateUnlocked,
}) => {
  const isAssetLocked = !!(selectedAsset?.is_locked || selectedAsset?.is_user_locked);
  const hasErrors = validationResult && !validationResult.hard_constraints_passed;

  return (
    <div className="flex flex-col gap-2">
      {/* ── Main Toolbar Bar ────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-900/95 backdrop-blur-md px-3.5 py-2 rounded-xl border border-slate-800 shadow-xl text-xs text-slate-200">
        {/* Interaction Modes */}
        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            onClick={() => onChangeMode('select')}
            title="Selection Mode"
            className={`px-2.5 py-1 rounded font-medium transition-all ${
              mode === 'select'
                ? 'bg-cyan-500 text-white shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            👆 Select
          </button>
          <button
            onClick={() => onChangeMode('move')}
            title="Move Mode (Drag assets in 2D/3D)"
            className={`px-2.5 py-1 rounded font-medium transition-all ${
              mode === 'move'
                ? 'bg-cyan-500 text-white shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            ✥ Move
          </button>
          <button
            onClick={() => onChangeMode('rotate')}
            title="Rotate Mode (Click or handle to rotate)"
            className={`px-2.5 py-1 rounded font-medium transition-all ${
              mode === 'rotate'
                ? 'bg-cyan-500 text-white shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            ↻ Rotate
          </button>
        </div>

        {/* Selected Asset Actions */}
        <div className="flex items-center gap-1.5 border-l border-r border-slate-800 px-2">
          {selectedAsset ? (
            <>
              <button
                onClick={onToggleLock}
                title={isAssetLocked ? 'Unlock Asset (Enable repositioning)' : 'Lock Asset (Prevent movement & preserve in regeneration)'}
                className={`flex items-center gap-1 px-2.5 py-1 rounded border font-medium transition-all ${
                  isAssetLocked
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30'
                    : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                }`}
              >
                <span>{isAssetLocked ? '🔒 Locked' : '🔓 Unlocked'}</span>
              </button>

              <button
                onClick={onRemoveAsset}
                disabled={isAssetLocked}
                title={isAssetLocked ? 'Unlock asset first before removing' : 'Remove Asset'}
                className="px-2 py-1 rounded bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20 disabled:opacity-40 disabled:cursor-not-allowed font-medium"
              >
                🗑 Remove
              </button>
            </>
          ) : (
            <span className="text-[11px] text-slate-500 italic">Select an asset to edit</span>
          )}

          <button
            onClick={onOpenCatalog}
            title="Add Furniture from Catalog"
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 text-cyan-300 border border-slate-700 hover:bg-slate-700 font-medium ml-1"
          >
            <span>+ Add Asset</span>
          </button>
        </div>

        {/* History Controls (Undo / Redo) */}
        <div className="flex items-center gap-1">
          <button
            onClick={onUndo}
            disabled={!canUndo}
            title="Undo (Ctrl+Z)"
            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-700"
          >
            ↩ Undo
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo}
            title="Redo (Ctrl+Y)"
            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-700"
          >
            ↪ Redo
          </button>
        </div>

        {/* Persistence & Selective Regeneration */}
        <div className="flex items-center gap-2">
          {/* Selective GA Regeneration */}
          <button
            onClick={onRegenerateUnlocked}
            disabled={isRegenerating || isSaving}
            title="Re-optimize unlocked furniture using the Genetic Algorithm while preserving locked items"
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/40 font-medium transition-all disabled:opacity-40"
          >
            <span className={isRegenerating ? 'animate-spin' : ''}>⚡</span>
            <span>{isRegenerating ? 'Optimizing...' : 'Regenerate Unlocked'}</span>
          </button>

          {/* Discard Edits */}
          {isDirty && (
            <button
              onClick={onDiscard}
              disabled={isSaving}
              className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-medium"
            >
              Discard
            </button>
          )}

          {/* Save Transactionally */}
          <button
            onClick={onSave}
            disabled={!isDirty || hasErrors || isSaving}
            title={
              !isDirty
                ? 'No pending changes to save'
                : hasErrors
                ? 'Resolve collision/boundary violations before saving'
                : 'Save changes transactionally to Master JSON'
            }
            className={`flex items-center gap-1.5 px-3.5 py-1 rounded-lg font-semibold transition-all ${
              !isDirty
                ? 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                : hasErrors
                ? 'bg-rose-900/40 text-rose-300 border border-rose-700/60 cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-950/50'
            }`}
          >
            <span>{isSaving ? 'Saving...' : 'Save Changes'}</span>
          </button>
        </div>
      </div>

      {/* ── Validation Feedback Banner ───────────────────────────────────── */}
      {isValidating && (
        <div className="flex items-center gap-2 bg-slate-900/90 text-cyan-300 border border-cyan-800/40 px-3 py-1.5 rounded-lg text-xs">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
          <span>Validating geometry and clearances with Neufert & Shapely rules...</span>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-center gap-2 bg-rose-950/90 text-rose-200 border border-rose-800/60 px-3 py-1.5 rounded-lg text-xs">
          <span>❌</span>
          <span>{errorMessage}</span>
        </div>
      )}

      {validationResult && validationResult.diagnostics.length > 0 && (
        <div className="flex flex-col gap-1 bg-slate-900/95 border border-amber-800/50 p-2.5 rounded-xl shadow-lg text-xs">
          <div className="flex items-center justify-between font-semibold text-amber-300 border-b border-amber-900/40 pb-1">
            <span>Spatial & Ergonomic Diagnostics ({validationResult.diagnostics.length})</span>
            <span className="text-[10px] text-slate-400">
              Score: {(validationResult.ergonomic_score * 100).toFixed(0)}%
            </span>
          </div>
          <div className="max-h-24 overflow-y-auto space-y-1 mt-1 pr-1">
            {validationResult.diagnostics.map((d, i) => (
              <div
                key={i}
                className={`text-[11px] flex items-start gap-1.5 p-1 rounded ${
                  d.severity === 'error'
                    ? 'bg-rose-950/40 text-rose-300 border border-rose-900/40'
                    : 'bg-amber-950/30 text-amber-300 border border-amber-900/30'
                }`}
              >
                <span>{d.severity === 'error' ? '⛔' : '⚠️'}</span>
                <div>
                  <span className="font-semibold">{d.code}:</span> {d.message}
                  {d.suggested_correction && (
                    <span className="text-slate-400 block text-[10px] italic">
                      Suggestion: {d.suggested_correction}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
