"use client"
/**
 * EliaOutputWrapper — ELIA-owned presentation wrapper.
 *
 * Encapsulates:
 *   - Derivation of in-memory EliaViewModel from upstream Master JSON and ELIA candidate output.
 *   - Preservation of source revisions and single-time unit normalization.
 *   - Dynamic SSR-safe loading of Three.js exterior viewer and SVG 2D plan renderer.
 *   - Clear distinction between Accepted Design (saved in Master JSON), Candidate Preview (unsaved),
 *     and Infeasible Candidates (unaccepted).
 *   - Standard tabs (2D Plan, 3D Scene, Raw JSON) with distinct Master JSON and Landscape JSON exports.
 *
 * Keeps all ELIA contract handling and props strictly isolated from shared output components.
 */
import React, { useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from '@/components/output/DownloadButtons'
import { FileJson, Layers, CheckCircle2, AlertTriangle, XCircle, Info } from 'lucide-react'
import type { ExteriorLandscape, ExteriorValidation, EliaContextFreshness } from '@/types/elia'
import { extractNormalizedUpstreamGeometry } from '@/lib/eliaGeometry'

// Dynamically import Three.js components to prevent SSR hydration errors
const ExteriorSceneViewer = dynamic(
  () => import('@/components/visualization/ExteriorSceneViewer'),
  { ssr: false, loading: () => <LoadingPlaceholder label="Loading 3D Exterior Scene..." /> }
)

const EliaLandscape2D = dynamic(
  () => import('@/components/visualization/EliaLandscape2D'),
  { ssr: false, loading: () => <LoadingPlaceholder label="Loading 2D Plan View..." /> }
)

function LoadingPlaceholder({ label }: { label: string }) {
  return (
    <div className="w-full min-h-[480px] flex items-center justify-center bg-[#0a140a] rounded-lg">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        <span className="text-sm font-mono">{label}</span>
      </div>
    </div>
  )
}

function formatPreferenceLabel(key: string): string {
  const map: Record<string, string> = {
    preferred_garden_zone: 'Garden Zone Preference',
    preferred_open_space_ratio: 'Open Space Target Ratio',
    low_maintenance_preference: 'Low Maintenance Preference',
    driveway_style: 'Driveway Style Curve/Alignment',
    driveway_surface: 'Driveway Surface Material',
    entrance_priority: 'Main Entrance Orientation',
    property_orientation: 'Property Orientation',
    design_style_geometry: 'Aesthetic Geometry Concept',
    utility_relocation_allowed: 'Utility Relocation',
    additional_requirements: 'Additional Custom Constraints',
    preferred_vegetation_categories: 'Requested Vegetation Categories',
    shade_tree_preference: 'Shade Canopy Trees',
    gate_type: 'Gate Placement/Style',
    preferred_gate_location: 'Requested Gate Coordinate',
    preferred_garage_location: 'Requested Garage Coordinate',
    garden_table_set_required: 'Garden Dining Set',
    garden_seating_required: 'Outdoor Garden Seating',
  };
  return map[key] || key.replace(/_/g, ' ');
}

export interface EliaOutputWrapperProps {
  projectName: string;
  projectId?: string;
  masterJson: any;
  data?: unknown;
  isProcessing?: boolean;
  runError?: string;
  viewStatus?: 'accepted' | 'preview' | 'infeasible';
  sourceRevision?: number | null;
  candidateRevision?: number | null;
  acceptedRevision?: number | null;
  acceptedSnapshot?: any;
  generationMode?: string;
  acceptedData?: unknown;
  candidateData?: unknown;
  candidateSnapshot?: any;
  candidateKind?: 'preview' | 'persisted_run';
  candidateStatus?: 'preview' | 'infeasible';
  contextFreshness?: EliaContextFreshness;
  isFormDirtyAgainstCandidate?: boolean;
  activeView?: 'candidate' | 'accepted';
  onToggleView?: (view: 'candidate' | 'accepted') => void;
  validationSummary?: ExteriorValidation | null;
  requiresReconciliation?: boolean;
  selectedFeatureId?: string | null;
  onSelectFeature?: (id: string) => void;
  gizmoMode?: 'translate' | 'rotate' | 'scale';
  onGizmoModeChange?: (mode: 'translate' | 'rotate' | 'scale') => void;
  onFeatureMoved?: (id: string, pos: [number, number]) => void;
  onFeatureRotated?: (id: string, angleDeg: number) => void;
  onFeatureScaled?: (id: string, factor: number) => void;
  lockedFeatureIds?: string[];
}

export function EliaOutputWrapper({
  projectName,
  projectId,
  masterJson,
  data,
  isProcessing,
  runError,
  viewStatus = 'accepted',
  sourceRevision,
  candidateRevision,
  acceptedRevision,
  acceptedSnapshot,
  generationMode,
  acceptedData,
  candidateData,
  candidateSnapshot,
  candidateKind = 'preview',
  candidateStatus = 'preview',
  contextFreshness = 'current',
  isFormDirtyAgainstCandidate = false,
  activeView = 'candidate',
  onToggleView,
  validationSummary,
  requiresReconciliation = false,
  selectedFeatureId,
  onSelectFeature,
  gizmoMode,
  onGizmoModeChange,
  onFeatureMoved,
  onFeatureRotated,
  onFeatureScaled,
  lockedFeatureIds = [],
}: EliaOutputWrapperProps) {
  const [jsonViewTab, setJsonViewTab] = useState<'landscape' | 'master'>('landscape');
  const [activeTab, setActiveTab] = useState<'2d' | '3d' | 'json'>('2d');

  const landscape = data ? (data as ExteriorLandscape) : null;

  // Use matching source snapshot for candidate preview or for accepted design when refresh failed
  const displayMasterJson = activeView === 'candidate'
    ? (candidateSnapshot ?? null)
    : (activeView === 'accepted' && acceptedSnapshot && contextFreshness !== 'current' ? acceptedSnapshot : masterJson);

  const displayRevision = activeView === 'candidate'
    ? (candidateRevision !== undefined ? candidateRevision : null)
    : (acceptedRevision !== undefined ? acceptedRevision : sourceRevision);

  // Authoritative ELIA view model derived from Master JSON and landscape
  const viewModel = useMemo(() => {
    return extractNormalizedUpstreamGeometry(
      displayMasterJson,
      landscape,
      projectId,
      displayRevision,
      activeView === 'accepted'
    );
  }, [displayMasterJson, landscape, projectId, displayRevision, activeView]);

  const hasAccepted = Boolean(acceptedData);
  const hasCandidate = Boolean(candidateData || (activeView === 'candidate' && data));
  const hasBothVersions = hasAccepted && hasCandidate;

  // Derive mode badge from displayed result's own metadata if available
  const displayedGenerationMode = landscape?.generation_mode || generationMode;

  // Determine export status key for filename
  const exportStatusKey = activeView === 'accepted'
    ? (hasAccepted ? 'accepted' : 'empty')
    : (candidateStatus === 'infeasible' ? 'infeasible' : candidateKind);

  // Download handler for authoritative Master JSON (blocked if context is not confirmed current or reconciliation pending)
  const handleDownloadMasterJson = () => {
    if (!masterJson || contextFreshness !== 'current' || requiresReconciliation) return;
    const blob = new Blob([JSON.stringify(masterJson, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${projectName || 'project'}_authoritative_master.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* Top Header Actions & Status Badges */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-xl font-bold">Landscape Visualization</h3>

            {/* View Badges — derived truthfully from active selection and actual data presence */}
            {activeView === 'accepted' && (
              hasAccepted ? (
                <Badge variant="outline" className="bg-emerald-950/60 text-emerald-400 border-emerald-500/40 text-[11px] gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Accepted Design (Saved)
                </Badge>
              ) : (
                <Badge variant="outline" className="text-muted-foreground border-border/60 text-[11px]">
                  No Saved Design Yet
                </Badge>
              )
            )}

            {activeView === 'candidate' && (
              candidateStatus === 'infeasible' ? (
                <Badge variant="outline" className="bg-rose-950/60 text-rose-300 border-rose-500/40 text-[11px] gap-1">
                  <XCircle className="w-3 h-3" /> Infeasible Candidate (Unaccepted)
                </Badge>
              ) : candidateKind === 'persisted_run' ? (
                <Badge variant="outline" className="bg-primary/20 text-primary border-primary/40 text-[11px] gap-1">
                  <Layers className="w-3 h-3" /> Persisted Run Candidate
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-amber-950/60 text-amber-300 border-amber-500/40 text-[11px] gap-1">
                  <AlertTriangle className="w-3 h-3" /> Candidate Preview (Unsaved)
                </Badge>
              )
            )}

            {activeView === 'candidate' && isFormDirtyAgainstCandidate && (
              <Badge variant="outline" className="text-amber-300/80 border-amber-500/30 text-[10px]">
                Inputs edited since generation
              </Badge>
            )}

            {contextFreshness === 'stale' && (
              <Badge variant="outline" className="bg-amber-950/40 text-amber-300 border-amber-500/40 text-[11px]">
                Stale Context
              </Badge>
            )}
            {contextFreshness === 'unavailable' && (
              <Badge variant="outline" className="bg-rose-950/40 text-rose-300 border-rose-500/40 text-[11px]">
                Context Unavailable
              </Badge>
            )}

            {activeView === 'candidate' && !candidateSnapshot && (
              <Badge variant="outline" className="bg-amber-950/40 text-amber-300 border-amber-500/40 text-[11px]">
                Snapshot Unavailable
              </Badge>
            )}

            {displayRevision !== undefined && displayRevision !== null ? (
              <span className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                rev {displayRevision}
              </span>
            ) : activeView === 'candidate' ? (
              <span className="text-[11px] font-mono text-amber-400/90 bg-muted px-2 py-0.5 rounded">
                rev unavailable
              </span>
            ) : null}
            {landscape && displayedGenerationMode && (
              <span className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                mode: {displayedGenerationMode}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {projectName ? `${projectName} · ` : ''}Eco-Spatial Landscape Intelligence
          </p>
        </div>

        {/* Export Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <DownloadImageButton
            filename={`${projectName || 'project'}_elia_${activeView}_plan.png`}
            targetId="elia-output-preview"
            disabled={!data || activeTab !== '2d'}
          />
          <DownloadPdfButton
            filename={`${projectName || 'project'}_elia_${activeView}_plan.pdf`}
            targetId="elia-output-preview"
            disabled={!data || activeTab !== '2d'}
          />
          <DownloadJsonButton
            filename={`${projectName || 'project'}_elia_${activeView}_${exportStatusKey}.json`}
            data={data}
            disabled={!data}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownloadMasterJson}
            disabled={!masterJson || contextFreshness !== 'current' || requiresReconciliation || activeView === 'candidate'}
            title={
              activeView === 'candidate'
                ? 'Master JSON export is only available from the Saved Accepted Design view'
                : requiresReconciliation
                ? 'Master JSON export blocked: project state must be reconciled first'
                : contextFreshness !== 'current'
                ? 'Master JSON export requires confirmed current context'
                : 'Download full project Master JSON with exterior landscape layer'
            }
          >
            <FileJson className="w-4 h-4 mr-2 text-primary" /> Master JSON
          </Button>
        </div>
      </div>

      {/* Version Switching Controls when candidate and accepted both exist */}
      {hasBothVersions && onToggleView && (
        <div className="flex items-center justify-between p-2.5 rounded-lg border border-border bg-card/60 text-xs">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary" />
            <span className="text-muted-foreground">Design versions available:</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant={activeView === 'candidate' ? 'default' : 'outline'}
              className="h-7 text-xs px-2.5"
              onClick={() => onToggleView('candidate')}
            >
              Current Candidate {candidateStatus === 'infeasible' ? '(Infeasible)' : candidateKind === 'preview' ? '(Unsaved)' : '(Persisted)'}
            </Button>
            <Button
              size="sm"
              variant={activeView === 'accepted' ? 'default' : 'outline'}
              className="h-7 text-xs px-2.5"
              onClick={() => onToggleView('accepted')}
            >
              Saved Accepted Design
            </Button>
          </div>
        </div>
      )}

      {/* Infeasible notice */}
      {viewStatus === 'infeasible' && (
        <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-950/20 text-rose-200 text-xs space-y-1">
          <div className="font-semibold flex items-center gap-1.5 text-rose-300">
            <XCircle className="w-4 h-4 shrink-0" /> Candidate Layout Infeasible
          </div>
          <p className="text-rose-200/90 leading-relaxed">
            The requested exterior layout could not satisfy all spatial or boundary constraints. 
            The existing accepted exterior design in the project Master JSON has been kept intact and unmodified.
          </p>
          {Array.isArray(validationSummary?.violations) && validationSummary.violations.length > 0 && (
            <ul className="list-disc pl-5 pt-1 space-y-0.5 text-rose-300/90 font-mono text-[11px]">
              {validationSummary.violations.map((violation, idx) => (
                <li key={idx}>{String(violation)}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Preference Fulfillment Transparency Banner */}
      {landscape && landscape.preference_fulfillment && (
        (() => {
          const pf = landscape.preference_fulfillment;
          const unsupported = pf.unsupported_preferences || [];
          const unfulfilled = pf.unfulfilled_preferences || [];
          const labelOnly = pf.label_only_preferences || [];
          const hasAny = unsupported.length > 0 || unfulfilled.length > 0 || labelOnly.length > 0;
          if (!hasAny) return null;

          return (
            <div className="p-3 rounded-lg border border-border/70 bg-card/60 text-xs space-y-2">
              <div className="font-semibold text-muted-foreground flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-primary" /> Preference & Capability Fulfillment Summary
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                {unsupported.length > 0 && (
                  <div className="p-2 rounded bg-muted/40 border border-border/40">
                    <span className="font-medium text-amber-300 block mb-0.5">Recorded (Unsupported by baseline geometry):</span>
                    <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                      {unsupported.map((item, i) => (
                        <li key={i}>{formatPreferenceLabel(item)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {unfulfilled.length > 0 && (
                  <div className="p-2 rounded bg-muted/40 border border-border/40">
                    <span className="font-medium text-rose-300 block mb-0.5">Unfulfilled under site boundary constraints:</span>
                    <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                      {unfulfilled.map((item, i) => (
                        <li key={i}>{formatPreferenceLabel(item)}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              {labelOnly.length > 0 && (
                <p className="text-[10px] text-muted-foreground italic">
                  Note: Concept style ({labelOnly.join(', ')}) is preserved in project metadata; baseline planner applies regulatory geometry rules.
                </p>
              )}
            </div>
          );
        })()
      )}

      {/* Tabs */}
      <Tabs defaultValue="2d" value={activeTab} onValueChange={(val: string) => setActiveTab(val as any)} className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="2d">2D Plan View</TabsTrigger>
          <TabsTrigger value="3d">3D Exterior View</TabsTrigger>
          <TabsTrigger value="json">JSON Inspection</TabsTrigger>
        </TabsList>

        {/* 2D Plan View Tab */}
        <TabsContent
          value="2d"
          className="bg-card/50 border border-border p-4 rounded-xl min-h-[500px]"
          id="elia-output-preview"
        >
          {isProcessing ? (
            <LoadingPlaceholder label="Generating exterior spatial plan..." />
          ) : (
            <EliaLandscape2D
              viewModel={viewModel}
              landscape={landscape}
              selectedFeatureId={selectedFeatureId}
              onSelectFeature={onSelectFeature}
              lockedFeatureIds={lockedFeatureIds}
            />
          )}
        </TabsContent>

        {/* 3D Scene View Tab */}
        <TabsContent
          value="3d"
          className="bg-card/50 border border-border rounded-xl overflow-hidden min-h-[500px]"
        >
          {isProcessing ? (
            <LoadingPlaceholder label="Calculating 3D solar and spatial constraints..." />
          ) : (
            <ExteriorSceneViewer
              viewModel={viewModel}
              landscape={landscape}
              selectedFeatureId={selectedFeatureId}
              gizmoMode={gizmoMode}
              onGizmoModeChange={onGizmoModeChange}
              onFeatureMoved={onFeatureMoved}
              onFeatureRotated={onFeatureRotated}
              onFeatureScaled={onFeatureScaled}
              lockedFeatureIds={lockedFeatureIds}
            />
          )}
        </TabsContent>

        {/* JSON Inspector Tab */}
        <TabsContent
          value="json"
          className="bg-card/50 border border-border p-4 rounded-xl min-h-[500px] overflow-auto max-h-[640px]"
        >
          <div className="flex items-center justify-between mb-3 border-b border-border/60 pb-2">
            <div className="flex gap-2 text-xs">
              <Button
                variant={jsonViewTab === 'landscape' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setJsonViewTab('landscape')}
              >
                Exterior Landscape JSON ({viewStatus})
              </Button>
              <Button
                variant={jsonViewTab === 'master' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setJsonViewTab('master')}
              >
                Project Master JSON
              </Button>
            </div>
            <span className="text-[11px] font-mono text-muted-foreground">
              {jsonViewTab === 'landscape'
                ? data ? `${Object.keys(landscape?.access || {}).length} access elements` : 'No data'
                : displayMasterJson ? `revision: ${displayRevision ?? displayMasterJson.revision ?? 1}` : 'No Master JSON'}
            </span>
          </div>

          <pre className="text-xs text-primary-foreground/90 font-mono whitespace-pre-wrap break-all leading-relaxed">
            {jsonViewTab === 'landscape'
              ? data
                ? JSON.stringify(data, null, 2)
                : '// No ELIA landscape output generated yet.\n// Click "Preview" or "Generate & Save" to run the exterior planner.'
              : displayMasterJson
              ? JSON.stringify(displayMasterJson, null, 2)
              : '// No source Master JSON snapshot available for this candidate.'}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default EliaOutputWrapper
