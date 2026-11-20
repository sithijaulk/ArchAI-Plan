'use client';

import React, { useState, useMemo, useEffect, Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import * as THREE from 'three';
import {
  SceneDataResponse,
  ViewCameraMode,
  LayerVisibilityState,
  ViewerSelectionState,
  PlacedAssetPersistedDTO,
  PlacedFixturePointDTO,
  PersistedRoomDesignDTO,
} from '@/types/esai';
import { BuildingScene } from './BuildingScene';
import { CameraController } from './CameraController';
import { WalkthroughController } from './WalkthroughController';
import { PlanView2D } from './PlanView2D';
import { ViewerToolbar } from '../controls/ViewerToolbar';
import { LayerControls } from '../controls/LayerControls';
import { ObjectInfoPanel } from '../controls/ObjectInfoPanel';
import { EditorToolbar, EditInteractionMode } from '../controls/EditorToolbar';
import { CatalogBrowserModal } from '../controls/CatalogBrowserModal';
import { ReportExportModal } from '../controls/ReportExportModal';
import { useRoomEditor } from '../hooks/useRoomEditor';

interface InteriorViewerProps {
  sceneData: SceneDataResponse;
  initialFloorId?: string;
  initialRoomId?: string;
  className?: string;
}

const DEFAULT_LAYERS: LayerVisibilityState = {
  walls: true,
  ceiling: true,
  furniture: true,
  cabinetry: true,
  appliances: true,
  sanitary: true,
  lighting: true,
  servicePoints: true,
  roomLabels: true,
  wireframe: false,
};

export const InteriorViewer: React.FC<InteriorViewerProps> = ({
  sceneData,
  initialFloorId,
  initialRoomId,
  className = '',
}) => {
  // ── Viewer State ────────────────────────────────────────────────────────────
  const [viewMode, setViewMode] = useState<'3d' | '2d' | 'split'>('3d');
  const [cameraMode, setCameraMode] = useState<ViewCameraMode>('perspective');
  const [resetCameraCounter, setResetCameraCounter] = useState(0);

  const [layers, setLayers] = useState<LayerVisibilityState>(DEFAULT_LAYERS);
  const [isolateFloor, setIsolateFloor] = useState(false);
  const [isRoomIsolated, setIsRoomIsolated] = useState(false);
  const [explodedView, setExplodedView] = useState(false);

  // Selection state
  const [selection, setSelection] = useState<ViewerSelectionState>({
    selectedFloorId: initialFloorId || (sceneData.floors[0]?.floor_id ?? null),
    selectedRoomId: initialRoomId || null,
    selectedAsset: null,
    selectedFixture: null,
  });

  // Active saved designs state (updated upon save/regeneration)
  const [activeSavedDesigns, setActiveSavedDesigns] = useState<Record<string, PersistedRoomDesignDTO>>(
    sceneData.saved_designs || {}
  );

  // Customization Editor State
  const [editInteractionMode, setEditInteractionMode] = useState<EditInteractionMode>('select');
  const [catalogModalOpen, setCatalogModalOpen] = useState(false);
  const [catalogModalMode, setCatalogModalMode] = useState<'add' | 'replace'>('add');
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  const capture3DCanvas = () => {
    try {
      const canvas = document.querySelector('canvas');
      if (canvas) {
        return canvas.toDataURL('image/png');
      }
    } catch (e) {
      console.warn('Canvas snapshot capture not available:', e);
    }
    return null;
  };

  // WebGL availability check
  const [webGLSupported, setWebGLSupported] = useState(true);

  useEffect(() => {
    try {
      const canvas = document.createElement('canvas');
      const supported = !!(
        window.WebGLRenderingContext &&
        (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
      );
      setWebGLSupported(supported);
      if (!supported) {
        setViewMode('2d');
      }
    } catch {
      setWebGLSupported(false);
      setViewMode('2d');
    }
  }, []);

  // Sync initial selection
  useEffect(() => {
    if (initialFloorId && initialFloorId !== selection.selectedFloorId) {
      setSelection((prev) => ({ ...prev, selectedFloorId: initialFloorId }));
    }
    if (initialRoomId && initialRoomId !== selection.selectedRoomId) {
      setSelection((prev) => ({ ...prev, selectedRoomId: initialRoomId }));
    }
  }, [initialFloorId, initialRoomId]);

  // Derived selected floor and room objects
  const selectedFloor = useMemo(() => {
    if (!selection.selectedFloorId) return sceneData.floors[0] || null;
    return sceneData.floors.find((f) => f.floor_id === selection.selectedFloorId) || null;
  }, [sceneData.floors, selection.selectedFloorId]);

  const selectedRoom = useMemo(() => {
    if (!selection.selectedRoomId || !selectedFloor) return null;
    return selectedFloor.rooms.find((r) => r.room_id === selection.selectedRoomId) || null;
  }, [selectedFloor, selection.selectedRoomId]);

  const savedDesign = useMemo(() => {
    if (!selection.selectedRoomId) return null;
    return activeSavedDesigns[selection.selectedRoomId] || sceneData.saved_designs[selection.selectedRoomId] || null;
  }, [activeSavedDesigns, sceneData.saved_designs, selection.selectedRoomId]);

  // Hook for room editing, locking, validation, and selective regeneration
  const editor = useRoomEditor({
    projectId: sceneData.project_id,
    roomId: selection.selectedRoomId,
    floorId: selection.selectedFloorId,
    initialDesign: savedDesign,
    onDesignUpdated: (updated) => {
      if (selection.selectedRoomId) {
        setActiveSavedDesigns((prev) => ({
          ...prev,
          [selection.selectedRoomId!]: updated,
        }));
      }
    },
  });

  // Keep selected asset in sync with draft updates
  useEffect(() => {
    if (selection.selectedAsset && editor.draftDesign) {
      const allAssets = [
        ...(editor.draftDesign.furniture || []),
        ...(editor.draftDesign.cabinetry || []),
        ...(editor.draftDesign.appliances || []),
        ...(editor.draftDesign.sanitary_fixtures || []),
        ...(editor.draftDesign.decorations || []),
      ];
      const match = allAssets.find((a) => a.instance_id === selection.selectedAsset?.instance_id);
      if (match) {
        setSelection((prev) => ({ ...prev, selectedAsset: match }));
      }
    }
  }, [editor.draftDesign]);

  const stalenessReport = useMemo(() => {
    if (!selection.selectedRoomId || !sceneData.staleness?.rooms) return null;
    return sceneData.staleness.rooms[selection.selectedRoomId] || null;
  }, [sceneData.staleness, selection.selectedRoomId]);

  // Handlers
  const handleSelectFloor = (floorId: string | null) => {
    setSelection((prev) => ({
      ...prev,
      selectedFloorId: floorId,
      selectedRoomId: null,
      selectedAsset: null,
      selectedFixture: null,
    }));
    setIsRoomIsolated(false);
    if (floorId) {
      setIsolateFloor(true);
    } else {
      setIsolateFloor(false);
    }
  };

  const handleSelectRoom = (roomId: string | null) => {
    setSelection((prev) => ({
      ...prev,
      selectedRoomId: roomId,
      selectedAsset: null,
      selectedFixture: null,
    }));
    if (roomId) {
      setIsRoomIsolated(true);
      setCameraMode('room_focus');
    } else {
      setIsRoomIsolated(false);
      setCameraMode('perspective');
    }
  };

  const handleToggleIsolateRoom = () => {
    setIsRoomIsolated((prev) => {
      const next = !prev;
      if (next && selection.selectedRoomId) {
        setCameraMode('room_focus');
      } else if (!next) {
        setCameraMode('perspective');
      }
      return next;
    });
  };

  const handleSelectAsset = (asset: PlacedAssetPersistedDTO) => {
    setSelection((prev) => ({
      ...prev,
      selectedAsset: asset,
      selectedFixture: null,
    }));
  };

  const handleSelectFixture = (fixture: PlacedFixturePointDTO) => {
    setSelection((prev) => ({
      ...prev,
      selectedFixture: fixture,
      selectedAsset: null,
    }));
  };

  const handleToggleLayer = (key: keyof LayerVisibilityState) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleResetCamera = () => {
    setResetCameraCounter((c) => c + 1);
  };

  return (
    <div className={`relative flex flex-col w-full h-[850px] bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 ${className}`}>
      {/* ── Top Floating Toolbar & Phase 7 Customization Toolbar ─────────── */}
      <div className="absolute top-4 left-4 right-4 z-20 pointer-events-auto flex flex-col gap-2">
        <ViewerToolbar
          floors={sceneData.floors}
          selectedFloorId={selection.selectedFloorId}
          onSelectFloor={handleSelectFloor}
          selectedRoomId={selection.selectedRoomId}
          onSelectRoom={handleSelectRoom}
          isRoomIsolated={isRoomIsolated}
          onToggleIsolateRoom={handleToggleIsolateRoom}
          viewMode={viewMode}
          onChangeViewMode={setViewMode}
          cameraMode={cameraMode}
          onChangeCameraMode={setCameraMode}
          isolateFloor={isolateFloor}
          onToggleIsolateFloor={() => setIsolateFloor((v) => !v)}
          explodedView={explodedView}
          onToggleExplodedView={() => setExplodedView((v) => !v)}
          onResetCamera={handleResetCamera}
          onOpenExport={() => setIsExportModalOpen(true)}
        />

        {/* Phase 7 Customization Toolbar */}
        {selection.selectedRoomId && (
          <EditorToolbar
            mode={editInteractionMode}
            onChangeMode={setEditInteractionMode}
            selectedAsset={selection.selectedAsset}
            canUndo={editor.canUndo}
            canRedo={editor.canRedo}
            isDirty={editor.isDirty}
            isSaving={editor.isSaving}
            isValidating={editor.isValidating}
            isRegenerating={editor.isRegenerating}
            validationResult={editor.validationResult}
            errorMessage={editor.errorMessage}
            onUndo={editor.undo}
            onRedo={editor.redo}
            onToggleLock={() => {
              if (selection.selectedAsset) {
                editor.toggleLock(selection.selectedAsset.instance_id);
              }
            }}
            onRemoveAsset={() => {
              if (selection.selectedAsset) {
                editor.removeAsset(selection.selectedAsset.instance_id);
                setSelection((prev) => ({ ...prev, selectedAsset: null }));
              }
            }}
            onOpenCatalog={() => {
              setCatalogModalMode('add');
              setCatalogModalOpen(true);
            }}
            onSave={editor.saveDraft}
            onDiscard={editor.discardDraft}
            onRegenerateUnlocked={() => editor.regenerateUnlocked(42)}
          />
        )}
      </div>

      {/* ── Main Viewports Container ────────────────────────────────────────── */}
      <div className="relative flex-1 w-full h-full flex overflow-hidden">
        {/* 3D WebGL Canvas Viewport */}
        {(viewMode === '3d' || viewMode === 'split') && (
          <div className={`relative h-full ${viewMode === 'split' ? 'w-1/2 border-r border-slate-800' : 'w-full'}`}>
            {!webGLSupported ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-6 text-slate-400">
                <span className="text-3xl mb-2">⚠️</span>
                <div className="text-base font-semibold text-white">WebGL Not Supported</div>
                <div className="text-xs text-slate-400 max-w-sm mt-1">
                  Your browser or hardware acceleration settings do not currently support WebGL. Switch to 2D Plan view for interactive floor plans.
                </div>
              </div>
            ) : (
              <Canvas
                shadows
                camera={{ fov: 45, near: 0.1, far: 200, position: [15, 12, 15] }}
                gl={{
                  antialias: true,
                  preserveDrawingBuffer: true,
                  toneMapping: THREE.ACESFilmicToneMapping,
                  toneMappingExposure: 1.1,
                  outputColorSpace: THREE.SRGBColorSpace,
                }}
              >
                <Suspense fallback={null}>
                  {/* Physically Plausible Environmental Lighting */}
                  <ambientLight intensity={0.4} />
                  <hemisphereLight args={['#ffffff', '#334155', 0.5]} />
                  <directionalLight
                    castShadow
                    position={[15, 25, 10]}
                    intensity={1.2}
                    shadow-mapSize={[2048, 2048]}
                    shadow-camera-near={0.5}
                    shadow-camera-far={60}
                    shadow-camera-left={-20}
                    shadow-camera-right={20}
                    shadow-camera-top={20}
                    shadow-camera-bottom={-20}
                    shadow-bias={-0.0001}
                  />

                  {/* Building Scene Container */}
                  <BuildingScene
                    sceneData={sceneData}
                    selectedFloorId={selection.selectedFloorId}
                    selectedRoomId={selection.selectedRoomId}
                    onSelectRoom={handleSelectRoom}
                    selectedAssetId={selection.selectedAsset?.instance_id || null}
                    onSelectAsset={handleSelectAsset}
                    selectedFixtureId={selection.selectedFixture?.fixture_id || selection.selectedFixture?.point_id || null}
                    onSelectFixture={handleSelectFixture}
                    layers={layers}
                    isolateFloor={isolateFloor}
                    isolateRoom={isRoomIsolated || cameraMode === 'room_focus'}
                    explodedView={explodedView}
                    draftDesign={editor.draftDesign}
                  />

                  {/* Orbit & Camera Modes Controller */}
                  <CameraController
                    mode={cameraMode}
                    floors={sceneData.floors}
                    selectedFloorId={selection.selectedFloorId}
                    selectedRoomId={selection.selectedRoomId}
                    resetTrigger={resetCameraCounter}
                  />

                  {/* First-person Walkthrough Controller */}
                  <WalkthroughController
                    active={cameraMode === 'walkthrough'}
                    floors={sceneData.floors}
                    selectedFloorId={selection.selectedFloorId}
                    selectedRoomId={selection.selectedRoomId}
                    onExit={() => setCameraMode('perspective')}
                  />
                </Suspense>
              </Canvas>
            )}

            {/* Walkthrough HUD Notification */}
            {cameraMode === 'walkthrough' && (
              <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 bg-slate-900/95 backdrop-blur-md px-4 py-2 rounded-xl border border-cyan-500/50 shadow-2xl text-xs text-white">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
                <span>Walkthrough Mode: Use <strong>W A S D</strong> or <strong>Arrows</strong> to move, click & drag to look.</span>
                <button
                  onClick={() => setCameraMode('perspective')}
                  className="bg-slate-800 hover:bg-slate-700 px-2.5 py-1 rounded-md text-[11px] font-semibold text-cyan-300 border border-slate-700 ml-2"
                >
                  Exit (ESC)
                </button>
              </div>
            )}
          </div>
        )}

        {/* 2D Plan Viewport */}
        {(viewMode === '2d' || viewMode === 'split') && selectedFloor && (
          <div className={`relative h-full ${viewMode === 'split' ? 'w-1/2' : 'w-full'}`}>
            <PlanView2D
              floor={selectedFloor}
              savedDesigns={activeSavedDesigns}
              selectedRoomId={selection.selectedRoomId}
              isRoomIsolated={isRoomIsolated}
              onSelectRoom={handleSelectRoom}
              selectedAssetId={selection.selectedAsset?.instance_id || null}
              onSelectAsset={handleSelectAsset}
              selectedFixtureId={selection.selectedFixture?.fixture_id || selection.selectedFixture?.point_id || null}
              onSelectFixture={handleSelectFixture}
              layers={layers}
              editMode={editInteractionMode}
              draftDesign={editor.draftDesign}
              onMoveAsset={(instId, x, y) => editor.moveAsset(instId, x, y)}
              onRotateAsset={(instId, deg) => editor.rotateAsset(instId, deg)}
            />
          </div>
        )}
      </div>

      {/* ── Bottom Left Floating Layer Controls ─────────────────────────────── */}
      <div className="absolute bottom-4 left-4 z-20 pointer-events-auto">
        <LayerControls
          layers={layers}
          onToggleLayer={handleToggleLayer}
          onResetLayers={() => setLayers(DEFAULT_LAYERS)}
        />
      </div>

      {/* ── Floating Right Object Inspector Panel ───────────────────────────── */}
      <div className="absolute top-28 right-4 z-20 pointer-events-auto">
        <ObjectInfoPanel
          selectedRoom={selectedRoom}
          selectedFloor={selectedFloor}
          savedDesign={editor.draftDesign || savedDesign}
          stalenessReport={stalenessReport}
          selectedAsset={selection.selectedAsset}
          selectedFixture={selection.selectedFixture}
          onClose={() =>
            setSelection((prev) => ({
              ...prev,
              selectedAsset: null,
              selectedFixture: null,
            }))
          }
          onMoveAsset={(x, y) => {
            if (selection.selectedAsset) {
              editor.moveAsset(selection.selectedAsset.instance_id, x, y);
            }
          }}
          onRotateAsset={(deg) => {
            if (selection.selectedAsset) {
              editor.rotateAsset(selection.selectedAsset.instance_id, deg);
            }
          }}
          onResizeAsset={(w, d, h) => {
            if (selection.selectedAsset) {
              editor.resizeAsset(selection.selectedAsset.instance_id, w, d, h);
            }
          }}
          onToggleLock={() => {
            if (selection.selectedAsset) {
              editor.toggleLock(selection.selectedAsset.instance_id);
            }
          }}
          onRemoveAsset={() => {
            if (selection.selectedAsset) {
              editor.removeAsset(selection.selectedAsset.instance_id);
              setSelection((prev) => ({ ...prev, selectedAsset: null }));
            }
          }}
          onOpenReplaceModal={() => {
            setCatalogModalMode('replace');
            setCatalogModalOpen(true);
          }}
          onUpdateMaterial={(mat, col) => {
            if (selection.selectedAsset) {
              editor.updateMaterial(selection.selectedAsset.instance_id, mat, col);
            }
          }}
          diagnostics={editor.validationResult?.diagnostics || []}
        />
      </div>

      {/* ── Catalog Asset Browser Modal ──────────────────────────────────────── */}
      <CatalogBrowserModal
        isOpen={catalogModalOpen}
        onClose={() => setCatalogModalOpen(false)}
        mode={catalogModalMode}
        roomType={selectedRoom?.room_type}
        currentAssetCategory={selection.selectedAsset?.category}
        onSelectAsset={(chosen) => {
          if (catalogModalMode === 'replace' && selection.selectedAsset) {
            editor.replaceAsset(selection.selectedAsset.instance_id, chosen);
          } else {
            editor.addAsset(chosen);
          }
        }}
      />

      {/* ── Phase 8: Report & Export Modal ────────────────────────────────────── */}
      <ReportExportModal
        projectId={sceneData.project_id}
        floors={sceneData.floors}
        selectedFloorId={selection.selectedFloorId}
        selectedRoomId={selection.selectedRoomId}
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        hasUnsavedChanges={editor.isDirty}
        onSaveFirst={editor.saveDraft}
        captureCurrent3DView={capture3DCanvas}
      />
    </div>
  );
};

