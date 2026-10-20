"use client";

import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from '@/components/output/DownloadButtons';
import { Button } from '@/components/ui/button';
import { Layers, AlertTriangle, CheckCircle2, FileCode, RotateCcw } from 'lucide-react';
import { PlanPreview2D } from './PlanPreview2D';

import { PlanPreview3D } from './PlanPreview3D';
import { CandidateComparison } from './CandidateComparison';
import { GabGenMasterJson } from '../../types';
import { gabGenExtendedApi } from '../../api';

interface BlueprintViewerProps {
  data: GabGenMasterJson | null;
  projectName: string;
  projectId?: string;
  onUpdate?: (updated: GabGenMasterJson) => void;
}

export const BlueprintViewer: React.FC<BlueprintViewerProps> = ({
  data,
  projectName,
  projectId,
  onUpdate
}) => {
  const [selectedFloor, setSelectedFloor] = useState<number | 'all'>('all');
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  const [exploded3D, setExploded3D] = useState(false);
  const [activeTab, setActiveTab] = useState<'2d' | '3d' | 'json'>('2d');
  const [editMessage, setEditMessage] = useState<string | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [isSelectingCand, setIsSelectingCand] = useState(false);


  const floors = data?.floor_plan?.floors || [];
  const validation = data?.gab_gen_validation;

  // Selected room details
  const selectedRoom = selectedRoomId
    ? floors.flatMap(f => f.rooms).find(r => r.room_id === selectedRoomId)
    : null;

  const handleNudgeRoom = async (dx: number, dy: number) => {
    if (!selectedRoom || !projectId || !data) return;
    setIsSavingEdit(true);
    setEditMessage(null);

    const newPolygon = selectedRoom.polygon.map(p => ({
      x: Math.round((p.x + dx) * 100) / 100,
      y: Math.round((p.y + dy) * 100) / 100
    }));

    try {
      const res = await gabGenExtendedApi.editRoom(projectId, {
        room_id: selectedRoom.room_id,
        target_floor_id: selectedRoom.floor_id,
        polygon: newPolygon
      });

      if (!res.valid) {
        setEditMessage(`Constraint violation: ${res.violations?.join('; ') || 'Cannot move room outside bounds.'}`);
      } else {
        setEditMessage("Room moved successfully!");
        if (onUpdate && res.floor_plan) {
          onUpdate({
            ...data,
            floor_plan: res.floor_plan
          });
        }
      }
    } catch (err: any) {
      setEditMessage(err.response?.data?.detail || "Failed to edit room.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleResizeRoom = async (scaleFactor: number) => {
    if (!selectedRoom || !projectId || !data) return;
    setIsSavingEdit(true);
    setEditMessage(null);

    const cx = selectedRoom.center.x;
    const cy = selectedRoom.center.y;
    const newPolygon = selectedRoom.polygon.map(p => ({
      x: Math.round((cx + (p.x - cx) * scaleFactor) * 100) / 100,
      y: Math.round((cy + (p.y - cy) * scaleFactor) * 100) / 100
    }));

    try {
      const res = await gabGenExtendedApi.editRoom(projectId, {
        room_id: selectedRoom.room_id,
        target_floor_id: selectedRoom.floor_id,
        polygon: newPolygon
      });

      if (!res.valid) {
        setEditMessage(`Resize violation: ${res.violations?.join('; ') || 'Cannot resize room.'}`);
      } else {
        setEditMessage(`Room resized to ${(selectedRoom.area * scaleFactor * scaleFactor).toFixed(1)} m²!`);
        if (onUpdate && res.floor_plan) {
          onUpdate({ ...data, floor_plan: res.floor_plan });
        }
      }
    } catch (err: any) {
      setEditMessage(err.response?.data?.detail || "Failed to resize room.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleRemoveRoom = async () => {
    if (!selectedRoom || !projectId || !data) return;
    if (selectedRoom.is_structural_stair) {
      setEditMessage("Cannot delete structural staircase core.");
      return;
    }
    setIsSavingEdit(true);
    setEditMessage(null);

    try {
      const res = await gabGenExtendedApi.removeRoom(projectId, selectedRoom.room_id);
      if (!res.valid) {
        setEditMessage(`Removal error: ${res.violations?.join('; ') || 'Failed to remove room.'}`);
      } else {
        setEditMessage(`Room '${selectedRoom.name}' removed successfully.`);
        setSelectedRoomId(null);
        if (onUpdate && res.floor_plan) {
          onUpdate({ ...data, floor_plan: res.floor_plan });
        }
      }
    } catch (err: any) {
      setEditMessage(err.response?.data?.detail || "Failed to remove room.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleReassignFloor = async (targetFloorId: string) => {
    if (!selectedRoom || !projectId || !data || selectedRoom.floor_id === targetFloorId) return;
    setIsSavingEdit(true);
    setEditMessage(null);

    try {
      const res = await gabGenExtendedApi.editRoom(projectId, {
        room_id: selectedRoom.room_id,
        target_floor_id: targetFloorId,
        polygon: selectedRoom.polygon
      });

      if (!res.valid) {
        setEditMessage(`Floor transfer violation: ${res.violations?.join('; ') || 'Could not move room to floor.'}`);
      } else {
        setEditMessage(`Room transferred to floor ${targetFloorId}!`);
        if (onUpdate && res.floor_plan) {
          onUpdate({ ...data, floor_plan: res.floor_plan });
        }
      }
    } catch (err: any) {
      setEditMessage(err.response?.data?.detail || "Failed to transfer room floor.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleSelectCandidate = async (candidateId: string) => {
    if (!projectId || !data) return;
    setIsSelectingCand(true);
    setEditMessage(null);
    try {
      const res = await gabGenExtendedApi.selectCandidate(projectId, candidateId);
      if (res.master_json && onUpdate) {
        onUpdate(res.master_json);
        setEditMessage(`Candidate '${candidateId}' activated successfully.`);
      }
    } catch (err: any) {
      setEditMessage(err.response?.data?.detail || "Failed to select candidate.");
    } finally {
      setIsSelectingCand(false);
    }
  };

  const handleUndo = async () => {
    if (!projectId || !data) return;
    setIsSavingEdit(true);
    setEditMessage(null);
    try {
      const res = await gabGenExtendedApi.undoEdit(projectId);
      if (!res.valid) {
        setEditMessage(res.message || "No edits to undo.");
      } else {
        setEditMessage(res.message);
        if (onUpdate && res.floor_plan) {
          onUpdate({
            ...data,
            floor_plan: res.floor_plan,
            roof_geometry: res.roof_geometry || data.roof_geometry
          });
        }
      }
    } catch (err: any) {
      setEditMessage(err.response?.data?.detail || "Failed to undo edit.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleChangeRoofType = async (newType: string) => {
    if (!projectId || !data) return;
    setIsSavingEdit(true);
    setEditMessage(null);
    try {
      const res = await gabGenExtendedApi.changeRoof(projectId, {
        roof_type: newType
      });
      if (!res.valid) {
        setEditMessage(`Roof error: ${res.violations?.join('; ') || 'Cannot change roof'}`);
      } else {
        setEditMessage(res.message);
        if (onUpdate && res.roof_geometry) {
          onUpdate({
            ...data,
            roof_geometry: res.roof_geometry
          });
        }
      }
    } catch (err: any) {
      setEditMessage(err.response?.data?.detail || "Failed to change roof.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const candidatePool = data?.candidate_generation?.candidates || [];
  const selectedCandidateId = data?.candidate_generation?.selected_candidate_id || data?.building_footprint?.candidate_id || null;
  const currentRoofType = data?.roof_geometry?.roof_type || 'flat_slab';


  return (
    <div className="space-y-4">
      {/* Top Header & Export Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xl font-bold text-foreground">GAB-Gen Blueprint Output</h3>
          <p className="text-xs text-muted-foreground">
            Stage 1 Vector Blueprint & Centralized Master JSON Architecture
          </p>
        </div>

        <div className="flex items-center gap-2">
          <DownloadImageButton
            filename={`${projectName || 'gab'}-blueprint-2d.png`}
            targetId="gab-2d-canvas"
            disabled={!data}
          />
          <DownloadPdfButton
            filename={`${projectName || 'gab'}-specification.pdf`}
            targetId="gab-2d-canvas"
            disabled={!data}
          />
          <DownloadJsonButton
            filename={`${projectName || 'gab'}-master-json.json`}
            data={data}
          />
        </div>
      </div>

      {/* Phase 5 Candidate Alternatives Comparison */}
      {candidatePool.length > 0 && (
        <CandidateComparison
          candidates={candidatePool}
          selectedCandidateId={selectedCandidateId}
          onSelectCandidate={handleSelectCandidate}
          isLoading={isSelectingCand}
        />
      )}

      {/* Status & Validation Banner */}
      {validation && (
        <div className="space-y-2">
          <div
            className={`p-3 rounded-xl border flex items-center justify-between text-xs ${
              validation.status === 'completed'
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : validation.status === 'needs_verification'
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-destructive/10 border-destructive/30 text-destructive'
            }`}
          >
            <div className="flex items-center gap-2">
              {validation.status === 'completed' ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                <AlertTriangle className="w-4 h-4" />
              )}
              <span>
                Status:{' '}
                <strong className="uppercase">{validation.status.replace(/_/g, ' ')}</strong>
                {validation.warnings?.length > 0 && ` — ${validation.warnings[0]}`}
                {validation.violations?.length > 0 && ` — ${validation.violations[0]}`}
              </span>
            </div>

            <div className="flex items-center gap-4 text-[11px] opacity-90">
              <span>
                Reconstructed: <strong>{data?.land_info?.reconstructed_area?.toFixed(1)} m²</strong>
              </span>
              <span>
                Buildable: <strong>{data?.buildable_footprint?.area?.toFixed(1)} m²</strong>
              </span>
            </div>
          </div>

          {/* Phase 6: Independent Architectural Feasibility Diagnostics */}
          {validation.validation_report && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
              <div className={`p-2 rounded-lg border ${validation.validation_report.geometric_validity ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-400' : 'bg-destructive/10 border-destructive/30 text-destructive'}`}>
                <span className="font-semibold block">Geometry</span>
                <span>{validation.validation_report.geometric_validity ? 'Valid & Contained' : 'Conflict / Overlap'}</span>
              </div>
              <div className={`p-2 rounded-lg border ${validation.validation_report.circulation_validity ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-400' : 'bg-destructive/10 border-destructive/30 text-destructive'}`}>
                <span className="font-semibold block">Circulation</span>
                <span>{validation.validation_report.circulation_validity ? 'Fully Connected' : 'Isolated Space'}</span>
              </div>
              <div className={`p-2 rounded-lg border ${validation.validation_report.staircase_validity ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-400' : 'bg-destructive/10 border-destructive/30 text-destructive'}`}>
                <span className="font-semibold block">Vertical Core</span>
                <span>{validation.validation_report.staircase_validity ? 'Aligned & Continuous' : 'Misaligned Stair'}</span>
              </div>
              <div className={`p-2 rounded-lg border ${validation.validation_report.regulatory_validity ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-400' : 'bg-amber-500/10 border-amber-500/20 text-amber-400'}`}>
                <span className="font-semibold block">Regulation</span>
                <span>{validation.validation_report.overall_status === 'VALID_WITH_REGULATORY_UNCERTAINTY' ? 'Provisional' : 'Verified'}</span>
              </div>
            </div>
          )}
        </div>
      )}



      {/* Floor Selector Bar (for Multi-Storey) */}
      {floors.length > 1 && (
        <div className="flex items-center gap-2 bg-card p-1.5 rounded-lg border border-border w-fit text-xs">
          <span className="text-[11px] text-muted-foreground px-2 font-medium flex items-center gap-1">
            <Layers className="w-3.5 h-3.5" /> Floor Level:
          </span>
          <Button
            size="sm"
            variant={selectedFloor === 'all' ? 'default' : 'ghost'}
            className="h-7 text-xs"
            onClick={() => setSelectedFloor('all')}
          >
            All Floors
          </Button>
          {floors.map((fl) => (
            <Button
              key={fl.floor_id}
              size="sm"
              variant={selectedFloor === fl.floor_index ? 'default' : 'ghost'}
              className="h-7 text-xs"
              onClick={() => setSelectedFloor(fl.floor_index)}
            >
              {fl.name}
            </Button>
          ))}
        </div>
      )}

      {/* Main Preview Tabs: 2D, 3D, and Master JSON Inspector */}
      <Tabs value={activeTab} onValueChange={(v: any) => setActiveTab(v)} className="w-full">
        <div className="flex items-center justify-between mb-3">
          <TabsList className="grid w-64 grid-cols-3">
            <TabsTrigger value="2d" className="text-xs">
              2D Vector
            </TabsTrigger>
            <TabsTrigger value="3d" className="text-xs">
              3D View
            </TabsTrigger>
            <TabsTrigger value="json" className="text-xs">
              Master JSON
            </TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            {/* Phase 7: Interactive Roof Type Switcher */}
            <div className="flex items-center gap-1 bg-card p-1 rounded-lg border border-border text-[11px]">
              <span className="text-muted-foreground px-1 font-medium">Roof:</span>
              {(['flat_slab', 'accessible_rooftop', 'gable', 'hip', 'mono_pitch'] as const).map((rt) => (
                <Button
                  key={rt}
                  size="sm"
                  variant={currentRoofType === rt ? 'default' : 'ghost'}
                  className="h-6 px-1.5 text-[10px]"
                  onClick={() => handleChangeRoofType(rt)}
                  disabled={isSavingEdit}
                >
                  {rt === 'flat_slab' ? 'Flat' : rt === 'accessible_rooftop' ? 'Terrace' : rt === 'gable' ? 'Gable' : rt === 'hip' ? 'Hip' : 'Mono'}
                </Button>
              ))}
            </div>

            {/* Phase 7: Undo Action Button */}
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs flex items-center gap-1"
              onClick={handleUndo}
              disabled={isSavingEdit}
              title="Undo last edit transaction"
            >
              <RotateCcw className="w-3 h-3" /> Undo
            </Button>

            {activeTab === '3d' && floors.length > 1 && (
              <Button
                size="sm"
                variant={exploded3D ? 'secondary' : 'outline'}
                className="h-7 text-xs"
                onClick={() => setExploded3D(!exploded3D)}
              >
                {exploded3D ? 'Compact View' : 'Exploded Levels'}
              </Button>
            )}
          </div>
        </div>


        {/* Room Editor Bar if a room is selected */}
        {selectedRoom && (
          <div className="mb-3 p-2.5 rounded-lg bg-pink-500/10 border border-pink-500/30 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-pink-400">Selected Room:</span>
              <strong className="text-foreground">{selectedRoom.name}</strong>
              <span className="text-muted-foreground font-mono">({selectedRoom.area.toFixed(1)} m²)</span>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground mr-1">Move:</span>
              <Button size="sm" variant="outline" className="h-6 w-6 p-0 text-xs" onClick={() => handleNudgeRoom(-0.5, 0)} disabled={isSavingEdit} title="Nudge West">←</Button>
              <Button size="sm" variant="outline" className="h-6 w-6 p-0 text-xs" onClick={() => handleNudgeRoom(0.5, 0)} disabled={isSavingEdit} title="Nudge East">→</Button>
              <Button size="sm" variant="outline" className="h-6 w-6 p-0 text-xs" onClick={() => handleNudgeRoom(0, 0.5)} disabled={isSavingEdit} title="Nudge North">↑</Button>
              <Button size="sm" variant="outline" className="h-6 w-6 p-0 text-xs" onClick={() => handleNudgeRoom(0, -0.5)} disabled={isSavingEdit} title="Nudge South">↓</Button>

              <span className="text-[11px] text-muted-foreground mx-1">| Scale:</span>
              <Button size="sm" variant="outline" className="h-6 px-1.5 text-[11px]" onClick={() => handleResizeRoom(1.05)} disabled={isSavingEdit} title="Enlarge +5%">+5%</Button>
              <Button size="sm" variant="outline" className="h-6 px-1.5 text-[11px]" onClick={() => handleResizeRoom(0.95)} disabled={isSavingEdit} title="Shrink -5%">-5%</Button>

              {floors.length > 1 && (
                <>
                  <span className="text-[11px] text-muted-foreground mx-1">| Floor:</span>
                  {floors.map((fl) => (
                    <Button
                      key={fl.floor_id}
                      size="sm"
                      variant={selectedRoom.floor_id === fl.floor_id ? 'secondary' : 'outline'}
                      className="h-6 px-1.5 text-[10px]"
                      onClick={() => handleReassignFloor(fl.floor_id)}
                      disabled={isSavingEdit || selectedRoom.floor_id === fl.floor_id}
                    >
                      {fl.floor_id}
                    </Button>
                  ))}
                </>
              )}

              {!selectedRoom.is_structural_stair && (
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-6 px-2 text-[10px] ml-1"
                  onClick={handleRemoveRoom}
                  disabled={isSavingEdit}
                >
                  Delete Room
                </Button>
              )}

              <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px] text-muted-foreground" onClick={() => setSelectedRoomId(null)}>Deselect</Button>
            </div>
          </div>
        )}

        {editMessage && (
          <div className="mb-3 p-2 rounded text-xs bg-muted/60 border border-border/80 text-foreground">
            {editMessage}
          </div>
        )}

        {/* Keep 2D canvas mounted or visible so export does not capture blank */}
        <div id="gab-2d-canvas" className={activeTab === '2d' ? 'block' : 'hidden'}>
          <PlanPreview2D
            data={data}
            selectedFloorIndex={selectedFloor}
            selectedRoomId={selectedRoomId}
            onSelectRoom={(id) => setSelectedRoomId(id)}
          />
        </div>


        {activeTab === '3d' && (
          <PlanPreview3D
            data={data}
            selectedFloorIndex={selectedFloor}
            explodedMode={exploded3D}
          />
        )}

        {activeTab === 'json' && (
          <div className="bg-card/70 border border-border p-4 rounded-xl min-h-[480px] max-h-[520px] overflow-auto">
            <pre className="text-xs text-primary-foreground/90 font-mono">
              {data ? JSON.stringify(data, null, 2) : 'No component output is available yet.'}
            </pre>
          </div>
        )}
      </Tabs>
    </div>
  );
};
