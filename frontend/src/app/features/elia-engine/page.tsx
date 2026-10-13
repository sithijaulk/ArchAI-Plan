"use client"
import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { EliaOutputWrapper } from '@/components/visualization/EliaOutputWrapper'
import { useProjectStore } from '@/store/projectStore'
import { eliaApi, LiveSolarConditions, SriLankaLocation } from '@/lib/api/elia'
import type {
  ELIARequirements,
  ExteriorLandscape,
  ELIAValidationResponse,
  ELIAResultResponse,
} from '@/types/elia'
import { extractNormalizedUpstreamGeometry } from '@/lib/eliaGeometry'
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
  const { projectId, projectName, masterJson, setComponentStatus, setOutput, outputs } = useProjectStore()

  // ---------------------------------------------------------------------------
  // 1. Authoritative Backend Context & Revision State
  // ---------------------------------------------------------------------------
  const [authoritativeMaster, setAuthoritativeMaster] = useState<any>(masterJson || null)
  const [sourceRevision, setSourceRevision] = useState<number | null>(null)
  const [isLoadingContext, setIsLoadingContext] = useState(false)
  const [contextError, setContextError] = useState<string | null>(null)

  // ---------------------------------------------------------------------------
  // 2. Candidate vs Accepted Design State
  // ---------------------------------------------------------------------------
  const [acceptedLandscape, setAcceptedLandscape] = useState<ExteriorLandscape | null>(null)
  const [candidateLandscape, setCandidateLandscape] = useState<ExteriorLandscape | null>(null)
  const [activeView, setActiveView] = useState<'candidate' | 'accepted'>('accepted')
  const [viewStatus, setViewStatus] = useState<'accepted' | 'preview' | 'infeasible'>('accepted')
  const [latestRun, setLatestRun] = useState<ELIAResultResponse | null>(null)
  const [isCheckingRun, setIsCheckingRun] = useState(false)

  // ---------------------------------------------------------------------------
  // 3. Operational Action States
  // ---------------------------------------------------------------------------
  const [isValidating, setIsValidating] = useState(false)
  const [validationResult, setValidationResult] = useState<ELIAValidationResponse | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

  const [isPreviewing, setIsPreviewing] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [requirementsDirty, setRequirementsDirty] = useState(false)

  // ---------------------------------------------------------------------------
  // 4. Requirements Form State
  // ---------------------------------------------------------------------------
  const [generationMode, setGenerationMode] = useState<'baseline' | 'trained_model'>('baseline')
  const [designStyle, setDesignStyle] = useState('contemporary')
  const [greeneryDensity, setGreeneryDensity] = useState<'low' | 'medium' | 'high'>('medium')
  const [openSpaceRatio, setOpenSpaceRatio] = useState(0.3)
  const [shadeTreePreference, setShadeTreePreference] = useState(false)

  // Parking & Access
  const [garageRequired, setGarageRequired] = useState(false)
  const [garageCapacity, setGarageCapacity] = useState(1)
  const [vehicleCount, setVehicleCount] = useState(1)
  const [drivewayRequired, setDrivewayRequired] = useState(true)
  const [drivewayStyle, setDrivewayStyle] = useState('auto')
  const [turningSpaceRequired, setTurningSpaceRequired] = useState(true)
  const [gateType, setGateType] = useState('unspecified')
  const [gateWidthM, setGateWidthM] = useState(3.6)

  // Garden & Outdoor Living
  const [gardenRequired, setGardenRequired] = useState(true)
  const [lawnRequired, setLawnRequired] = useState(false)
  const [gardenSeatingRequired, setGardenSeatingRequired] = useState(false)
  const [gardenTableSetRequired, setGardenTableSetRequired] = useState(false)
  const [pedestrianPathRequired, setPedestrianPathRequired] = useState(false)
  const [gardenPathRequired, setGardenPathRequired] = useState(false)
  const [boundaryWallRequired, setBoundaryWallRequired] = useState(false)
  const [boundaryWallType, setBoundaryWallType] = useState('masonry')
  const [boundaryWallHeightM, setBoundaryWallHeightM] = useState(1.8)

  // Lighting & Vertical Greenery
  const [lightingRequired, setLightingRequired] = useState(false)
  const [lightingStyle, setLightingStyle] = useState('minimal')
  const [verticalGreeneryMode, setVerticalGreeneryMode] = useState<'automatic' | 'preferred' | 'disabled'>('automatic')

  // Solar & Location
  const [cityQuery, setCityQuery] = useState('')
  const [locations, setLocations] = useState<SriLankaLocation[]>([])
  const [selectedLocation, setSelectedLocation] = useState<SriLankaLocation | null>(null)
  const [solar, setSolar] = useState<LiveSolarConditions | null>(null)
  const [includeLiveSolar, setIncludeLiveSolar] = useState(false)
  const [isSearchingLocation, setIsSearchingLocation] = useState(false)
  const [isLoadingSolar, setIsLoadingSolar] = useState(false)
  const [locationError, setLocationError] = useState('')

  // ---------------------------------------------------------------------------
  // 5. Lifecycle & Routing
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!projectId) {
      router.push('/start')
    }
  }, [projectId, router])

  // Fetch authoritative context on load
  const loadAuthoritativeContext = useCallback(async () => {
    if (!projectId) return
    setIsLoadingContext(true)
    setContextError(null)
    setConflictError(null)
    try {
      const response = await eliaApi.getContext(projectId)
      const doc = response.master_json || masterJson
      setAuthoritativeMaster(doc)
      if (response.revision !== undefined && response.revision !== null) {
        setSourceRevision(response.revision)
      } else if (doc && typeof (doc as Record<string, any>).revision === 'number') {
        setSourceRevision((doc as Record<string, any>).revision)
      }

      // Check for accepted exterior in Master JSON
      const existingExterior = ((doc as Record<string, any>)?.exterior_landscape || outputs['elia_engine']) as ExteriorLandscape | null
      if (existingExterior && existingExterior.access) {
        setAcceptedLandscape(existingExterior)
        if (!candidateLandscape) {
          setActiveView('accepted')
          setViewStatus('accepted')
        }
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Could not load project context.'
      setContextError(`Context fetch notice: ${typeof msg === 'object' ? JSON.stringify(msg) : msg}`)
      if (masterJson) {
        setAuthoritativeMaster(masterJson)
        if (typeof (masterJson as Record<string, any>).revision === 'number') {
          setSourceRevision((masterJson as Record<string, any>).revision)
        }
      }
    } finally {
      setIsLoadingContext(false)
    }
  }, [projectId, masterJson, outputs, candidateLandscape])

  // Check latest run from backend
  const loadLatestRun = useCallback(async () => {
    if (!projectId) return
    setIsCheckingRun(true)
    try {
      const run = await eliaApi.getResult(projectId)
      setLatestRun(run)
    } catch {
      // 404 is normal if no run has occurred yet
      setLatestRun(null)
    } finally {
      setIsCheckingRun(false)
    }
  }, [projectId])

  useEffect(() => {
    if (projectId) {
      loadAuthoritativeContext()
      loadLatestRun()
    }
  }, [projectId, loadAuthoritativeContext, loadLatestRun])

  // Derive normalized upstream site geometry info
  const siteViewModel = useMemo(() => {
    return extractNormalizedUpstreamGeometry(authoritativeMaster || masterJson, null, projectId || undefined)
  }, [authoritativeMaster, masterJson, projectId])

  // ---------------------------------------------------------------------------
  // 6. Request Payload Serialization
  // ---------------------------------------------------------------------------
  const buildSerializedRequirements = useCallback((): ELIARequirements => {
    const req: ELIARequirements = {
      units: 'm',
      design_style: designStyle,
      greenery_level: greeneryDensity,
      landscape_priority: 'balanced',
      vertical_greenery_enabled: verticalGreeneryMode !== 'disabled',
      include_live_solar: includeLiveSolar,
      access: {
        gate_type: gateType,
        gate_width_m: gateWidthM,
        garage_required: garageRequired,
        driveway_required: drivewayRequired,
        turning_space_required: turningSpaceRequired,
      },
      landscape: {
        garden_required: gardenRequired,
        lawn_required: lawnRequired,
        greenery_density: greeneryDensity,
        preferred_open_space_ratio: openSpaceRatio,
        shade_tree_preference: shadeTreePreference,
        garden_seating_required: gardenSeatingRequired,
        garden_table_set_required: gardenTableSetRequired,
        pedestrian_path_required: pedestrianPathRequired,
        garden_path_required: gardenPathRequired,
        boundary_wall_required: boundaryWallRequired,
      },
      vertical_greenery: {
        mode: verticalGreeneryMode,
        enabled: verticalGreeneryMode !== 'disabled',
      },
      lighting: {
        required: lightingRequired,
        style: lightingStyle,
        preferred_spacing_m: 8.0,
      },
    }

    // Only send garage details when garage is required
    if (garageRequired) {
      req.access!.garage_capacity = garageCapacity
      req.access!.vehicle_count = vehicleCount
    }

    // Only send driveway details when driveway is required
    if (drivewayRequired) {
      req.access!.driveway_style = drivewayStyle
    }

    // Only send wall details when boundary wall is required
    if (boundaryWallRequired) {
      req.landscape!.boundary_wall_type = boundaryWallType
      req.landscape!.boundary_wall_height_m = boundaryWallHeightM
    }

    // Attach location coordinates only when both latitude and longitude exist
    if (selectedLocation) {
      req.location = {
        latitude: selectedLocation.latitude,
        longitude: selectedLocation.longitude,
        timezone: selectedLocation.timezone || null,
        city: selectedLocation.name,
      }
      req.latitude = selectedLocation.latitude
      req.longitude = selectedLocation.longitude
      req.timezone = selectedLocation.timezone || null
    }

    return req
  }, [
    designStyle,
    greeneryDensity,
    openSpaceRatio,
    shadeTreePreference,
    verticalGreeneryMode,
    includeLiveSolar,
    garageRequired,
    garageCapacity,
    vehicleCount,
    drivewayRequired,
    drivewayStyle,
    turningSpaceRequired,
    gateType,
    gateWidthM,
    gardenRequired,
    lawnRequired,
    gardenSeatingRequired,
    gardenTableSetRequired,
    pedestrianPathRequired,
    gardenPathRequired,
    boundaryWallRequired,
    boundaryWallType,
    boundaryWallHeightM,
    lightingRequired,
    lightingStyle,
    selectedLocation,
  ])

  // Track requirement edits
  const onRequirementChange = () => {
    setRequirementsDirty(true)
    setValidationError(null)
    setActionError(null)
  }

  // ---------------------------------------------------------------------------
  // 7. Operational Actions
  // ---------------------------------------------------------------------------

  // Action A: Validate Requirements
  const handleValidateRequirements = async () => {
    if (!projectId) return
    setIsValidating(true)
    setValidationError(null)
    setValidationResult(null)
    try {
      const requirements = buildSerializedRequirements()
      const response = await eliaApi.validateInput(projectId, {
        requirements,
        master_json: authoritativeMaster,
        source_revision: sourceRevision,
        generation_mode: generationMode,
      })
      setValidationResult(response)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'object' ? `${detail.code}: ${detail.message}` : (detail || err.message || 'Validation failed.')
      setValidationError(msg)
    } finally {
      setIsValidating(false)
    }
  }

  // Action B: Preview Candidate (Unsaved, Non-Destructive)
  const handlePreviewCandidate = async () => {
    if (!projectId || !authoritativeMaster) return
    setIsPreviewing(true)
    setActionError(null)
    setConflictError(null)
    try {
      const requirements = buildSerializedRequirements()
      const response = await eliaApi.preview({
        master_json: authoritativeMaster,
        requirements,
        generation_mode: generationMode,
        source_revision: sourceRevision,
      })

      setCandidateLandscape(response.exterior_landscape)
      setActiveView('candidate')
      setViewStatus(response.outcome === 'valid' ? 'preview' : 'infeasible')
      setRequirementsDirty(false)

      if (response.outcome === 'infeasible') {
        const reason = response.exterior_landscape?.validation_summary?.violations?.join('; ') || 'Candidate layout is infeasible under site boundary constraints.'
        setActionError(`Infeasible Candidate: ${reason}`)
      }
    } catch (err: any) {
      handleApiError(err, 'Preview generation failed.')
    } finally {
      setIsPreviewing(false)
    }
  }

  // Action C: Generate & Save (Mutating, CAS-Protected)
  const handleGenerateAndSave = async () => {
    if (!projectId) return
    setIsGenerating(true)
    setActionError(null)
    setConflictError(null)
    try {
      const requirements = buildSerializedRequirements()
      const response = await eliaApi.run(projectId, {
        requirements,
        generation_mode: generationMode,
        apply_to_project: true,
        source_revision: sourceRevision,
      })

      setCandidateLandscape(response.exterior_landscape)
      setRequirementsDirty(false)

      if (response.outcome === 'valid') {
        setAcceptedLandscape(response.exterior_landscape)
        setActiveView('accepted')
        setViewStatus('accepted')
        setOutput('elia_engine', response.exterior_landscape)
        setComponentStatus('elia_engine', 'completed')
        // Refresh authoritative context to update revision
        await loadAuthoritativeContext()
        await loadLatestRun()
      } else {
        // Infeasible: preserved earlier accepted exterior!
        setActiveView('candidate')
        setViewStatus('infeasible')
        const violations = response.exterior_landscape?.validation_summary?.violations?.join('; ') || 'Site boundary constraints could not be satisfied.'
        setActionError(`Infeasible Run: ${violations} (Previously accepted design preserved).`)
        await loadLatestRun()
      }
    } catch (err: any) {
      handleApiError(err, 'Exterior layout generation failed.')
      setComponentStatus('elia_engine', 'failed')
    } finally {
      setIsGenerating(false)
    }
  }

  // Centralized Error Parser (Handles 409 Conflict, 503 Model Unavailable, and Network/DB errors)
  const handleApiError = (err: any, fallbackMessage: string) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail

    if (status === 409) {
      // Stale revision CAS conflict
      const currentRev = detail?.current_revision || 'newer'
      setConflictError(
        `Revision Conflict (409): The project was modified concurrently (current revision is ${currentRev}). Your requirements form has been preserved. Please refresh context and regenerate.`
      )
      loadAuthoritativeContext()
      return
    }

    if (status === 503) {
      // Trained model unavailable without fallback
      const code = typeof detail === 'object' ? detail.code : ''
      const msg = typeof detail === 'object' ? detail.message : detail
      setActionError(
        `${code || 'ELIA_MODEL_UNAVAILABLE'}: ${msg || 'The trained exterior AI model is not registered on this backend. Use the Baseline Heuristic Generator.'}`
      )
      return
    }

    if (status === 401 || status === 403) {
      setActionError('Authentication required: Admin credentials or valid session needed for ELIA engine.')
      return
    }

    if (status === 500) {
      const msg = typeof detail === 'object' ? `${detail.code || 'ERROR'}: ${detail.message}` : (detail || fallbackMessage)
      setActionError(`Backend Processing Error (500): ${msg}. Check database and backend server status.`)
      return
    }

    const msg = typeof detail === 'object' ? `${detail.code}: ${detail.message}` : (detail || err.message || fallbackMessage)
    setActionError(msg)
  }

  // Location search handlers
  const handleLocationSearch = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (cityQuery.trim().length < 2) return
    setIsSearchingLocation(true)
    setLocationError('')
    setSelectedLocation(null)
    setSolar(null)
    try {
      const response = await eliaApi.searchLocations(cityQuery.trim())
      setLocations(response.results)
      if (response.results.length === 0) setLocationError('No matching Sri Lankan locations found.')
    } catch {
      setLocations([])
      setLocationError('Location search is unavailable. Please try again.')
    } finally {
      setIsSearchingLocation(false)
    }
  }

  const handleSolarLookup = async () => {
    if (!selectedLocation || !projectId) return
    setIsLoadingSolar(true)
    setLocationError('')
    try {
      const data = await eliaApi.currentSolar(projectId, selectedLocation)
      setSolar(data)
    } catch {
      setSolar(null)
      setLocationError('Current solar conditions could not be loaded from weather API.')
    } finally {
      setIsLoadingSolar(false)
    }
  }

  // Currently displayed exterior data
  const displayedExterior = activeView === 'accepted' ? acceptedLandscape : candidateLandscape

  if (!projectId) return null

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
        {conflictError && (
          <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-950/20 text-amber-200 text-sm flex items-start justify-between gap-3 shadow-sm">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-amber-300">Stale Project Revision</div>
                <p className="mt-0.5 leading-relaxed">{conflictError}</p>
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="border-amber-500/40 text-amber-200 shrink-0"
              onClick={loadAuthoritativeContext}
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh Context
            </Button>
          </div>
        )}

        {actionError && (
          <div className="p-4 rounded-xl border border-rose-500/40 bg-rose-950/20 text-rose-200 text-sm flex items-start gap-2.5 shadow-sm">
            <XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-semibold text-rose-300">Operation Notice</div>
              <p className="mt-0.5 leading-relaxed">{actionError}</p>
            </div>
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
                  onClick={loadAuthoritativeContext}
                  disabled={isLoadingContext}
                  title="Reload authoritative project context"
                >
                  <RefreshCw className={`w-4 h-4 ${isLoadingContext ? 'animate-spin' : ''}`} />
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
                      {sourceRevision ?? '1'}
                    </span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      CAS concurrency key
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg border border-border/50 bg-muted/30">
                    <span className="text-muted-foreground block text-[11px]">Accepted Exterior</span>
                    <span className="font-semibold font-mono text-foreground text-sm">
                      {acceptedLandscape ? 'Persisted' : 'None yet'}
                    </span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      In Master JSON
                    </span>
                  </div>
                </div>

                {siteViewModel.geometryState !== 'ready' && (
                  <div className="p-2.5 rounded-md border border-amber-500/30 bg-amber-950/20 text-amber-200 text-xs">
                    {siteViewModel.geometryMessage || 'Upstream site geometry required from Components 1-3.'}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 2. Client Requirements Form Tabs */}
            <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
              <CardHeader className="pb-3 pt-4 px-5 border-b border-border/40">
                <CardTitle className="text-base font-semibold flex items-center justify-between">
                  <span>Client Requirements</span>
                  <Badge variant="outline" className="text-[10px] font-mono">
                    Units: meters
                  </Badge>
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
                          checked={garageRequired}
                          onChange={(e) => { setGarageRequired(e.target.checked); onRequirementChange() }}
                          className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                        />
                      </div>

                      {garageRequired && (
                        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/30">
                          <div>
                            <Label htmlFor="garage-cap" className="text-xs text-muted-foreground">Garage Capacity (vehicles)</Label>
                            <Input
                              id="garage-cap"
                              type="number"
                              min={1}
                              max={3}
                              value={garageCapacity}
                              onChange={(e) => { setGarageCapacity(Math.min(3, Math.max(1, parseInt(e.target.value) || 1))); onRequirementChange() }}
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
                              value={vehicleCount}
                              onChange={(e) => { setVehicleCount(Math.min(3, Math.max(1, parseInt(e.target.value) || 1))); onRequirementChange() }}
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
                          checked={drivewayRequired}
                          onChange={(e) => { setDrivewayRequired(e.target.checked); onRequirementChange() }}
                          className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                        />
                      </div>

                      {drivewayRequired && (
                        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/30">
                          <div>
                            <Label htmlFor="drive-style" className="text-xs text-muted-foreground">Driveway Style</Label>
                            <select
                              id="drive-style"
                              value={drivewayStyle}
                              onChange={(e) => { setDrivewayStyle(e.target.value); onRequirementChange() }}
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
                                checked={turningSpaceRequired}
                                onChange={(e) => { setTurningSpaceRequired(e.target.checked); onRequirementChange() }}
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
                          value={gateType}
                          onChange={(e) => { setGateType(e.target.value); onRequirementChange() }}
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
                          value={gateWidthM}
                          onChange={(e) => { setGateWidthM(parseFloat(e.target.value) || 3.6); onRequirementChange() }}
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
                          value={greeneryDensity}
                          onChange={(e) => { setGreeneryDensity(e.target.value as any); onRequirementChange() }}
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
                          value={openSpaceRatio}
                          onChange={(e) => { setOpenSpaceRatio(parseFloat(e.target.value) || 0.3); onRequirementChange() }}
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
                            checked={gardenRequired}
                            onChange={(e) => { setGardenRequired(e.target.checked); onRequirementChange() }}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Planting Beds</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={lawnRequired}
                            onChange={(e) => { setLawnRequired(e.target.checked); onRequirementChange() }}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Turf / Lawn</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={shadeTreePreference}
                            onChange={(e) => { setShadeTreePreference(e.target.checked); onRequirementChange() }}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Shade Canopy Trees</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={gardenSeatingRequired}
                            onChange={(e) => { setGardenSeatingRequired(e.target.checked); onRequirementChange() }}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Outdoor Seating</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={gardenTableSetRequired}
                            onChange={(e) => { setGardenTableSetRequired(e.target.checked); onRequirementChange() }}
                            className="w-3.5 h-3.5 rounded text-primary"
                          />
                          <span>Garden Dining Set</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={pedestrianPathRequired}
                            onChange={(e) => { setPedestrianPathRequired(e.target.checked); onRequirementChange() }}
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
                          checked={boundaryWallRequired}
                          onChange={(e) => { setBoundaryWallRequired(e.target.checked); onRequirementChange() }}
                          className="w-3.5 h-3.5 rounded text-primary"
                        />
                      </div>
                      {boundaryWallRequired && (
                        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border/30">
                          <div>
                            <Label className="text-[11px] text-muted-foreground">Wall Type</Label>
                            <select
                              value={boundaryWallType}
                              onChange={(e) => { setBoundaryWallType(e.target.value); onRequirementChange() }}
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
                              value={boundaryWallHeightM}
                              onChange={(e) => { setBoundaryWallHeightM(parseFloat(e.target.value) || 1.8); onRequirementChange() }}
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
                          checked={lightingRequired}
                          onChange={(e) => { setLightingRequired(e.target.checked); onRequirementChange() }}
                          className="w-4 h-4 rounded text-primary"
                        />
                      </div>
                      {lightingRequired && (
                        <div className="pt-2 border-t border-border/30">
                          <Label className="text-xs text-muted-foreground">Lighting Fixture Style</Label>
                          <select
                            value={lightingStyle}
                            onChange={(e) => { setLightingStyle(e.target.value); onRequirementChange() }}
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
                      <Label className="text-xs font-medium">Vertical Greenery Fallback</Label>
                      <select
                        value={verticalGreeneryMode}
                        onChange={(e) => { setVerticalGreeneryMode(e.target.value as any); onRequirementChange() }}
                        className="mt-1 w-full h-8 rounded-md border border-input bg-background px-2 text-xs"
                      >
                        <option value="automatic">Automatic (on tight plots)</option>
                        <option value="preferred">Always Preferred</option>
                        <option value="disabled">Disabled</option>
                      </select>
                      <p className="text-[11px] text-muted-foreground leading-tight pt-1">
                        Utilizes external building walls or terraces when ground planting clearance is restricted.
                      </p>
                    </div>

                    {/* Architectural Style & Truthful Disclosures */}
                    <div className="space-y-2 p-3 rounded-lg border border-border/40 bg-muted/20">
                      <Label className="text-xs font-medium">Aesthetic Concept Label</Label>
                      <select
                        value={designStyle}
                        onChange={(e) => { setDesignStyle(e.target.value); onRequirementChange() }}
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
                          Baseline planner applies regulatory geometry heuristics. The style label is preserved in metadata.
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
                          disabled={isSearchingLocation || cityQuery.trim().length < 2}
                          className="h-8 px-2.5"
                        >
                          {isSearchingLocation ? <LoaderCircle className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                        </Button>
                      </div>
                    </form>

                    {locations.length > 0 && (
                      <div className="max-h-36 overflow-y-auto space-y-1 rounded border border-border p-1 text-xs">
                        {locations.map((loc) => (
                          <button
                            key={loc.id}
                            type="button"
                            onClick={() => { setSelectedLocation(loc); setSolar(null); setLocationError('') }}
                            className={`w-full text-left p-1.5 rounded transition-colors ${selectedLocation?.id === loc.id ? 'bg-primary/20 text-primary font-medium' : 'hover:bg-muted'}`}
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

                    {selectedLocation && (
                      <div className="p-2.5 rounded-lg border border-border/50 bg-muted/30 space-y-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-primary">{selectedLocation.name}</span>
                          <span className="text-[10px] font-mono text-muted-foreground">
                            {selectedLocation.latitude.toFixed(4)}, {selectedLocation.longitude.toFixed(4)}
                          </span>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="w-full h-7 text-xs"
                          onClick={handleSolarLookup}
                          disabled={isLoadingSolar}
                        >
                          {isLoadingSolar ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1" /> : <Sun className="w-3.5 h-3.5 mr-1" />}
                          Load Live Solar Irradiance
                        </Button>
                      </div>
                    )}

                    {solar && (
                      <div className="p-2.5 rounded-lg border border-border/50 bg-muted/40 space-y-1.5 text-xs">
                        <div className="flex items-center justify-between font-medium">
                          <span>Solar Irradiance (GHI)</span>
                          <span className="font-mono text-primary">{solar.irradiance_w_m2.shortwave_radiation ?? '—'} W/m²</span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                          <span>Sun Elevation / Azimuth</span>
                          <span>{solar.solar_position.elevation_degrees.toFixed(1)}° / {solar.solar_position.azimuth_degrees.toFixed(1)}°</span>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between p-2 rounded border border-border/40 text-xs">
                      <Label htmlFor="live-solar-toggle" className="cursor-pointer">Include Solar in Run</Label>
                      <input
                        id="live-solar-toggle"
                        type="checkbox"
                        checked={includeLiveSolar}
                        onChange={(e) => { setIncludeLiveSolar(e.target.checked); onRequirementChange() }}
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
                      onClick={() => setGenerationMode('baseline')}
                      className={`p-2.5 rounded-lg border text-left text-xs transition-colors ${generationMode === 'baseline' ? 'border-primary bg-primary/10 text-primary' : 'border-border/60 hover:bg-muted/40'}`}
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
                      onClick={() => setGenerationMode('trained_model')}
                      className={`p-2.5 rounded-lg border text-left text-xs transition-colors ${generationMode === 'trained_model' ? 'border-amber-500 bg-amber-950/20 text-amber-300' : 'border-border/60 hover:bg-muted/40'}`}
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

                {generationMode === 'trained_model' && (
                  <div className="p-2.5 rounded border border-amber-500/30 bg-amber-950/20 text-amber-200 text-[11px] leading-tight">
                    Model adapter not yet registered on this backend. Requesting this mode triggers explicit 503 response without fallback.
                  </div>
                )}

                {/* Validation Response Summary Banner */}
                {validationResult && (
                  <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-950/20 text-emerald-200 text-xs space-y-1">
                    <div className="font-semibold flex items-center gap-1.5 text-emerald-300">
                      <CheckCircle2 className="w-4 h-4" /> Requirements Validated
                    </div>
                    <div className="grid grid-cols-2 gap-1 text-[11px] pt-1 font-mono">
                      <span>Land Area: {validationResult.geometry.land_area_m2.toFixed(1)} m²</span>
                      <span>House Footprint: {validationResult.geometry.house_footprint_area_m2.toFixed(1)} m²</span>
                      <span>North: {validationResult.orientation.north_angle_degrees.toFixed(1)}°</span>
                      <span>Units: {validationResult.geometry.source_units}</span>
                    </div>
                  </div>
                )}

                {validationError && (
                  <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-950/20 text-rose-200 text-xs">
                    <div className="font-semibold text-rose-300">Validation Notice</div>
                    <p className="mt-0.5">{validationError}</p>
                  </div>
                )}

                {/* Main Action Buttons */}
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full text-xs h-9"
                    onClick={handleValidateRequirements}
                    disabled={isValidating || isPreviewing || isGenerating}
                  >
                    {isValidating ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                    Validate Inputs
                  </Button>

                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full text-xs h-9"
                    onClick={handlePreviewCandidate}
                    disabled={isPreviewing || isGenerating || isValidating}
                    title="Generate candidate proposal in memory without modifying database"
                  >
                    {isPreviewing ? <LoaderCircle className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Eye className="w-3.5 h-3.5 mr-1.5" />}
                    Preview (Unsaved)
                  </Button>
                </div>

                <Button
                  type="button"
                  className="w-full electric-glow h-10 text-sm font-semibold"
                  onClick={handleGenerateAndSave}
                  disabled={isGenerating || isPreviewing || isValidating}
                  title="Generate candidate and persist accepted result to project Master JSON"
                >
                  {isGenerating ? (
                    <span className="flex items-center gap-2">
                      <LoaderCircle className="w-4 h-4 animate-spin" /> Persisting Exterior Spatial Plan...
                    </span>
                  ) : (
                    'Generate & Save Landscape'
                  )}
                </Button>

                {/* Latest Run Inspector Card */}
                {latestRun && (
                  <div className="pt-2 border-t border-border/40 text-[11px] text-muted-foreground flex items-center justify-between">
                    <span className="flex items-center gap-1 font-mono">
                      <History className="w-3 h-3" /> Run {latestRun.run_id.slice(0, 8)}: {latestRun.status}
                    </span>
                    <time className="text-[10px]">
                      {latestRun.completed_at ? new Date(latestRun.completed_at).toLocaleTimeString() : ''}
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
              projectId={projectId}
              masterJson={authoritativeMaster || masterJson}
              data={displayedExterior}
              isProcessing={isGenerating || isPreviewing}
              runError={actionError || undefined}
              viewStatus={viewStatus}
              sourceRevision={sourceRevision}
              generationMode={generationMode}
              acceptedData={acceptedLandscape}
              activeView={activeView}
              onToggleView={(view) => {
                setActiveView(view)
                setViewStatus(view === 'accepted' ? 'accepted' : 'preview')
              }}
              validationSummary={displayedExterior?.validation_summary}
            />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
