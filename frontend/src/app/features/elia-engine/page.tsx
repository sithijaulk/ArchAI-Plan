"use client"
import React, { useState, useEffect, useMemo, useRef, useSyncExternalStore, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { EliaOutputWrapper } from '@/components/visualization/EliaOutputWrapper'
import { useProjectStore } from '@/store/projectStore'
import { eliaApi } from '@/lib/api/elia'
import { extractNormalizedUpstreamGeometry } from '@/lib/eliaGeometry'
import { computeRequirementsFingerprint } from '@/lib/eliaSerialization'
import { EliaWorkflowController, EliaWorkflowState } from '@/lib/eliaWorkflowController'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
} from 'lucide-react'

export default function EliaEnginePage() {
  const router = useRouter()
  const { projectId, projectName, masterJson, setComponentStatus, setOutput } = useProjectStore()

  // Production state controller instance
  const controllerRef = useRef<EliaWorkflowController | null>(null)
  if (!controllerRef.current) {
    controllerRef.current = new EliaWorkflowController(projectId)
  }
  const controller = controllerRef.current

  // Synchronize with production workflow controller with stable server snapshot
  const state = useSyncExternalStore(
    useCallback((notify) => controller.subscribe(notify), [controller]),
    useCallback(() => controller.getState(), [controller]),
    useCallback(() => EliaWorkflowController.getServerSnapshot(), [])
  )

  // Local UI state for location search query input
  const [cityQuery, setCityQuery] = useState('')

  // Coherent project lifecycle: activation on mount/project change, deactivation on cleanup
  useEffect(() => {
    controller.activate(projectId)
    if (!projectId) {
      router.push('/start')
      return
    }

    controller.loadAuthoritativeContext(eliaApi)
    controller.loadLatestRun(eliaApi)

    return () => {
      controller.deactivate()
    }
  }, [projectId, controller, router])

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

  // Upstream Site View Model
  const displayMasterJson = state.activeView === 'candidate' && state.candidate?.sourceSnapshot
    ? state.candidate.sourceSnapshot
    : (state.authoritativeMaster || masterJson)

  const displayRevision = state.activeView === 'candidate'
    ? (state.candidate?.sourceRevision !== undefined ? state.candidate.sourceRevision : state.sourceRevision)
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

  if (!projectId) return null

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
                  <LoaderCircle className="w-3.5 h-3.5 mr-1.5 animate-spin" />
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

        {state.contextError && (
          <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-950/20 text-amber-200 text-xs flex items-center justify-between gap-2">
            <span>{state.contextError} (Displaying last confirmed state).</span>
            <Button
              size="sm"
              variant="outline"
              className="h-6 text-[11px]"
              onClick={() => controller.loadAuthoritativeContext(eliaApi)}
            >
              Retry
            </Button>
          </div>
        )}

        {state.latestRunError && (
          <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-950/20 text-rose-200 text-xs flex items-center justify-between gap-2">
            <span>Run History Warning: {state.latestRunError}</span>
            <Button
              size="sm"
              variant="outline"
              className="h-6 text-[11px]"
              onClick={() => controller.loadLatestRun(eliaApi)}
            >
              Retry
            </Button>
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
                    {projectName} · Authoritative upstream geometry
                  </p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-muted-foreground"
                  onClick={() => {
                    controller.loadAuthoritativeContext(eliaApi)
                    controller.loadLatestRun(eliaApi)
                  }}
                  disabled={state.isLoadingContext}
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
                        : 'Missing'}
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
                        : 'Missing'}
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
                <Tabs defaultValue="access" className="w-full">
                  <TabsList className="grid grid-cols-4 mb-4 text-xs">
                    <TabsTrigger value="access" className="text-xs py-1.5"><Car className="w-3.5 h-3.5 mr-1" /> Access</TabsTrigger>
                    <TabsTrigger value="garden" className="text-xs py-1.5"><Trees className="w-3.5 h-3.5 mr-1" /> Garden</TabsTrigger>
                    <TabsTrigger value="lighting" className="text-xs py-1.5"><Lightbulb className="w-3.5 h-3.5 mr-1" /> Lighting</TabsTrigger>
                    <TabsTrigger value="solar" className="text-xs py-1.5"><Sun className="w-3.5 h-3.5 mr-1" /> Solar</TabsTrigger>
                  </TabsList>

                  {/* TAB 1: ACCESS & PARKING */}
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
                            <Label htmlFor="garage-cap" className="text-xs text-muted-foreground">Garage Capacity (vehicles)</Label>
                            <Input
                              id="garage-cap"
                              type="number"
                              min={1}
                              max={3}
                              value={form.garageCapacity}
                              onChange={(e) => controller.editRequirement({ garageCapacity: e.target.value })}
                              className="mt-1 h-8 text-xs font-mono"
                            />
                            <span className="text-[10px] text-muted-foreground">Max 3 in baseline heuristic</span>
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
                            <div className="flex items-center justify-between">
                              <Label htmlFor="drive-style" className="text-xs text-muted-foreground">Driveway Style</Label>
                              <span className="text-[9px] text-muted-foreground font-mono">(Recorded pref)</span>
                            </div>
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
                            <span className="text-[10px] text-muted-foreground leading-tight block mt-0.5">
                              Baseline planner uses regulatory geometry path.
                            </span>
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

                  {/* TAB 2: GARDEN & LANDSCAPE */}
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
                        <div className="flex items-center justify-between">
                          <Label htmlFor="open-ratio" className="text-xs text-muted-foreground">Open Space Ratio</Label>
                          <span className="text-[9px] text-muted-foreground font-mono">(Recorded pref)</span>
                        </div>
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
                        <span className="text-[10px] text-muted-foreground leading-tight block mt-0.5">
                          Baseline maximizes ground clearance.
                        </span>
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

                  {/* TAB 3: LIGHTING & VERTICAL GREENERY */}
                  <TabsContent value="lighting" className="space-y-4">
                    {/* Outdoor Lighting */}
                    <div className="space-y-3 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="light-req" className="font-medium cursor-pointer">Outdoor Lighting Plan</Label>
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
                          <Label className="text-xs text-muted-foreground">Lighting Fixture Style</Label>
                          <select
                            value={form.lightingStyle}
                            onChange={(e) => controller.editRequirement({ lightingStyle: e.target.value })}
                            className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                          >
                            <option value="minimal">Minimal Bollards</option>
                            <option value="accent">Pathway & Tree Accent</option>
                            <option value="ambient">Ambient Perimeter</option>
                          </select>
                        </div>
                      )}
                    </div>

                    {/* Vertical Greenery */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label className="text-xs font-medium">Vertical Greenery Strategy</Label>
                      <select
                        value={form.verticalGreeneryMode}
                        onChange={(e) => controller.editRequirement({ verticalGreeneryMode: e.target.value as any })}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="automatic">Automatic (on tight plots)</option>
                        <option value="preferred">Always Preferred</option>
                        <option value="disabled">Disabled</option>
                      </select>
                      <p className="text-[11px] text-muted-foreground leading-tight pt-1">
                        Applied to external building walls or terraces when ground planting clearance is restricted. Requires upstream house geometry.
                      </p>
                    </div>

                    {/* Aesthetic Style & Truthful Disclosures */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label className="text-xs font-medium">Aesthetic Concept Label</Label>
                      <select
                        value={form.designStyle}
                        onChange={(e) => controller.editRequirement({ designStyle: e.target.value })}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="contemporary">Contemporary Living</option>
                        <option value="modern">Modern Minimalist</option>
                        <option value="tropical">Tropical Sri Lankan Modern</option>
                        <option value="traditional">Traditional Vernacular</option>
                      </select>
                      <div className="flex items-start gap-1.5 pt-1 text-[11px] text-muted-foreground leading-tight">
                        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-primary" />
                        <span>
                          Baseline planner applies regulatory geometry heuristics. The concept style is preserved in project metadata.
                        </span>
                      </div>
                    </div>
                  </TabsContent>

                  {/* TAB 4: SOLAR & LOCATION */}
                  <TabsContent value="solar" className="space-y-3">
                    <form onSubmit={handleLocationSearch} className="space-y-2">
                      <Label htmlFor="elia-city-search" className="text-xs">Search Sri Lankan Locality</Label>
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
                      <div className="max-h-36 overflow-y-auto space-y-1 rounded border border-border p-1 text-xs">
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

                    <div className="flex items-center justify-between p-2 rounded border border-border/40 text-xs">
                      <Label htmlFor="live-solar-toggle" className="cursor-pointer">Include Solar in Run</Label>
                      <input
                        id="live-solar-toggle"
                        type="checkbox"
                        checked={form.includeLiveSolar}
                        onChange={(e) => controller.editRequirement({ includeLiveSolar: e.target.checked })}
                        className="w-3.5 h-3.5 rounded text-primary"
                      />
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
                    disabled={state.isValidating || state.isPreviewing || state.isGenerating}
                  >
                    {state.isValidating ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                    Validate Inputs
                  </Button>

                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full text-xs h-9"
                    onClick={() => controller.previewCandidate(eliaApi)}
                    disabled={state.isPreviewing || state.isGenerating || state.isValidating}
                    title="Generate candidate proposal in memory without modifying database"
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
                    disabled={!controller.canGenerateAndSave()}
                    title={
                      state.requiresReconciliation
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
                  {state.requiresReconciliation && (
                    <p className="text-[10px] text-rose-400 text-center mt-1">
                      Project state must be reconciled before retrying save. Click &quot;Check Status &amp; Reconcile&quot; above.
                    </p>
                  )}
                  {!state.requiresReconciliation && (state.sourceRevision === null || state.sourceRevision === undefined || state.contextFreshness !== 'current') && (
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

          {/* RIGHT COLUMN: Three.js 3D Viewer & 2D Plan View (7 cols) */}
          <div className="lg:col-span-7">
            <EliaOutputWrapper
              projectName={projectName}
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
            />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
