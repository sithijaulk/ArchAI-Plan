"use client"
import React, { useState, useEffect, useMemo, useRef, useSyncExternalStore, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { EliaOutputWrapper } from '@/components/visualization/EliaOutputWrapper'
import { useProjectStore } from '@/store/projectStore'
import { eliaApi } from '@/lib/api/elia'
import { extractNormalizedUpstreamGeometry } from '@/lib/eliaGeometry'
import { computeRequirementsFingerprint } from '@/lib/eliaSerialization'
import { EliaWorkflowController } from '@/lib/eliaWorkflowController'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { FactorAssessmentRow, FactorsAssessment } from '@/types/elia'
import {
  LoaderCircle,
  MapPin,
  Search,
  Sun,
  RefreshCw,
  Eye,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Compass,
  Car,
  Trees,
  Lightbulb,
  Sparkles,
  Info,
  Layers,
  History,
  Droplets,
  Sliders,
  Lock,
  Unlock,
  Trash2,
  Undo2,
  RotateCcw,
  Check,
  ShieldCheck,
  Tag,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
} from 'lucide-react'

const CATALOG_SPECIES_OPTIONS = [
  { id: 'areca_catechu', name: 'Areca Palm (Puwak)', scientific: 'Areca catechu', category: 'small_tree' },
  { id: 'plumeria_obtusa', name: 'Frangipani (Araliya)', scientific: 'Plumeria obtusa', category: 'small_tree' },
  { id: 'bougainvillea_spectabilis', name: 'Bougainvillea', scientific: 'Bougainvillea spectabilis', category: 'climber' },
  { id: 'heliconia_psittacorum', name: 'Parrot Flower', scientific: 'Heliconia psittacorum', category: 'shrub' },
  { id: 'codiaeum_variegatum', name: 'Croton (Kos Gaha)', scientific: 'Codiaeum variegatum', category: 'shrub' },
  { id: 'mesua_ferrea', name: 'Ceylon Ironwood (Naa)', scientific: 'Mesua ferrea', category: 'shade_tree' },
  { id: 'shade_tree', name: 'Generic Shade Tree', scientific: 'Unassessed', category: 'shade_tree' },
  { id: 'small_tree', name: 'Generic Small Tree', scientific: 'Unassessed', category: 'small_tree' },
  { id: 'shrub', name: 'Generic Shrub', scientific: 'Unassessed', category: 'shrub' },
  { id: 'ground_cover', name: 'Generic Ground Cover', scientific: 'Unassessed', category: 'ground_cover' },
  { id: 'climber', name: 'Generic Climber', scientific: 'Unassessed', category: 'climber' },
]

function getPosCoords(pos: unknown): [number, number] | null {
  if (Array.isArray(pos) && pos.length >= 2 && typeof pos[0] === 'number' && typeof pos[1] === 'number') {
    return [pos[0], pos[1]]
  }
  if (pos && typeof pos === 'object' && 'x' in pos && 'y' in pos) {
    const o = pos as { x: number; y: number }
    if (typeof o.x === 'number' && typeof o.y === 'number') {
      return [o.x, o.y]
    }
  }
  return null
}

export default function EliaEnginePage() {
  const router = useRouter()
  const { projectId, projectName, masterJson, setComponentStatus, setOutput } = useProjectStore()

  // Production state controller instance (strictly null-safe without fabricated demo IDs)
  const controllerRef = useRef<EliaWorkflowController | null>(null)
  if (!controllerRef.current) {
    controllerRef.current = new EliaWorkflowController(projectId || null)
  }
  const controller = controllerRef.current

  // Synchronize with production workflow controller with stable server snapshot
  const state = useSyncExternalStore(
    useCallback((notify) => controller.subscribe(notify), [controller]),
    useCallback(() => controller.getState(), [controller]),
    useCallback(() => EliaWorkflowController.getServerSnapshot(), [])
  )

  // Local UI state
  const [cityQuery, setCityQuery] = useState('')
  const [catalogEntries, setCatalogEntries] = useState(CATALOG_SPECIES_OPTIONS)
  const [saveCandidateSuccess, setSaveCandidateSuccess] = useState<string | null>(null)

  // Load botanical catalogue from backend
  useEffect(() => {
    eliaApi.getVegetationCatalog().then((cat) => {
      if (cat && Array.isArray(cat.entries) && cat.entries.length > 0) {
        setCatalogEntries(
          cat.entries.map((e: any) => ({
            id: e.vegetation_id,
            name: e.display_name || e.vegetation_id,
            scientific: e.scientific_name || 'Unassessed',
            category: e.category,
          }))
        )
      }
    }).catch(() => {
      // Fallback stays active
    })
  }, [])

  // Coherent project lifecycle: activation on mount/project change, deactivation on cleanup
  useEffect(() => {
    controller.activate(projectId || null)

    if (projectId) {
      controller.loadAuthoritativeContext(eliaApi)
      controller.loadLatestRun(eliaApi)
    }

    return () => {
      controller.deactivate()
    }
  }, [projectId, controller])

  // Warn on browser unload if form has unsaved edits
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (state.requirementsDirty) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [state.requirementsDirty])

  // Upstream Site View Model (strictly null if no authoritative project data exists)
  const displayMasterJson = state.activeView === 'candidate'
    ? (state.candidate?.sourceSnapshot ?? null)
    : (state.authoritativeMaster || masterJson || null)

  const displayRevision = state.activeView === 'candidate'
    ? (state.candidate?.sourceRevision !== undefined ? state.candidate.sourceRevision : null)
    : state.sourceRevision

  const siteViewModel = useMemo(() => {
    return extractNormalizedUpstreamGeometry(
      displayMasterJson,
      null,
      projectId || undefined,
      displayRevision,
      state.activeView === 'accepted'
    )
  }, [displayMasterJson, projectId, displayRevision, state.activeView])

  // Check if form was edited since selected candidate was generated
  const isFormDirtyAgainstCandidate = useMemo(() => {
    if (!state.candidate) return false
    return computeRequirementsFingerprint(state.formState) !== state.candidate.submittedFingerprint
  }, [state.candidate, state.formState])

  // Selected exterior data
  const displayedExterior = state.activeView === 'accepted'
    ? state.acceptedLandscape
    : (state.candidate?.landscape ?? null)

  const viewStatus: 'accepted' | 'preview' | 'infeasible' = state.activeView === 'accepted'
    ? 'accepted'
    : (state.candidate?.outcome === 'infeasible' ? 'infeasible' : 'preview')

  // Candidate editable objects list for customization
  const candidateFeatures = useMemo(() => {
    const l = state.candidate?.landscape
    if (!l) return []
    const list: { id: string; type: string; category: string; position: [number, number]; label: string }[] = []
    if (Array.isArray(l.vegetation_nodes)) {
      for (const v of l.vegetation_nodes) {
        const coords = getPosCoords(v.position)
        if (v.json_id && coords) {
          list.push({
            id: v.json_id,
            type: 'vegetation',
            category: v.category || 'vegetation',
            position: coords,
            label: `Plant: ${v.category || v.json_id} (${coords[0].toFixed(1)}m, ${coords[1].toFixed(1)}m)`,
          })
        }
      }
    }
    if (Array.isArray(l.outdoor_elements)) {
      for (const o of l.outdoor_elements) {
        const coords = getPosCoords(o.position)
        if (o.json_id && coords) {
          list.push({
            id: o.json_id,
            type: 'outdoor_element',
            category: o.category || 'amenity',
            position: coords,
            label: `Amenity: ${o.category || o.json_id} (${coords[0].toFixed(1)}m, ${coords[1].toFixed(1)}m)`,
          })
        }
      }
    }
    if (Array.isArray(l.outdoor_lighting?.nodes)) {
      for (const lt of l.outdoor_lighting.nodes) {
        const coords = getPosCoords(lt.position)
        if (lt.json_id && coords) {
          const catStr = typeof lt.fixture_style === 'string' ? lt.fixture_style : 'light'
          list.push({
            id: lt.json_id,
            type: 'lighting',
            category: catStr,
            position: coords,
            label: `Light: ${catStr || lt.json_id} (${coords[0].toFixed(1)}m, ${coords[1].toFixed(1)}m)`,
          })
        }
      }
    }
    return list
  }, [state.candidate?.landscape])

  const selectedFeature = candidateFeatures.find((f) => f.id === state.selectedFeatureId)
  const lockedFeatureIds = useMemo(() => {
    return (state.formState.lockedFeatures || []).map((lf: any) => lf.json_id || lf.featureId || '')
  }, [state.formState.lockedFeatures])

  // Factors assessment data
  const factorsAssessment: FactorsAssessment | undefined = displayedExterior?.factors_assessment

  // Search handler
  const handleLocationSearch = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (cityQuery.trim().length < 2) return
    await controller.searchLocations(eliaApi, cityQuery.trim())
  }

  // Solar handler
  const handleSolarLookup = async () => {
    if (!state.formState.selectedLocation) return
    await controller.loadSolar(eliaApi, state.formState.selectedLocation)
  }

  // Candidate Save Handler
  const handleSaveCandidate = async () => {
    setSaveCandidateSuccess(null)
    const success = await controller.saveEditedCandidate(eliaApi, {
      setOutput: (comp, data) => setOutput(comp as any, data),
      setComponentStatus: (comp, status) => setComponentStatus(comp as any, status),
    })
    if (success) {
      setSaveCandidateSuccess('Customized landscape successfully saved and persisted to Master JSON.')
      setTimeout(() => setSaveCandidateSuccess(null), 5000)
    }
  }

  const form = state.formState

  return (
    <FeatureWorkflowShell
      componentId="elia_engine"
      title="ELIA-Engine: Eco-Spatial Landscape Intelligence"
      number="04"
      description="Generates exterior spatial planning including access, parking, safety zoning, solar orientation, and adaptive greenery."
      onPrev={() => router.push('/features/esai-engine')}
    >
      <div className="p-4 sm:p-6 lg:p-8 space-y-8">
        {/* Banner: Waiting for upstream project data (displayed when no real project context is loaded) */}
        {!projectId && (
          <div className="p-4 rounded-xl border border-blue-500/40 bg-blue-950/20 text-blue-200 text-sm flex items-start gap-3 shadow-sm">
            <Info className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-semibold text-blue-300">Waiting for upstream project data</div>
              <p className="mt-0.5 text-xs text-blue-200/90 leading-relaxed">
                No active project is selected. The requirements form can be reviewed and configured below, but spatial plan generation, validation, and saving require an authoritative project with upstream geometry from Components 1–3.
              </p>
            </div>
          </div>
        )}

        {/* Top Operational Status Banners */}
        {state.requiresReconciliation && (
          <div className="p-4 rounded-xl border border-rose-500/40 bg-rose-950/20 text-rose-200 text-sm flex items-start justify-between gap-3 shadow-sm">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-rose-300">
                  {state.unresolvedMutation?.status === 'processing'
                    ? 'Mutation Still Processing on Server'
                    : 'Reconciliation Required'}
                </div>
                <p className="mt-0.5 leading-relaxed text-xs">
                  {state.unresolvedMutation?.status === 'processing'
                    ? 'The previous exterior layout mutation is still processing on the server. Generate & Save remains blocked until processing completes.'
                    : state.actionError || 'An uncertain network or transport failure occurred during the previous save request. Generate & Save and authoritative export remain blocked until reconciliation confirms backend state.'}
                </p>
                {state.unresolvedMutation && (
                  <div className="mt-1 text-[11px] font-mono text-rose-300/80">
                    Source rev: {state.unresolvedMutation.sourceRevision} · Mode: {state.unresolvedMutation.submittedGenerationMode} · Status: {state.unresolvedMutation.status}
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="outline"
                className="border-rose-500/40 text-rose-200 hover:bg-rose-900/30 text-xs"
                onClick={() => controller.reconcileMutation(eliaApi)}
                disabled={state.isReconciling}
              >
                {state.isReconciling ? (
                  <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                )}
                Check Status & Reconcile
              </Button>
            </div>
          </div>
        )}

        {state.conflictError && (
          <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-950/20 text-amber-200 text-sm flex items-start justify-between gap-3 shadow-sm">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-amber-300">Stale Project Revision</div>
                <p className="mt-0.5 leading-relaxed">{state.conflictError}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="border-amber-500/40 text-amber-200 shrink-0"
                onClick={() => {
                  controller.loadAuthoritativeContext(eliaApi)
                  controller.loadLatestRun(eliaApi)
                }}
              >
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh Context
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-amber-200/70 hover:text-amber-200 text-xs"
                onClick={() => controller.dismissConflict()}
              >
                Dismiss
              </Button>
            </div>
          </div>
        )}

        {state.actionError && (
          <div className="p-4 rounded-xl border border-rose-500/40 bg-rose-950/20 text-rose-200 text-sm flex items-start justify-between gap-2.5 shadow-sm">
            <div className="flex items-start gap-2.5">
              <XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold text-rose-300">Operation Notice</div>
                <p className="mt-0.5 leading-relaxed">{state.actionError}</p>
              </div>
            </div>
            <Button
              size="sm"
              variant="ghost"
              className="text-rose-200/70 hover:text-rose-200 text-xs shrink-0"
              onClick={() => controller.dismissActionError()}
            >
              Dismiss
            </Button>
          </div>
        )}

        {saveCandidateSuccess && (
          <div className="p-4 rounded-xl border border-emerald-500/40 bg-emerald-950/20 text-emerald-200 text-sm flex items-center gap-2.5 shadow-sm">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            <span className="font-medium">{saveCandidateSuccess}</span>
          </div>
        )}

        {/* ------------------------------------------------------------------- */}
        {/* Main Grid: Input & Context Controls (Left) vs Output Viewer (Right) */}
        {/* ------------------------------------------------------------------- */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* LEFT COLUMN: Context & Requirements Form (5 cols) */}
          <div className="lg:col-span-5 space-y-6">
            {/* 1. Project Context & Upstream Geometry Card */}
            <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
              <CardHeader className="pb-3 pt-4 px-5 border-b border-border/40 flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Compass className="w-4 h-4 text-primary" /> Inherited Site Context
                  </CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {projectName || (projectId ? `Project ${projectId}` : 'No active project')} · Authoritative upstream geometry
                  </p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-muted-foreground"
                  onClick={() => {
                    if (projectId) {
                      controller.loadAuthoritativeContext(eliaApi)
                      controller.loadLatestRun(eliaApi)
                    }
                  }}
                  disabled={!projectId || state.isLoadingContext}
                  title="Reload authoritative project context"
                >
                  <RefreshCw className={`w-4 h-4 ${state.isLoadingContext ? 'animate-spin' : ''}`} />
                </Button>
              </CardHeader>
              <CardContent className="p-5 space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-2.5">
                  <div className="p-2.5 rounded-lg border border-border/50 bg-muted/30">
                    <span className="text-muted-foreground block text-[11px]">Land Boundary</span>
                    <span className="font-semibold font-mono text-foreground text-sm">
                      {siteViewModel.landPolygon
                        ? `${siteViewModel.landPolygon.coordinates?.[0]?.length || 0} pts`
                        : projectId ? 'Missing' : 'Waiting'}
                    </span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      {siteViewModel.geometryState === 'ready' ? 'Polygon verified' : siteViewModel.geometryState}
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg border border-border/50 bg-muted/30">
                    <span className="text-muted-foreground block text-[11px]">House Footprint</span>
                    <span className="font-semibold font-mono text-foreground text-sm">
                      {siteViewModel.housePolygon
                        ? `${siteViewModel.housePolygon.coordinates?.[0]?.length || 0} pts`
                        : projectId ? 'Missing' : 'Waiting'}
                    </span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      Height: ~{siteViewModel.buildingHeightM?.toFixed(1) || '3.5'}m {siteViewModel.isHeightEstimated ? '(est)' : ''}
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg border border-border/50 bg-muted/30">
                    <span className="text-muted-foreground block text-[11px]">Project Revision</span>
                    <span className="font-semibold font-mono text-foreground text-sm">
                      {state.sourceRevision !== null && state.sourceRevision !== undefined ? state.sourceRevision : 'Unloaded'}
                    </span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      CAS concurrency key
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg border border-border/50 bg-muted/30">
                    <span className="text-muted-foreground block text-[11px]">Accepted Exterior</span>
                    <span className="font-semibold font-mono text-foreground text-sm">
                      {state.acceptedLandscape ? 'Persisted' : 'None yet'}
                    </span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      In Master JSON
                    </span>
                  </div>
                </div>

                {siteViewModel.geometryState !== 'ready' && (
                  <div className="p-2.5 rounded-md border border-amber-500/30 bg-amber-950/20 text-amber-200 text-xs">
                    {siteViewModel.geometryMessage || 'Upstream site geometry required from previous components.'}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 2. Client Requirements Form Tabs */}
            <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
              <CardHeader className="pb-3 pt-4 px-5 border-b border-border/40">
                <CardTitle className="text-base font-semibold flex items-center justify-between">
                  <span>Client Requirements</span>
                  <div className="flex items-center gap-1.5">
                    {state.requirementsDirty && (
                      <Badge variant="outline" className="text-[10px] text-amber-300 border-amber-500/40">
                        Unsaved Edits
                      </Badge>
                    )}
                    <Badge variant="outline" className="text-[10px] font-mono">
                      Units: meters
                    </Badge>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5">
                <Tabs defaultValue="concept" className="w-full">
                  <TabsList className="grid grid-cols-5 mb-4 text-xs">
                    <TabsTrigger value="concept" className="text-xs py-1.5"><Sliders className="w-3.5 h-3.5 mr-1" /> Style</TabsTrigger>
                    <TabsTrigger value="access" className="text-xs py-1.5"><Car className="w-3.5 h-3.5 mr-1" /> Access</TabsTrigger>
                    <TabsTrigger value="garden" className="text-xs py-1.5"><Trees className="w-3.5 h-3.5 mr-1" /> Garden</TabsTrigger>
                    <TabsTrigger value="solar" className="text-xs py-1.5"><Sun className="w-3.5 h-3.5 mr-1" /> Eco</TabsTrigger>
                    <TabsTrigger value="lighting" className="text-xs py-1.5"><Lightbulb className="w-3.5 h-3.5 mr-1" /> Lighting</TabsTrigger>
                  </TabsList>

                  {/* TAB 1: DESIGN CONCEPT & STYLE */}
                  <TabsContent value="concept" className="space-y-4">
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label htmlFor="design-concept" className="text-xs font-semibold text-foreground">Design Concept</Label>
                      <select
                        id="design-concept"
                        value={
                          ['modern', 'greeny', 'minimalistic', 'minimalist'].includes((form.designStyle || '').toLowerCase())
                            ? (form.designStyle.toLowerCase() === 'minimalist' ? 'minimalistic' : form.designStyle.toLowerCase())
                            : ''
                        }
                        onChange={(e) => controller.editRequirement({ designStyle: e.target.value })}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="" disabled>Select a design concept</option>
                        <option value="modern">Modern</option>
                        <option value="greeny">Greeny</option>
                        <option value="minimalistic">Minimalistic</option>
                      </select>
                      <p className="text-[11px] text-muted-foreground leading-tight pt-1">
                        Influences planting density, open space weighting, and amenity arrangement through explicit planner heuristics.
                      </p>
                    </div>

                    {/* Maintenance Preference */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label htmlFor="maintenance-pref" className="text-xs font-semibold text-foreground">Maintenance Preference</Label>
                      <select
                        id="maintenance-pref"
                        value={form.maintenancePreference || 'no_preference'}
                        onChange={(e) => controller.editRequirement({ maintenancePreference: e.target.value as any })}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="low">Low (Drought-tolerant, slow-growing)</option>
                        <option value="medium">Medium (Regular pruning & care)</option>
                        <option value="high">High (Lush ornamental maintenance)</option>
                        <option value="no_preference">No preference</option>
                      </select>
                      <span className="text-[10px] text-muted-foreground block">
                        Used to filter and score plant species from the botanical catalogue.
                      </span>
                    </div>

                    {/* Water Availability / Irrigation */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label htmlFor="water-avail" className="text-xs font-semibold text-foreground">Water Availability / Irrigation</Label>
                      <select
                        id="water-avail"
                        value={form.waterAvailability || 'unknown'}
                        onChange={(e) => controller.editRequirement({ waterAvailability: e.target.value as any })}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="limited">Limited (Low irrigation capacity)</option>
                        <option value="regular">Regular (Standard domestic tap/well supply)</option>
                        <option value="irrigation_available">Irrigation available (Automated sprinkler/drip)</option>
                        <option value="unknown">Unknown (Not yet assessed)</option>
                      </select>
                      <span className="text-[10px] text-muted-foreground block">
                        Unknown water availability will not assume optimal hydration.
                      </span>
                    </div>
                  </TabsContent>

                  {/* TAB 2: ACCESS & PARKING */}
                  <TabsContent value="access" className="space-y-4">
                    {/* Garage */}
                    <div className="space-y-3 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="garage-req" className="font-medium cursor-pointer">Require Garage / Parking</Label>
                        <input
                          id="garage-req"
                          type="checkbox"
                          checked={form.garageRequired}
                          onChange={(e) => controller.editRequirement({ garageRequired: e.target.checked })}
                          className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                        />
                      </div>

                      {form.garageRequired && (
                        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/30">
                          <div>
                            <Label htmlFor="garage-cap" className="text-xs text-muted-foreground">Garage Capacity</Label>
                            <Input
                              id="garage-cap"
                              type="number"
                              min={1}
                              max={3}
                              value={form.garageCapacity}
                              onChange={(e) => controller.editRequirement({ garageCapacity: e.target.value })}
                              className="mt-1 h-8 text-xs font-mono"
                            />
                          </div>
                          <div>
                            <Label htmlFor="vehicle-cnt" className="text-xs text-muted-foreground">Vehicle Count</Label>
                            <Input
                              id="vehicle-cnt"
                              type="number"
                              min={1}
                              max={3}
                              value={form.vehicleCount}
                              onChange={(e) => controller.editRequirement({ vehicleCount: e.target.value })}
                              className="mt-1 h-8 text-xs font-mono"
                            />
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Driveway */}
                    <div className="space-y-3 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="driveway-req" className="font-medium cursor-pointer">Generate Driveway</Label>
                        <input
                          id="driveway-req"
                          type="checkbox"
                          checked={form.drivewayRequired}
                          onChange={(e) => controller.editRequirement({ drivewayRequired: e.target.checked })}
                          className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                        />
                      </div>

                      {form.drivewayRequired && (
                        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/30">
                          <div>
                            <Label htmlFor="drive-style" className="text-xs text-muted-foreground">Driveway Style</Label>
                            <select
                              id="drive-style"
                              value={form.drivewayStyle}
                              onChange={(e) => controller.editRequirement({ drivewayStyle: e.target.value })}
                              className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                            >
                              <option value="auto">Auto Heuristic</option>
                              <option value="straight">Direct Straight</option>
                              <option value="curved">Curved Path</option>
                            </select>
                          </div>
                          <div className="flex items-center pt-5">
                            <label className="flex items-center gap-2 text-xs cursor-pointer">
                              <input
                                type="checkbox"
                                checked={form.turningSpaceRequired}
                                onChange={(e) => controller.editRequirement({ turningSpaceRequired: e.target.checked })}
                                className="w-3.5 h-3.5 rounded border-border text-primary"
                              />
                              <span>Turning Space</span>
                            </label>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Gate */}
                    <div className="grid grid-cols-2 gap-3 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <div>
                        <Label htmlFor="gate-type" className="text-xs text-muted-foreground">Gate Style</Label>
                        <select
                          id="gate-type"
                          value={form.gateType}
                          onChange={(e) => controller.editRequirement({ gateType: e.target.value })}
                          className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                        >
                          <option value="unspecified">Auto Placement</option>
                          <option value="sliding">Sliding Gate</option>
                          <option value="swing">Swing Gate</option>
                          <option value="double_swing">Double Swing</option>
                        </select>
                      </div>
                      <div>
                        <Label htmlFor="gate-width" className="text-xs text-muted-foreground">Gate Width (m)</Label>
                        <Input
                          id="gate-width"
                          type="number"
                          step={0.1}
                          min={2.0}
                          max={6.0}
                          value={form.gateWidthM}
                          onChange={(e) => controller.editRequirement({ gateWidthM: e.target.value })}
                          className="mt-1 h-8 text-xs font-mono"
                        />
                      </div>
                    </div>
                  </TabsContent>

                  {/* TAB 3: GARDEN & LANDSCAPE */}
                  <TabsContent value="garden" className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label htmlFor="green-density" className="text-xs text-muted-foreground">Vegetation Density</Label>
                        <select
                          id="green-density"
                          value={form.greeneryDensity}
                          onChange={(e) => controller.editRequirement({ greeneryDensity: e.target.value as any })}
                          className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                        >
                          <option value="low">Low (Spacious)</option>
                          <option value="medium">Medium (Balanced)</option>
                          <option value="high">High (Lush Garden)</option>
                        </select>
                      </div>
                      <div>
                        <Label htmlFor="open-ratio" className="text-xs text-muted-foreground">Open Space Ratio</Label>
                        <Input
                          id="open-ratio"
                          type="number"
                          step={0.05}
                          min={0.1}
                          max={0.9}
                          value={form.openSpaceRatio}
                          onChange={(e) => controller.editRequirement({ openSpaceRatio: e.target.value })}
                          className="mt-1 h-8 text-xs font-mono"
                        />
                      </div>
                    </div>

                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20 text-xs">
                      <div className="font-medium text-muted-foreground mb-1">Garden Features</div>
                      <div className="grid grid-cols-2 gap-2">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={form.gardenRequired}
                            onChange={(e) => controller.editRequirement({ gardenRequired: e.target.checked })}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Planting Beds</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={form.lawnRequired}
                            onChange={(e) => controller.editRequirement({ lawnRequired: e.target.checked })}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Turf / Lawn</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={form.shadeTreePreference}
                            onChange={(e) => controller.editRequirement({ shadeTreePreference: e.target.checked })}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Shade Canopy Trees</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={form.gardenSeatingRequired}
                            onChange={(e) => controller.editRequirement({ gardenSeatingRequired: e.target.checked })}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Outdoor Seating</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={form.gardenTableSetRequired}
                            onChange={(e) => controller.editRequirement({ gardenTableSetRequired: e.target.checked })}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Garden Dining Set</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={form.pedestrianPathRequired}
                            onChange={(e) => controller.editRequirement({ pedestrianPathRequired: e.target.checked })}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Pedestrian Paths</span>
                        </label>
                      </div>
                    </div>

                    {/* Plant Preferences Section */}
                    <div className="space-y-3 p-3 rounded-lg border border-border/40 bg-muted/20 text-xs">
                      <Label className="text-xs font-semibold flex items-center gap-1.5">
                        <Tag className="w-3.5 h-3.5 text-primary" /> Preferred Plant Species
                      </Label>
                      <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto p-1 border rounded bg-background">
                        {catalogEntries.slice(0, 8).map((sp) => {
                          const isPref = (form.preferredPlantIds || []).includes(sp.id)
                          return (
                            <button
                              key={sp.id}
                              type="button"
                              onClick={() => {
                                const current = form.preferredPlantIds || []
                                const next = isPref
                                  ? current.filter((id) => id !== sp.id)
                                  : [...current, sp.id]
                                controller.editRequirement({ preferredPlantIds: next })
                              }}
                              className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                                isPref ? 'bg-primary text-primary-foreground border-primary' : 'bg-muted text-muted-foreground border-border'
                              }`}
                            >
                              {sp.name}
                            </button>
                          )
                        })}
                      </div>
                      <span className="text-[10px] text-muted-foreground block">
                        Selected plants receive score bonuses during vegetation placement.
                      </span>
                    </div>

                    {/* Boundary Wall */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="wall-req" className="text-xs font-medium cursor-pointer">Boundary Enclosure</Label>
                        <input
                          id="wall-req"
                          type="checkbox"
                          checked={form.boundaryWallRequired}
                          onChange={(e) => controller.editRequirement({ boundaryWallRequired: e.target.checked })}
                          className="w-3.5 h-3.5 rounded text-primary"
                        />
                      </div>
                      {form.boundaryWallRequired && (
                        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border/30">
                          <div>
                            <Label className="text-[11px] text-muted-foreground">Wall Type</Label>
                            <select
                              value={form.boundaryWallType}
                              onChange={(e) => controller.editRequirement({ boundaryWallType: e.target.value })}
                              className="mt-1 w-full h-7 rounded border border-input bg-background px-2 text-xs"
                            >
                              <option value="masonry">Masonry Wall</option>
                              <option value="fence">Perimeter Fence</option>
                              <option value="hedge">Living Green Hedge</option>
                            </select>
                          </div>
                          <div>
                            <Label className="text-[11px] text-muted-foreground">Height (m)</Label>
                            <Input
                              type="number"
                              step={0.1}
                              value={form.boundaryWallHeightM}
                              onChange={(e) => controller.editRequirement({ boundaryWallHeightM: e.target.value })}
                              className="mt-1 h-7 text-xs font-mono"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </TabsContent>

                  {/* TAB 4: SOLAR & ENVIRONMENTAL */}
                  <TabsContent value="solar" className="space-y-4">
                    {/* Climate Zone */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label htmlFor="climate-zone" className="text-xs font-semibold">Sri Lankan Climate Zone</Label>
                      <select
                        id="climate-zone"
                        value={form.climateZone || 'unknown'}
                        onChange={(e) => controller.editRequirement({ climateZone: e.target.value as any })}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="unknown">Unknown (Site analysis required)</option>
                        <option value="wet_zone">Wet Zone (Colombo, Kandy, Galle, Ratnapura)</option>
                        <option value="intermediate_zone">Intermediate Zone (Kurunegala, Badulla)</option>
                        <option value="dry_zone">Dry Zone (Jaffna, Anuradhapura, Hambantota)</option>
                      </select>
                      <span className="text-[10px] text-muted-foreground block">
                        Used to match botanical tolerances against regional rainfall and humidity.
                      </span>
                    </div>

                    {/* Site Exposure */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label htmlFor="site-exposure" className="text-xs font-semibold">Site Sunlight Exposure</Label>
                      <select
                        id="site-exposure"
                        value={form.siteExposure || 'unknown'}
                        onChange={(e) => controller.editRequirement({ siteExposure: e.target.value as any })}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="unknown">Unknown (Calculated from orientation/irradiance)</option>
                        <option value="sheltered">Sheltered (Protected by surrounding buildings)</option>
                        <option value="moderate">Moderate Exposure</option>
                        <option value="exposed">High Sun Exposure</option>
                        <option value="coastal_wind">Coastal Wind / Maritime Exposure</option>
                      </select>
                    </div>

                    {/* Locality Search */}
                    <form onSubmit={handleLocationSearch} className="space-y-2 pt-1">
                      <Label htmlFor="elia-city-search" className="text-xs">Search Locality for Solar Positioning</Label>
                      <div className="flex gap-2">
                        <Input
                          id="elia-city-search"
                          value={cityQuery}
                          onChange={(e) => setCityQuery(e.target.value)}
                          placeholder="Colombo, Kandy, Galle..."
                          className="h-8 text-xs"
                        />
                        <Button
                          type="submit"
                          variant="outline"
                          size="sm"
                          disabled={state.isSearchingLocation || cityQuery.trim().length < 2}
                          className="h-8 px-2.5"
                        >
                          {state.isSearchingLocation ? <LoaderCircle className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                        </Button>
                      </div>
                    </form>

                    {state.locations.length > 0 && (
                      <div className="max-h-32 overflow-y-auto space-y-1 rounded border border-border p-1 text-xs">
                        {state.locations.map((loc) => (
                          <button
                            key={loc.id}
                            type="button"
                            onClick={() => controller.selectLocation(loc)}
                            className={`w-full text-left p-1.5 rounded transition-colors ${form.selectedLocation?.id === loc.id ? 'bg-primary/20 text-primary font-medium' : 'hover:bg-muted'}`}
                          >
                            <span className="flex items-center gap-1.5">
                              <MapPin className="w-3 h-3 shrink-0" /> {loc.name}
                            </span>
                            <span className="text-[10px] text-muted-foreground pl-4.5 block">
                              {loc.admin1 || loc.country} ({loc.latitude.toFixed(3)}, {loc.longitude.toFixed(3)})
                            </span>
                          </button>
                        ))}
                      </div>
                    )}

                    {form.selectedLocation && (
                      <div className="p-2.5 rounded-lg border border-border/50 bg-muted/30 space-y-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-primary">{form.selectedLocation.name}</span>
                          <span className="text-[10px] font-mono text-muted-foreground">
                            {form.selectedLocation.latitude.toFixed(4)}, {form.selectedLocation.longitude.toFixed(4)}
                          </span>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="w-full h-7 text-xs"
                          onClick={handleSolarLookup}
                          disabled={state.isLoadingSolar}
                        >
                          {state.isLoadingSolar ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1" /> : <Sun className="w-3.5 h-3.5 mr-1" />}
                          Load Live Solar Irradiance
                        </Button>
                      </div>
                    )}

                    {state.solar && (
                      <div className="p-2.5 rounded-lg border border-border/50 bg-muted/40 space-y-1.5 text-xs">
                        <div className="flex items-center justify-between font-medium">
                          <span>Solar Irradiance (GHI)</span>
                          <span className="font-mono text-primary">{state.solar.irradiance_w_m2.shortwave_radiation ?? '—'} W/m²</span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                          <span>Sun Elevation / Azimuth</span>
                          <span>{state.solar.solar_position.elevation_degrees.toFixed(1)}° / {state.solar.solar_position.azimuth_degrees.toFixed(1)}°</span>
                        </div>
                      </div>
                    )}
                  </TabsContent>

                  {/* TAB 5: LIGHTING & AMENITIES */}
                  <TabsContent value="lighting" className="space-y-4">
                    {/* Lighting & Vertical Greenery Options */}
                    <div className="space-y-3 p-3 rounded-lg border border-border/40 bg-muted/20 text-xs">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="light-req" className="font-medium cursor-pointer">Include Outdoor Lighting Plan</Label>
                        <input
                          id="light-req"
                          type="checkbox"
                          checked={form.lightingRequired}
                          onChange={(e) => controller.editRequirement({ lightingRequired: e.target.checked })}
                          className="w-4 h-4 rounded text-primary"
                        />
                      </div>
                      {form.lightingRequired && (
                        <div className="pt-2 border-t border-border/30">
                          <Label className="text-[11px] text-muted-foreground">Lighting Fixture Style</Label>
                          <select
                            value={form.lightingStyle}
                            onChange={(e) => controller.editRequirement({ lightingStyle: e.target.value })}
                            className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                          >
                            <option value="minimal">Minimal Bollards</option>
                            <option value="accent">Pathway &amp; Tree Accent</option>
                            <option value="ambient">Ambient Perimeter</option>
                          </select>
                        </div>
                      )}
                    </div>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>

            {/* 3. Generation Mode & Operational Actions Card */}
            <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
              <CardContent className="p-5 space-y-4">
                {/* Generation Mode Selector */}
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold flex items-center justify-between">
                    <span>Generation Mode</span>
                    <span className="text-[10px] font-mono text-muted-foreground">Explicit contract mode</span>
                  </Label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => controller.editRequirement({ generationMode: 'baseline' })}
                      className={`p-2.5 rounded-lg border text-left text-xs transition-colors ${form.generationMode === 'baseline' ? 'border-primary bg-primary/10 text-primary' : 'border-border/60 hover:bg-muted/40'}`}
                    >
                      <div className="font-semibold flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5" /> Baseline Planner
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        Deterministic spatial heuristics
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => controller.editRequirement({ generationMode: 'trained_model' })}
                      className={`p-2.5 rounded-lg border text-left text-xs transition-colors ${form.generationMode === 'trained_model' ? 'border-amber-500 bg-amber-950/20 text-amber-300' : 'border-border/60 hover:bg-muted/40'}`}
                    >
                      <div className="font-semibold flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5" /> Trained AI Model
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        Google Colab (Stage 6/7)
                      </div>
                    </button>
                  </div>
                </div>

                {form.generationMode === 'trained_model' && (
                  <div className="p-2.5 rounded border border-amber-500/30 bg-amber-950/20 text-amber-200 text-[11px] leading-tight">
                    Model adapter not yet registered on this backend. Requesting this mode triggers explicit 503 response without fallback.
                  </div>
                )}

                {/* Validation Response Summary Banner */}
                {state.validationResult && (
                  <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-950/20 text-emerald-200 text-xs space-y-1">
                    <div className="font-semibold flex items-center gap-1.5 text-emerald-300">
                      <CheckCircle2 className="w-4 h-4" /> Requirements Validated
                    </div>
                    <div className="grid grid-cols-2 gap-1 text-[11px] pt-1 font-mono">
                      <span>Land Area: {state.validationResult.geometry.land_area_m2.toFixed(1)} m²</span>
                      <span>House Footprint: {state.validationResult.geometry.house_footprint_area_m2.toFixed(1)} m²</span>
                      <span>North: {state.validationResult.orientation.north_angle_degrees.toFixed(1)}°</span>
                      <span>Units: {state.validationResult.geometry.source_units}</span>
                    </div>
                  </div>
                )}

                {state.validationError && (
                  <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-950/20 text-rose-200 text-xs">
                    <div className="font-semibold text-rose-300">Validation Notice</div>
                    <p className="mt-0.5">{state.validationError}</p>
                  </div>
                )}

                {/* Main Action Buttons */}
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full text-xs h-9"
                    onClick={() => controller.validateRequirements(eliaApi)}
                    disabled={!projectId || state.isValidating || state.isPreviewing || state.isGenerating}
                    title={!projectId ? 'Waiting for upstream project context' : 'Validate input requirements against upstream geometry'}
                  >
                    {state.isValidating ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                    Validate Inputs
                  </Button>

                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full text-xs h-9"
                    onClick={() => controller.previewCandidate(eliaApi)}
                    disabled={!projectId || state.isPreviewing || state.isGenerating || state.isValidating}
                    title={!projectId ? 'Waiting for upstream project context' : 'Generate candidate proposal in memory without modifying database'}
                  >
                    {state.isPreviewing ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Eye className="w-3.5 h-3.5 mr-1.5" />}
                    Preview (Unsaved)
                  </Button>
                </div>

                <div>
                  <Button
                    type="button"
                    className="w-full electric-glow h-10 text-sm font-semibold"
                    onClick={() => controller.generateAndSave(eliaApi, { setOutput, setComponentStatus })}
                    disabled={!projectId || !controller.canGenerateAndSave()}
                    title={
                      !projectId
                        ? 'Waiting for upstream project context'
                        : state.requiresReconciliation
                        ? 'Project state must be reconciled before saving'
                        : state.sourceRevision === null || state.sourceRevision === undefined
                        ? 'Authoritative project revision required before saving'
                        : state.contextFreshness !== 'current'
                        ? 'Authoritative project context must be current before saving'
                        : 'Generate candidate and persist accepted result to project Master JSON'
                    }
                  >
                    {state.isGenerating ? (
                      <span className="flex items-center gap-2">
                        <LoaderCircle className="w-4 h-4 animate-spin" /> Persisting Exterior Spatial Plan...
                      </span>
                    ) : (
                      'Generate & Save Landscape'
                    )}
                  </Button>
                  {!projectId && (
                    <p className="text-[10px] text-blue-400 text-center mt-1">
                      Waiting for upstream project data. Open an active project from previous components to enable generation.
                    </p>
                  )}
                  {projectId && state.requiresReconciliation && (
                    <p className="text-[10px] text-rose-400 text-center mt-1">
                      Project state must be reconciled before retrying save. Click &quot;Check Status &amp; Reconcile&quot; above.
                    </p>
                  )}
                  {projectId && !state.requiresReconciliation && (state.sourceRevision === null || state.sourceRevision === undefined || state.contextFreshness !== 'current') && (
                    <p className="text-[10px] text-amber-400/90 text-center mt-1">
                      Authoritative confirmed project revision required before saving. Click refresh context above.
                    </p>
                  )}
                </div>

                {/* Latest Run Inspector Card */}
                {state.latestRun && (
                  <div className="pt-2 border-t border-border/40 text-[11px] text-muted-foreground flex items-center justify-between">
                    <span className="flex items-center gap-1 font-mono">
                      <History className="w-3 h-3" /> Run {state.latestRun.run_id.slice(0, 8)}: {state.latestRun.status}
                    </span>
                    <time className="text-[10px]">
                      {state.latestRun.completed_at ? new Date(state.latestRun.completed_at).toLocaleTimeString() : ''}
                    </time>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* RIGHT COLUMN: Output Viewer, Object Customization & Assessment (7 cols) */}
          <div className="lg:col-span-7 space-y-6">
            <EliaOutputWrapper
              projectName={projectName || ''}
              projectId={projectId || undefined}
              masterJson={state.authoritativeMaster || masterJson}
              data={displayedExterior}
              isProcessing={state.isGenerating || state.isPreviewing}
              runError={state.actionError || undefined}
              viewStatus={viewStatus}
              sourceRevision={state.sourceRevision}
              candidateRevision={state.candidate?.sourceRevision}
              acceptedRevision={state.acceptedProvenance?.sourceRevision}
              acceptedSnapshot={state.acceptedProvenance?.sourceSnapshot}
              generationMode={state.candidate?.generationMode || form.generationMode}
              acceptedData={state.acceptedLandscape}
              candidateData={state.candidate?.landscape}
              candidateSnapshot={state.candidate?.sourceSnapshot}
              candidateKind={state.candidate?.kind}
              candidateStatus={state.candidate?.outcome === 'infeasible' ? 'infeasible' : 'preview'}
              contextFreshness={state.contextFreshness}
              requiresReconciliation={state.requiresReconciliation}
              isFormDirtyAgainstCandidate={isFormDirtyAgainstCandidate}
              activeView={state.activeView}
              onToggleView={(view) => controller.toggleActiveView(view)}
              validationSummary={displayedExterior?.validation_summary}
              selectedFeatureId={state.selectedFeatureId}
              onSelectFeature={(id) => controller.selectFeature(id)}
              lockedFeatureIds={lockedFeatureIds}
            />

            {/* 4. CUSTOMER CUSTOMIZATION & PROPERTY EDITOR PANEL */}
            {state.candidate && state.activeView === 'candidate' && (
              <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
                <CardHeader className="pb-3 pt-4 px-5 border-b border-border/40 flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                      <Sliders className="w-4 h-4 text-primary" /> Modify Landscape Proposal
                    </CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Select generated plants, seating, or lighting to adjust coordinates, replace species, or lock before regeneration.
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      onClick={() => controller.undoCandidateEdit()}
                      disabled={state.candidateEditHistory.length === 0}
                      title="Undo last modification"
                    >
                      <Undo2 className="w-3.5 h-3.5 mr-1" /> Undo
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs text-muted-foreground"
                      onClick={() => controller.resetCandidateEdits()}
                      disabled={state.candidateEditHistory.length === 0}
                      title="Reset candidate edits"
                    >
                      <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="p-5 space-y-4">
                  {/* Feature Selection Dropdown */}
                  <div className="space-y-1.5">
                    <Label htmlFor="feature-selector" className="text-xs font-medium">Select Generated Element to Edit</Label>
                    <select
                      id="feature-selector"
                      value={state.selectedFeatureId || ''}
                      onChange={(e) => controller.selectFeature(e.target.value || null)}
                      className="w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                    >
                      <option value="">-- Choose an exterior object or click it on the 2D Plan --</option>
                      {candidateFeatures.map((f) => (
                        <option key={f.id} value={f.id}>
                          {lockedFeatureIds.includes(f.id) ? '🔒 ' : ''}{f.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Property Editor for Selected Feature */}
                  {selectedFeature ? (
                    <div className="p-3.5 rounded-lg border border-primary/30 bg-primary/5 space-y-3 text-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-primary">{selectedFeature.category}</span>
                          <span className="font-mono text-[10px] text-muted-foreground">({selectedFeature.id})</span>
                          {lockedFeatureIds.includes(selectedFeature.id) && (
                            <Badge variant="outline" className="border-amber-500/40 text-amber-300 text-[10px] gap-1">
                              <Lock className="w-2.5 h-2.5" /> Locked
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Button
                            size="sm"
                            variant={lockedFeatureIds.includes(selectedFeature.id) ? 'default' : 'outline'}
                            className="h-7 text-xs"
                            onClick={() => controller.toggleFeatureLock(selectedFeature.id)}
                            title="Preserve this object position across regenerations"
                          >
                            {lockedFeatureIds.includes(selectedFeature.id) ? (
                              <>
                                <Unlock className="w-3 h-3 mr-1" /> Unlock
                              </>
                            ) : (
                              <>
                                <Lock className="w-3 h-3 mr-1" /> Lock
                              </>
                            )}
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            className="h-7 text-xs"
                            onClick={() => controller.removeFeature(selectedFeature.id)}
                            title="Remove this object from proposal"
                          >
                            <Trash2 className="w-3 h-3 mr-1" /> Remove
                          </Button>
                        </div>
                      </div>

                      {/* Position Coordinates with Nudge Controls */}
                      <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/30">
                        <div>
                          <Label className="text-[11px] text-muted-foreground">X Coordinate (m)</Label>
                          <div className="flex items-center gap-1 mt-1">
                            <Button
                              size="icon"
                              variant="outline"
                              className="h-7 w-7 text-xs shrink-0"
                              onClick={() => controller.editFeaturePosition(selectedFeature.id, [selectedFeature.position[0] - 0.5, selectedFeature.position[1]])}
                              title="Nudge Left -0.5m"
                            >
                              <ArrowLeft className="w-3 h-3" />
                            </Button>
                            <Input
                              type="number"
                              step={0.1}
                              value={selectedFeature.position[0].toFixed(2)}
                              onChange={(e) => {
                                const val = parseFloat(e.target.value)
                                if (!isNaN(val)) controller.editFeaturePosition(selectedFeature.id, [val, selectedFeature.position[1]])
                              }}
                              className="h-7 text-xs font-mono text-center"
                            />
                            <Button
                              size="icon"
                              variant="outline"
                              className="h-7 w-7 text-xs shrink-0"
                              onClick={() => controller.editFeaturePosition(selectedFeature.id, [selectedFeature.position[0] + 0.5, selectedFeature.position[1]])}
                              title="Nudge Right +0.5m"
                            >
                              <ArrowRight className="w-3 h-3" />
                            </Button>
                          </div>
                        </div>

                        <div>
                          <Label className="text-[11px] text-muted-foreground">Y Coordinate (m)</Label>
                          <div className="flex items-center gap-1 mt-1">
                            <Button
                              size="icon"
                              variant="outline"
                              className="h-7 w-7 text-xs shrink-0"
                              onClick={() => controller.editFeaturePosition(selectedFeature.id, [selectedFeature.position[0], selectedFeature.position[1] - 0.5])}
                              title="Nudge Down -0.5m"
                            >
                              <ArrowDown className="w-3 h-3" />
                            </Button>
                            <Input
                              type="number"
                              step={0.1}
                              value={selectedFeature.position[1].toFixed(2)}
                              onChange={(e) => {
                                const val = parseFloat(e.target.value)
                                if (!isNaN(val)) controller.editFeaturePosition(selectedFeature.id, [selectedFeature.position[0], val])
                              }}
                              className="h-7 text-xs font-mono text-center"
                            />
                            <Button
                              size="icon"
                              variant="outline"
                              className="h-7 w-7 text-xs shrink-0"
                              onClick={() => controller.editFeaturePosition(selectedFeature.id, [selectedFeature.position[0], selectedFeature.position[1] + 0.5])}
                              title="Nudge Up +0.5m"
                            >
                              <ArrowUp className="w-3 h-3" />
                            </Button>
                          </div>
                        </div>
                      </div>

                      {/* Vegetation Replacement Dropdown */}
                      {selectedFeature.type === 'vegetation' && (
                        <div className="pt-2 border-t border-border/30">
                          <Label className="text-[11px] text-muted-foreground">Replace with Alternative Plant Species</Label>
                          <select
                            value={selectedFeature.category}
                            onChange={(e) => {
                              const chosen = catalogEntries.find((c) => c.id === e.target.value)
                              if (chosen) {
                                controller.replaceVegetationPlant(selectedFeature.id, {
                                  vegetation_id: chosen.id,
                                  display_name: chosen.name,
                                  scientific_name: chosen.scientific,
                                  category: chosen.category,
                                })
                              }
                            }}
                            className="mt-1 w-full h-8 rounded border border-input bg-background px-2 text-xs"
                          >
                            {catalogEntries.map((sp) => (
                              <option key={sp.id} value={sp.id}>
                                {sp.name} ({sp.scientific})
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="p-3 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                      Click an element in the 2D Plan above or select from the dropdown to edit its position, lock it, or swap species.
                    </div>
                  )}

                  {/* Candidate Validation Violations */}
                  {state.candidateValidationError && (
                    <div className="p-3 rounded-lg border border-rose-500/40 bg-rose-950/20 text-rose-200 text-xs space-y-1">
                      <div className="font-semibold flex items-center gap-1.5 text-rose-300">
                        <XCircle className="w-4 h-4" /> Customization Boundary Violation
                      </div>
                      <p>{state.candidateValidationError}</p>
                      {state.candidateValidationViolations.length > 0 && (
                        <ul className="list-disc pl-5 pt-1 space-y-0.5 font-mono text-[11px]">
                          {state.candidateValidationViolations.map((v, i) => (
                            <li key={i}>{v}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {/* Candidate Validation & Persistence Action Buttons */}
                  <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/40">
                    <Button
                      type="button"
                      variant="outline"
                      className="text-xs h-9"
                      onClick={() => controller.validateEditedCandidate(eliaApi)}
                      disabled={!projectId || state.isValidatingCandidate}
                    >
                      {state.isValidatingCandidate ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <ShieldCheck className="w-3.5 h-3.5 mr-1.5" />}
                      Validate Customization
                    </Button>

                    <Button
                      type="button"
                      className="text-xs h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                      onClick={handleSaveCandidate}
                      disabled={!projectId || state.isSavingCandidate || state.requiresReconciliation}
                    >
                      {state.isSavingCandidate ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Check className="w-3.5 h-3.5 mr-1.5" />}
                      Save Customized Design
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 5. RECOMMENDATIONS ASSESSMENT PANEL (7 Factors) */}
            {factorsAssessment && (
              <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
                <CardHeader className="pb-3 pt-4 px-5 border-b border-border/40">
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-primary" /> Environmental &amp; Customer Factor Assessment
                  </CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Concise verification of spatial, botanical, and climatic constraints considered for this landscape proposal.
                  </p>
                </CardHeader>
                <CardContent className="p-5 space-y-4 text-xs">
                  {/* Factor Evaluation Table */}
                  <div className="overflow-x-auto rounded-lg border border-border/50">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead className="bg-muted/50 text-muted-foreground border-b border-border/50 font-medium text-[11px]">
                        <tr>
                          <th className="p-2.5">Factor</th>
                          <th className="p-2.5">Input Value</th>
                          <th className="p-2.5">Data Source</th>
                          <th className="p-2.5">Status</th>
                          <th className="p-2.5">Reason &amp; Limitations</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {factorsAssessment.factors?.map((row: FactorAssessmentRow, idx: number) => {
                          const statusBadge =
                            row.status === 'satisfied' ? (
                              <Badge variant="outline" className="bg-emerald-950/60 text-emerald-400 border-emerald-500/40 text-[10px]">
                                Satisfied
                              </Badge>
                            ) : row.status === 'unmet' ? (
                              <Badge variant="outline" className="bg-rose-950/60 text-rose-300 border-rose-500/40 text-[10px]">
                                Unmet
                              </Badge>
                            ) : row.status === 'unknown' ? (
                              <Badge variant="outline" className="bg-amber-950/60 text-amber-300 border-amber-500/40 text-[10px]">
                                Unknown
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-muted-foreground border-border/50 text-[10px]">
                                N/A
                              </Badge>
                            )

                          return (
                            <tr key={idx} className="hover:bg-muted/20">
                              <td className="p-2.5 font-medium text-foreground">{row.factor_label || row.factor}</td>
                              <td className="p-2.5 font-mono text-[11px] text-muted-foreground">{row.input_value}</td>
                              <td className="p-2.5 text-muted-foreground text-[11px]">{row.data_source}</td>
                              <td className="p-2.5">{statusBadge}</td>
                              <td className="p-2.5 text-muted-foreground leading-relaxed text-[11px]">{row.reason_and_limitations}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Object-Level Explanations */}
                  {factorsAssessment.object_level_explanations && factorsAssessment.object_level_explanations.length > 0 && (
                    <div className="p-3 rounded-lg border border-border/40 bg-muted/10 space-y-1.5">
                      <span className="font-semibold text-muted-foreground block text-[11px]">Vegetation Suitability Insights:</span>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                        {factorsAssessment.object_level_explanations.slice(0, 6).map((obj, i: number) => (
                          <div key={i} className="p-1.5 rounded bg-background border border-border/40 font-mono text-[10px]">
                            <span className="font-semibold text-primary">{obj.json_id}: </span>
                            <span className="text-muted-foreground">{obj.suitability_explanation}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
