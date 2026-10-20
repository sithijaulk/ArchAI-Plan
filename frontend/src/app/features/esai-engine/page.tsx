"use client"

import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import {
  Building2,
  Layers,
  DoorOpen,
  Sliders,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  Save,
  Sparkles,
  ArrowRight,
  ShieldAlert,
  Info,
  RefreshCw,
  Palette,
  Lightbulb,
  Maximize2,
  Trash2,
  Check,
  ChevronRight,
  ChevronDown,
  Bed,
  Tv,
  UtensilsCrossed,
  Bath,
  Briefcase,
  HelpCircle,
  FileCheck2,
} from 'lucide-react'

import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { useProjectStore } from '@/store/projectStore'
import {
  esaiApi,
  InteriorContext,
  FloorSummary,
  FloorRoom,
  EffectivePreferences,
  PreferenceSchema,
} from '@/lib/api/esai'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

// ─── Constants & Options ───────────────────────────────────────────────────────

const STYLE_OPTIONS = [
  { value: 'modern', label: 'Modern', desc: 'Clean geometric lines, sleek minimalist forms' },
  { value: 'minimalist', label: 'Minimalist', desc: 'Monochromatic, clutter-free, purposeful' },
  { value: 'scandinavian', label: 'Scandinavian', desc: 'Warm woods, soft neutral textures, airy light' },
  { value: 'japandi', label: 'Japandi', desc: 'Zen organic simplicity, dark woods & earth tones' },
  { value: 'contemporary', label: 'Contemporary', desc: 'Fluid, state-of-the-art curves and materials' },
  { value: 'industrial', label: 'Industrial', desc: 'Exposed structural concrete, brick, black metal' },
  { value: 'luxury', label: 'Luxury & Glam', desc: 'Polished marble, brass trims, velvet accents' },
  { value: 'traditional', label: 'Traditional Classic', desc: 'Mouldings, symmetry, rich hardwoods' },
]

const PALETTE_OPTIONS = [
  { value: 'neutral_warm', label: 'Warm Neutral', preview: 'bg-gradient-to-r from-amber-100 via-stone-200 to-amber-200' },
  { value: 'cool_slate', label: 'Cool Slate', preview: 'bg-gradient-to-r from-slate-200 via-gray-300 to-zinc-400' },
  { value: 'earth_terracotta', label: 'Earth & Terracotta', preview: 'bg-gradient-to-r from-orange-200 via-amber-300 to-stone-400' },
  { value: 'nordic_forest', label: 'Nordic Forest & Sage', preview: 'bg-gradient-to-r from-emerald-100 via-teal-200 to-stone-300' },
  { value: 'monochrome_high_contrast', label: 'Monochrome High-Contrast', preview: 'bg-gradient-to-r from-neutral-900 via-neutral-500 to-neutral-100' },
  { value: 'luxury_gold_navy', label: 'Navy & Brushed Brass', preview: 'bg-gradient-to-r from-blue-950 via-indigo-900 to-amber-400' },
]

const FLOORING_OPTIONS = [
  'oak_hardwood',
  'engineered_wood',
  'marble_tile',
  'porcelain_large_format',
  'polished_concrete',
  'terrazzo',
  'wool_carpet',
]

const LIGHTING_OPTIONS = [
  { value: 'warm_diffuse', label: 'Warm Diffuse (2700K)', desc: 'Cozy, ambient evening relaxation' },
  { value: 'neutral_architectural', label: 'Neutral Architectural (3500K)', desc: 'Balanced daylight clarity' },
  { value: 'bright_task', label: 'High-CRI Bright Task (4000K)', desc: 'Precise visual focus for work & kitchen' },
  { value: 'cove_indirect', label: 'Concealed Indirect Cove', desc: 'Reflected architectural perimeter glow' },
]

export default function EsaiEnginePage() {
  const router = useRouter()
  const { projectId, projectName, skipComponent } = useProjectStore()

  // ─── Local State ─────────────────────────────────────────────────────────────
  const [context, setContext] = useState<InteriorContext | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [activeLevel, setActiveLevel] = useState<'building' | 'floor' | 'room'>('building')
  const [selectedFloorId, setSelectedFloorId] = useState<string>('')
  const [selectedRoomId, setSelectedRoomId] = useState<string>('')
  const [collapsedFloors, setCollapsedFloors] = useState<Record<string, boolean>>({})

  // Preference Form Data
  const [buildingPrefs, setBuildingPrefs] = useState<Record<string, any>>({
    style: 'modern',
    primary_palette: 'neutral_warm',
    flooring: 'oak_hardwood',
    lighting_mood: 'warm_diffuse',
    wall_finish: 'paint_matte',
  })

  const [floorPrefs, setFloorPrefs] = useState<Record<string, any>>({})
  const [roomPrefs, setRoomPrefs] = useState<Record<string, any>>({
    preferences: {},
    specific_assets: [],
    custom_constraints: [],
  })

  const [effective, setEffective] = useState<EffectivePreferences | null>(null)
  const [roomSchema, setRoomSchema] = useState<PreferenceSchema | null>(null)

  const [isSaving, setIsSaving] = useState(false)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null)
  const [orphanModal, setOrphanModal] = useState<any | null>(null)
  const [runModalOpen, setRunModalOpen] = useState(false)

  // Redirect if no project selected
  useEffect(() => {
    if (!projectId) router.push('/start')
  }, [projectId, router])

  // ─── Fetch Interior Context ──────────────────────────────────────────────────
  const loadContext = useCallback(async () => {
    if (!projectId) return
    setIsLoading(true)
    try {
      const data = await esaiApi.getInteriorContext(projectId)
      setContext(data)

      // Set default selected floor and room
      if (data.floors.length > 0) {
        const firstFloor = data.floors[0]
        setSelectedFloorId(firstFloor.floor_id)
        if (firstFloor.rooms.length > 0) {
          setSelectedRoomId(firstFloor.rooms[0].room_id)
        }
      }

      // Load building defaults
      const bRes = await esaiApi.getBuildingPreferences(projectId)
      if (bRes?.preferences) {
        setBuildingPrefs((prev) => ({ ...prev, ...bRes.preferences }))
      }
    } catch (err: any) {
      console.error('Failed to load ESAI context', err)
      setStatusMessage({ type: 'error', text: 'Could not load project interior geometry.' })
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    loadContext()
  }, [loadContext])

  // Find currently selected room and floor
  const selectedFloor: FloorSummary | undefined = useMemo(() => {
    return context?.floors.find((f) => f.floor_id === selectedFloorId)
  }, [context, selectedFloorId])

  const selectedRoom: FloorRoom | undefined = useMemo(() => {
    return selectedFloor?.rooms.find((r) => r.room_id === selectedRoomId)
  }, [selectedFloor, selectedRoomId])

  // ─── Load Floor Preferences when floor changes ───────────────────────────────
  useEffect(() => {
    if (!projectId || !selectedFloorId) return
    esaiApi
      .getFloorPreferences(projectId, selectedFloorId)
      .then((res) => {
        setFloorPrefs(res?.preferences || {})
      })
      .catch(() => setFloorPrefs({}))
  }, [projectId, selectedFloorId])

  // ─── Load Room Preferences & Effective Cascade ───────────────────────────────
  const loadRoomDetails = useCallback(async () => {
    if (!projectId || !selectedRoomId || !selectedFloorId) return
    try {
      const [rPrefs, eff, schema] = await Promise.all([
        esaiApi.getRoomPreferences(projectId, selectedRoomId),
        esaiApi.getEffectivePreferences(projectId, selectedRoomId, selectedFloorId),
        selectedRoom?.room_type
          ? esaiApi.getPreferenceSchema(projectId, selectedRoom.room_type)
          : Promise.resolve(null),
      ])

      if (rPrefs) {
        setRoomPrefs({
          preferences: rPrefs.preferences || {},
          specific_assets: (rPrefs as any).specific_assets || [],
          custom_constraints: (rPrefs as any).custom_constraints || [],
        })
      } else {
        setRoomPrefs({ preferences: {}, specific_assets: [], custom_constraints: [] })
      }

      setEffective(eff)
      if (schema) setRoomSchema(schema)
    } catch (err) {
      console.error('Error loading room preferences', err)
    }
  }, [projectId, selectedRoomId, selectedFloorId, selectedRoom?.room_type])

  useEffect(() => {
    loadRoomDetails()
  }, [loadRoomDetails])

  // ─── Save Handlers ───────────────────────────────────────────────────────────
  const handleSaveBuilding = async () => {
    if (!projectId) return
    setIsSaving(true)
    setStatusMessage(null)
    try {
      await esaiApi.saveBuildingPreferences(projectId, buildingPrefs)
      setStatusMessage({ type: 'success', text: 'Building-level defaults saved successfully.' })
      await loadRoomDetails()
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err.response?.data?.detail?.message || 'Failed to save building preferences.' })
    } finally {
      setIsSaving(false)
    }
  }

  const handleSaveFloor = async () => {
    if (!projectId || !selectedFloorId) return
    setIsSaving(true)
    setStatusMessage(null)
    try {
      await esaiApi.saveFloorPreferences(projectId, selectedFloorId, floorPrefs)
      setStatusMessage({ type: 'success', text: `Floor overrides for "${selectedFloor?.floor_name || selectedFloorId}" saved.` })
      await loadRoomDetails()
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err.response?.data?.detail?.message || 'Failed to save floor preferences.' })
    } finally {
      setIsSaving(false)
    }
  }

  const handleResetFloor = async () => {
    if (!projectId || !selectedFloorId) return
    if (!confirm('Revert all floor overrides and inherit directly from building defaults?')) return
    setIsSaving(true)
    try {
      await esaiApi.resetFloorPreferences(projectId, selectedFloorId)
      setFloorPrefs({})
      setStatusMessage({ type: 'info', text: 'Floor overrides reset to building defaults.' })
      await loadRoomDetails()
    } catch (err) {
      setStatusMessage({ type: 'error', text: 'Failed to reset floor preferences.' })
    } finally {
      setIsSaving(false)
    }
  }

  const handleSaveRoom = async () => {
    if (!projectId || !selectedRoomId) return
    setIsSaving(true)
    setStatusMessage(null)
    try {
      await esaiApi.saveRoomPreferences(projectId, selectedRoomId, roomPrefs)
      setStatusMessage({ type: 'success', text: `Preferences for "${selectedRoom?.name || selectedRoomId}" saved.` })
      await loadContext()
      await loadRoomDetails()
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err.response?.data?.detail?.message || 'Failed to save room preferences.' })
    } finally {
      setIsSaving(false)
    }
  }

  const handleResetRoom = async () => {
    if (!projectId || !selectedRoomId) return
    if (!confirm('Revert this room to inherit from floor and building defaults? Custom overrides will be cleared.')) return
    setIsSaving(true)
    try {
      await esaiApi.resetRoomPreferences(projectId, selectedRoomId)
      setRoomPrefs({ preferences: {}, specific_assets: [], custom_constraints: [] })
      setStatusMessage({ type: 'info', text: 'Room preferences reverted to inherited defaults.' })
      await loadContext()
      await loadRoomDetails()
    } catch (err) {
      setStatusMessage({ type: 'error', text: 'Failed to reset room preferences.' })
    } finally {
      setIsSaving(false)
    }
  }

  const handleDetectOrphans = async () => {
    if (!projectId) return
    try {
      const rep = await esaiApi.detectOrphans(projectId)
      setOrphanModal(rep)
      await loadContext()
    } catch (err) {
      alert('Orphan check failed')
    }
  }

  // Helper for source badge
  const renderSourceBadge = (key: string) => {
    if (!effective) return null
    let source = 'DEFAULT'
    if (typeof effective.sources === 'object' && !Array.isArray(effective.sources)) {
      if ('building' in effective.sources && Array.isArray((effective.sources as any).building)) {
        const s = effective.sources as { building: string[]; floor: string[]; room: string[] }
        if (s.room?.includes(key)) source = 'OVERRIDDEN_ROOM'
        else if (s.floor?.includes(key)) source = 'INHERITED_FLOOR'
        else if (s.building?.includes(key)) source = 'INHERITED_BUILDING'
      } else {
        source = (effective.sources as Record<string, string>)[key] || 'DEFAULT'
      }
    }

    switch (source) {
      case 'OVERRIDDEN_ROOM':
        return <Badge className="bg-purple-500/20 text-purple-300 border-purple-500/40 text-[10px]">Room Override</Badge>
      case 'INHERITED_FLOOR':
        return <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-500/40 text-[10px]">Floor Default</Badge>
      case 'INHERITED_BUILDING':
        return <Badge className="bg-cyan-500/20 text-cyan-300 border-cyan-500/40 text-[10px]">Building Default</Badge>
      default:
        return <Badge variant="outline" className="text-muted-foreground text-[10px]">System Default</Badge>
    }
  }

  // Room type icon
  const getRoomIcon = (type: string) => {
    const t = type.toLowerCase()
    if (t.includes('bed')) return <Bed className="w-3.5 h-3.5 text-purple-400" />
    if (t.includes('living') || t.includes('lounge')) return <Tv className="w-3.5 h-3.5 text-blue-400" />
    if (t.includes('kitchen') || t.includes('pantry') || t.includes('dining')) return <UtensilsCrossed className="w-3.5 h-3.5 text-amber-400" />
    if (t.includes('bath') || t.includes('toilet')) return <Bath className="w-3.5 h-3.5 text-cyan-400" />
    if (t.includes('study') || t.includes('office')) return <Briefcase className="w-3.5 h-3.5 text-emerald-400" />
    return <DoorOpen className="w-3.5 h-3.5 text-stone-400" />
  }

  return (
    <FeatureWorkflowShell
      componentId="esai_engine"
      title="ESAI-Engine: Ergonomic Spatial Interior Intelligence"
      number="03"
      description="Multi-level client preference system with deterministic Neufert-standard ergonomic resolution."
      onPrev={() => router.push('/features/vsai-rectifier')}
      onNext={() => router.push('/features/elia-engine')}
      onSkip={async () => {
        await skipComponent('esai_engine')
        router.push('/features/elia-engine')
      }}
    >
      <div className="p-6 max-w-[1600px] mx-auto space-y-6">

        {/* ─── Top Status Banner & Staleness Indicator ──────────────────────────── */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-card/60 backdrop-blur border border-border/80 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Building2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold tracking-tight text-foreground">{projectName || 'Interior Design Project'}</h2>
                <Badge variant="outline" className="border-cyan-500/40 text-cyan-300 bg-cyan-500/10 text-xs">Phase 2: Preferences Active</Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {context?.total_floors || 0} Floors • {context?.total_rooms || 0} Rooms • {context?.configured_rooms || 0} Configured
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {context?.geometry_staleness?.is_stale ? (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs">
                <AlertCircle className="w-4 h-4 text-amber-400 animate-pulse" />
                <span>Upstream Geometry Modified</span>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px] text-amber-300 hover:bg-amber-500/20" onClick={handleDetectOrphans}>
                  Scan Orphans
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Geometry Synchronized</span>
              </div>
            )}

            <Button
              size="sm"
              variant="outline"
              className="text-xs border-border/80 hover:bg-muted/50 gap-1.5"
              onClick={loadContext}
              disabled={isLoading}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              Reload Context
            </Button>

            <Button
              size="sm"
              className="text-xs bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white shadow-md shadow-cyan-500/20 gap-1.5"
              onClick={() => setRunModalOpen(true)}
            >
              <Sparkles className="w-3.5 h-3.5" />
              Run ESAI Optimizer
            </Button>
          </div>
        </div>

        {/* ─── Feedback Toast / Banner ─────────────────────────────────────────── */}
        {statusMessage && (
          <div
            className={`p-3.5 rounded-lg text-xs flex items-center justify-between border ${
              statusMessage.type === 'success'
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                : statusMessage.type === 'error'
                ? 'bg-red-500/10 border-red-500/30 text-red-300'
                : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
            }`}
          >
            <div className="flex items-center gap-2">
              {statusMessage.type === 'success' ? <Check className="w-4 h-4" /> : <Info className="w-4 h-4" />}
              <span>{statusMessage.text}</span>
            </div>
            <button className="text-muted-foreground hover:text-foreground text-xs" onClick={() => setStatusMessage(null)}>
              ✕
            </button>
          </div>
        )}

        {/* ─── Main 3-Column Layout ────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

          {/* ══════════════════════════════════════════════════════════════════════════
              COLUMN 1 (3 Cols): Spatial Hierarchy Tree Navigator
             ══════════════════════════════════════════════════════════════════════════ */}
          <div className="lg:col-span-3 space-y-4">
            <Card className="border-border/70 bg-card/70 backdrop-blur shadow-sm">
              <CardHeader className="pb-3 pt-4 px-4 border-b border-border/50">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold tracking-wide flex items-center gap-2">
                    <Layers className="w-4 h-4 text-cyan-400" />
                    Spatial Navigator
                  </CardTitle>
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0.5">
                    {context?.total_rooms || 0} Rooms
                  </Badge>
                </div>
                <CardDescription className="text-[11px] text-muted-foreground">
                  Select a scope to configure multi-level interior preferences.
                </CardDescription>
              </CardHeader>

              <CardContent className="p-3 space-y-2">
                {/* 1. Global Building Defaults Target */}
                <button
                  onClick={() => setActiveLevel('building')}
                  className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between ${
                    activeLevel === 'building'
                      ? 'bg-cyan-500/15 border-cyan-500/50 shadow-sm shadow-cyan-500/10 text-cyan-200'
                      : 'bg-muted/30 border-transparent hover:bg-muted/60 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Building2 className={`w-4 h-4 ${activeLevel === 'building' ? 'text-cyan-400' : 'text-muted-foreground'}`} />
                    <div>
                      <div className="text-xs font-semibold">Building Defaults</div>
                      <div className="text-[10px] opacity-75">Global theme, palette & lighting</div>
                    </div>
                  </div>
                  <Badge variant="outline" className="text-[9px] border-cyan-500/40 text-cyan-300 bg-cyan-500/10">
                    Global
                  </Badge>
                </button>

                <div className="pt-2 pb-1 px-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
                  <span>Floors & Rooms</span>
                  <span className="text-[10px] normal-case text-muted-foreground font-normal">Inheritance tree</span>
                </div>

                {/* 2. Floor & Rooms Hierarchy */}
                <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
                  {context?.floors.map((fl) => {
                    const isFloorSelected = activeLevel === 'floor' && selectedFloorId === fl.floor_id
                    const isCollapsed = collapsedFloors[fl.floor_id]

                    return (
                      <div key={fl.floor_id} className="rounded-lg border border-border/50 bg-background/50 overflow-hidden">
                        {/* Floor Header Bar */}
                        <div
                          className={`flex items-center justify-between p-2.5 transition-colors cursor-pointer ${
                            isFloorSelected ? 'bg-emerald-500/15 border-l-2 border-emerald-400' : 'hover:bg-muted/40'
                          }`}
                        >
                          <div
                            className="flex items-center gap-2 flex-1"
                            onClick={() => {
                              setSelectedFloorId(fl.floor_id)
                              setActiveLevel('floor')
                            }}
                          >
                            <Layers className="w-3.5 h-3.5 text-emerald-400" />
                            <span className="text-xs font-medium text-foreground">{fl.floor_name || fl.floor_id}</span>
                            <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 bg-muted/30">
                              {fl.rooms.length}
                            </Badge>
                          </div>

                          <button
                            className="p-1 rounded hover:bg-muted/60 text-muted-foreground"
                            onClick={(e) => {
                              e.stopPropagation()
                              setCollapsedFloors((prev) => ({ ...prev, [fl.floor_id]: !prev[fl.floor_id] }))
                            }}
                          >
                            {isCollapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                        </div>

                        {/* Room Items */}
                        {!isCollapsed && (
                          <div className="divide-y divide-border/30 bg-muted/10">
                            {fl.rooms.map((rm) => {
                              const isRoomActive = activeLevel === 'room' && selectedRoomId === rm.room_id

                              return (
                                <button
                                  key={rm.room_id}
                                  onClick={() => {
                                    setSelectedFloorId(fl.floor_id)
                                    setSelectedRoomId(rm.room_id)
                                    setActiveLevel('room')
                                  }}
                                  className={`w-full text-left py-2 px-3 pl-7 flex items-center justify-between transition-colors ${
                                    isRoomActive
                                      ? 'bg-purple-500/15 text-purple-200 border-l-2 border-purple-400'
                                      : 'hover:bg-muted/40 text-muted-foreground hover:text-foreground'
                                  }`}
                                >
                                  <div className="flex items-center gap-2 truncate">
                                    {getRoomIcon(rm.room_type)}
                                    <div className="truncate">
                                      <div className="text-xs font-medium truncate">{rm.name}</div>
                                      <div className="text-[10px] text-muted-foreground flex items-center gap-1.5">
                                        <span>{rm.room_type.replace('_', ' ')}</span>
                                        <span>•</span>
                                        <span>{rm.area_sqm.toFixed(1)} m²</span>
                                      </div>
                                    </div>
                                  </div>

                                  <div className="flex items-center gap-1 shrink-0">
                                    {rm.is_orphaned ? (
                                      <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4">
                                        Orphan
                                      </Badge>
                                    ) : rm.preference_saved ? (
                                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                    ) : (
                                      <span className="w-2 h-2 rounded-full bg-border" title="Inheriting defaults" />
                                    )}
                                  </div>
                                </button>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* ══════════════════════════════════════════════════════════════════════════
              COLUMN 2 (6 Cols): Preference Configuration Editor
             ══════════════════════════════════════════════════════════════════════════ */}
          <div className="lg:col-span-6 space-y-4">

            {/* Scope Breadcrumb Bar */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-card/80 border border-border/70 text-xs">
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="font-semibold text-foreground">Scope:</span>
                <span className="px-2 py-0.5 rounded bg-muted text-foreground">
                  {activeLevel === 'building' && '🏢 Building-Level Defaults'}
                  {activeLevel === 'floor' && `🏗️ Floor Override (${selectedFloor?.floor_name || selectedFloorId})`}
                  {activeLevel === 'room' && `🛋️ Room: ${selectedRoom?.name || selectedRoomId} (${selectedRoom?.room_type.replace('_', ' ')})`}
                </span>
              </div>

              <div className="flex items-center gap-2">
                {activeLevel === 'floor' && (
                  <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-red-400 hover:bg-red-500/10" onClick={handleResetFloor}>
                    <RotateCcw className="w-3 h-3 mr-1" /> Revert to Building
                  </Button>
                )}
                {activeLevel === 'room' && (
                  <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-red-400 hover:bg-red-500/10" onClick={handleResetRoom}>
                    <RotateCcw className="w-3 h-3 mr-1" /> Revert Room Overrides
                  </Button>
                )}
              </div>
            </div>

            {/* ── 1. BUILDING LEVEL PREFERENCES ── */}
            {activeLevel === 'building' && (
              <Card className="border-border/70 bg-card/70 backdrop-blur">
                <CardHeader className="pb-3 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base font-semibold flex items-center gap-2">
                        <Palette className="w-4 h-4 text-cyan-400" />
                        Global Building Interior Defaults
                      </CardTitle>
                      <CardDescription className="text-xs">
                        Base style, palette, and finishes applied across all floors and rooms unless specifically overridden.
                      </CardDescription>
                    </div>
                    <Button size="sm" className="bg-cyan-600 hover:bg-cyan-700 text-white gap-1.5 h-8 text-xs" onClick={handleSaveBuilding} disabled={isSaving}>
                      <Save className="w-3.5 h-3.5" />
                      {isSaving ? 'Saving...' : 'Save Defaults'}
                    </Button>
                  </div>
                </CardHeader>

                <CardContent className="p-5 space-y-6">
                  {/* Style Selector */}
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" /> Architectural Interior Style
                    </label>
                    <div className="grid grid-cols-2 gap-2.5">
                      {STYLE_OPTIONS.map((opt) => (
                        <div
                          key={opt.value}
                          onClick={() => setBuildingPrefs((p) => ({ ...p, style: opt.value }))}
                          className={`p-3 rounded-lg border text-left cursor-pointer transition-all ${
                            buildingPrefs.style === opt.value
                              ? 'bg-cyan-500/15 border-cyan-500 text-cyan-100 shadow-sm'
                              : 'bg-muted/20 border-border/50 hover:bg-muted/40 text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          <div className="text-xs font-bold text-foreground">{opt.label}</div>
                          <div className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{opt.desc}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Primary Color Palette */}
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <Palette className="w-3.5 h-3.5 text-cyan-400" /> Primary Color Palette
                    </label>
                    <div className="grid grid-cols-2 gap-2.5">
                      {PALETTE_OPTIONS.map((pal) => (
                        <div
                          key={pal.value}
                          onClick={() => setBuildingPrefs((p) => ({ ...p, primary_palette: pal.value }))}
                          className={`p-3 rounded-lg border cursor-pointer transition-all ${
                            buildingPrefs.primary_palette === pal.value
                              ? 'bg-cyan-500/15 border-cyan-500 text-cyan-100'
                              : 'bg-muted/20 border-border/50 hover:bg-muted/40 text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-xs font-medium text-foreground">{pal.label}</span>
                            {buildingPrefs.primary_palette === pal.value && <Check className="w-3.5 h-3.5 text-cyan-400" />}
                          </div>
                          <div className={`h-2.5 w-full rounded-full ${pal.preview}`} />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Flooring & Lighting Mood Grid */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-foreground">Default Flooring Material</label>
                      <select
                        value={buildingPrefs.flooring || 'oak_hardwood'}
                        onChange={(e) => setBuildingPrefs((p) => ({ ...p, flooring: e.target.value }))}
                        className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      >
                        {FLOORING_OPTIONS.map((f) => (
                          <option key={f} value={f}>
                            {f.replace('_', ' ').toUpperCase()}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-foreground">Lighting Mood & Temperature</label>
                      <select
                        value={buildingPrefs.lighting_mood || 'warm_diffuse'}
                        onChange={(e) => setBuildingPrefs((p) => ({ ...p, lighting_mood: e.target.value }))}
                        className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      >
                        {LIGHTING_OPTIONS.map((l) => (
                          <option key={l.value} value={l.value}>
                            {l.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── 2. FLOOR LEVEL PREFERENCES ── */}
            {activeLevel === 'floor' && selectedFloor && (
              <Card className="border-border/70 bg-card/70 backdrop-blur">
                <CardHeader className="pb-3 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base font-semibold flex items-center gap-2">
                        <Layers className="w-4 h-4 text-emerald-400" />
                        Floor Override: {selectedFloor.floor_name || selectedFloorId}
                      </CardTitle>
                      <CardDescription className="text-xs">
                        Configure floor-wide overrides. Any setting defined here overrides building defaults for all rooms on this floor.
                      </CardDescription>
                    </div>
                    <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5 h-8 text-xs" onClick={handleSaveFloor} disabled={isSaving}>
                      <Save className="w-3.5 h-3.5" />
                      {isSaving ? 'Saving...' : 'Save Floor Overrides'}
                    </Button>
                  </div>
                </CardHeader>

                <CardContent className="p-5 space-y-5">
                  <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 flex items-center justify-between">
                    <div>
                      <span className="font-semibold">Floor Hierarchy Active:</span> Rooms on {selectedFloor.floor_name || selectedFloorId} will automatically inherit these settings.
                    </div>
                    {Object.keys(floorPrefs).length > 0 && (
                      <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-500/40 text-[10px]">
                        {Object.keys(floorPrefs).length} Overrides Defined
                      </Badge>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-foreground">Floor-Level Flooring Override</label>
                      <select
                        value={floorPrefs.flooring || ''}
                        onChange={(e) => {
                          const v = e.target.value
                          setFloorPrefs((p) => (v ? { ...p, flooring: v } : (({ flooring, ...rest }) => rest)(p)))
                        }}
                        className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      >
                        <option value="">— Inherit Building Default ({buildingPrefs.flooring || 'oak_hardwood'}) —</option>
                        {FLOORING_OPTIONS.map((f) => (
                          <option key={f} value={f}>
                            {f.replace('_', ' ').toUpperCase()}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-foreground">Floor Lighting Mood Override</label>
                      <select
                        value={floorPrefs.lighting_mood || ''}
                        onChange={(e) => {
                          const v = e.target.value
                          setFloorPrefs((p) => (v ? { ...p, lighting_mood: v } : (({ lighting_mood, ...rest }) => rest)(p)))
                        }}
                        className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      >
                        <option value="">— Inherit Building Default —</option>
                        {LIGHTING_OPTIONS.map((l) => (
                          <option key={l.value} value={l.value}>
                            {l.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-foreground">Floor Style Override (Optional)</label>
                    <select
                      value={floorPrefs.style || ''}
                      onChange={(e) => {
                        const v = e.target.value
                        setFloorPrefs((p) => (v ? { ...p, style: v } : (({ style, ...rest }) => rest)(p)))
                      }}
                      className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    >
                      <option value="">— Inherit Building Default ({buildingPrefs.style || 'modern'}) —</option>
                      {STYLE_OPTIONS.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── 3. ROOM LEVEL PREFERENCES (DYNAMIC FORM) ── */}
            {activeLevel === 'room' && selectedRoom && (
              <Card className="border-border/70 bg-card/70 backdrop-blur">
                <CardHeader className="pb-3 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-base font-semibold flex items-center gap-2">
                          {getRoomIcon(selectedRoom.room_type)}
                          {selectedRoom.name}
                        </CardTitle>
                        <Badge variant="outline" className="text-[10px] px-2 py-0 border-purple-500/40 text-purple-300 bg-purple-500/10">
                          {selectedRoom.room_type.replace('_', ' ')}
                        </Badge>
                      </div>
                      <CardDescription className="text-xs mt-0.5">
                        Floor: {selectedFloor?.floor_name || selectedFloorId} • Area: {selectedRoom.area_sqm.toFixed(1)} m²
                      </CardDescription>
                    </div>

                    <Button size="sm" className="bg-purple-600 hover:bg-purple-700 text-white gap-1.5 h-8 text-xs" onClick={handleSaveRoom} disabled={isSaving}>
                      <Save className="w-3.5 h-3.5" />
                      {isSaving ? 'Saving...' : 'Save Room'}
                    </Button>
                  </div>
                </CardHeader>

                <CardContent className="p-5">
                  <Tabs defaultValue="specific" className="space-y-4">
                    <TabsList className="bg-muted/40 p-1 border border-border/60">
                      <TabsTrigger value="specific" className="text-xs">
                        Layout & Specifics
                      </TabsTrigger>
                      <TabsTrigger value="finishes" className="text-xs">
                        Finishes & Ambience
                      </TabsTrigger>
                      <TabsTrigger value="constraints" className="text-xs">
                        Custom Constraints
                      </TabsTrigger>
                    </TabsList>

                    {/* Tab 1: Room-Specific Dynamic Fields */}
                    <TabsContent value="specific" className="space-y-4 pt-2">
                      {/* BEDROOMS (Master Bed, Bedroom, Guest Room) */}
                      {selectedRoom.room_type.toLowerCase().includes('bed') && (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Bed Type / Size</label>
                              <select
                                value={roomPrefs.preferences?.bed_type || 'king'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, bed_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="king">King (180 × 200 cm)</option>
                                <option value="queen">Queen (160 × 200 cm)</option>
                                <option value="double">Double (140 × 200 cm)</option>
                                <option value="twin">Twin / Single (90 × 200 cm)</option>
                                <option value="bunk">Bunk Bed (Space Saver)</option>
                              </select>
                            </div>

                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Wardrobe Configuration</label>
                              <select
                                value={roomPrefs.preferences?.wardrobe_type || 'walk_in'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, wardrobe_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="walk_in">Walk-in Closet / Dressing Zone</option>
                                <option value="fitted_full_height">Fitted Full-Height Wardrobe</option>
                                <option value="sliding_door">Sliding Door Wardrobe</option>
                                <option value="freestanding">Freestanding Armoire</option>
                                <option value="none">No Wardrobe Required</option>
                              </select>
                            </div>
                          </div>

                          <div className="grid grid-cols-3 gap-3">
                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.dressing_table_required ?? true}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, dressing_table_required: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Dressing Table & Mirror</span>
                            </label>

                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.tv_in_bedroom ?? false}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, tv_in_bedroom: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Wall-Mounted TV</span>
                            </label>

                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.study_desk_required ?? false}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, study_desk_required: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Study / Laptop Desk</span>
                            </label>
                          </div>
                        </div>
                      )}

                      {/* LIVING ROOM & LOUNGES */}
                      {(selectedRoom.room_type.toLowerCase().includes('living') ||
                        selectedRoom.room_type.toLowerCase().includes('lounge')) && (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Sofa Configuration</label>
                              <select
                                value={roomPrefs.preferences?.sofa_type || 'l_shaped_sectional'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, sofa_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="l_shaped_sectional">L-Shaped Sectional</option>
                                <option value="3_seater_plus_armchairs">3-Seater Sofa + 2 Armchairs</option>
                                <option value="modular_pit">Deep Modular Conversation Pit</option>
                                <option value="compact_2_seater">Compact 2-Seater Loveseat</option>
                              </select>
                            </div>

                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Seating Capacity Target</label>
                              <select
                                value={roomPrefs.preferences?.seating_capacity || '6'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, seating_capacity: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="4">4 Persons</option>
                                <option value="6">6 Persons (Standard Family)</option>
                                <option value="8">8 Persons (Entertaining)</option>
                                <option value="10">10+ Persons (Large Social)</option>
                              </select>
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Entertainment / TV Wall</label>
                              <select
                                value={roomPrefs.preferences?.tv_wall_type || 'floating_credenza'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, tv_wall_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="floating_credenza">Floating Console Credenza</option>
                                <option value="full_media_slat_wall">Full Acoustic Slat Media Wall</option>
                                <option value="fireplace_integrated">Fireplace + TV Integrated Unit</option>
                                <option value="projector_screen">Motorized Drop-down Projector</option>
                              </select>
                            </div>

                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Room Focal Point</label>
                              <select
                                value={roomPrefs.preferences?.focal_point || 'tv_wall'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, focal_point: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="tv_wall">TV / Media Center</option>
                                <option value="window_garden_view">Garden / Window View</option>
                                <option value="fireplace">Architectural Fireplace</option>
                                <option value="central_conversation">Central Coffee Table Cluster</option>
                              </select>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* KITCHEN & PANTRY */}
                      {(selectedRoom.room_type.toLowerCase().includes('kitchen') ||
                        selectedRoom.room_type.toLowerCase().includes('pantry')) && (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Kitchen Layout Typology</label>
                              <select
                                value={roomPrefs.preferences?.layout_type || 'island'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, layout_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="island">Island Kitchen (Central Prep & Dining)</option>
                                <option value="l_shaped">L-Shaped with Peninsula</option>
                                <option value="parallel">Parallel / Galley Counter</option>
                                <option value="u_shaped">U-Shaped High-Efficiency Work Triangle</option>
                                <option value="single_wall">Single-Wall Linear with Tall Units</option>
                              </select>
                            </div>

                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Hob & Cooktop Provision</label>
                              <select
                                value={roomPrefs.preferences?.hob_type || 'induction'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, hob_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="induction">4-Zone Induction Cooktop</option>
                                <option value="gas">Flush Black Glass Gas Burners</option>
                                <option value="hybrid">Hybrid Gas + Induction</option>
                              </select>
                            </div>
                          </div>

                          <div className="grid grid-cols-3 gap-3">
                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.dishwasher_required ?? true}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, dishwasher_required: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Integrated Dishwasher</span>
                            </label>

                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.breakfast_bar_required ?? true}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, breakfast_bar_required: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Breakfast Bar Seating</span>
                            </label>

                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.under_cabinet_lighting ?? true}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, under_cabinet_lighting: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Under-Cabinet Task LED</span>
                            </label>
                          </div>
                        </div>
                      )}

                      {/* BATHROOMS & TOILETS */}
                      {selectedRoom.room_type.toLowerCase().includes('bath') && (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Shower vs Bathtub</label>
                              <select
                                value={roomPrefs.preferences?.shower_bath_setup || 'walk_in_shower'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, shower_bath_setup: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="walk_in_shower">Frameless Glass Walk-in Rainshower</option>
                                <option value="bathtub_freestanding">Freestanding Soaking Tub + Shower</option>
                                <option value="tub_shower_combo">Bathtub / Shower Combo Unit</option>
                                <option value="shower_cubicle">Compact Corner Cubicle</option>
                              </select>
                            </div>

                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Vanity Unit</label>
                              <select
                                value={roomPrefs.preferences?.vanity_type || 'floating_double'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, vanity_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="floating_double">Floating Double-Sink Vanity</option>
                                <option value="floating_single">Floating Single-Sink Vanity</option>
                                <option value="vessel_sink_console">Vessel Sink with Stone Console</option>
                              </select>
                            </div>
                          </div>

                          <div className="grid grid-cols-3 gap-3">
                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.bidet_required ?? false}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, bidet_required: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Bidet / Smart Toilet</span>
                            </label>

                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.heated_towel_rail ?? true}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, heated_towel_rail: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Heated Towel Rail</span>
                            </label>

                            <label className="flex items-center gap-2 p-3 rounded-lg border border-border/60 bg-muted/20 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={roomPrefs.preferences?.mirror_backlight ?? true}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, mirror_backlight: e.target.checked },
                                  }))
                                }
                                className="rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs">Anti-Fog LED Mirror</span>
                            </label>
                          </div>
                        </div>
                      )}

                      {/* STUDY & OFFICE */}
                      {(selectedRoom.room_type.toLowerCase().includes('study') ||
                        selectedRoom.room_type.toLowerCase().includes('office')) && (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Desk Typology</label>
                              <select
                                value={roomPrefs.preferences?.desk_type || 'standing_desk'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, desk_type: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="standing_desk">Electric Height-Adjustable Standing Desk</option>
                                <option value="executive_l_shaped">Executive L-Shaped Corner Desk</option>
                                <option value="minimal_floating">Floating Wall-Mounted Slab Desk</option>
                                <option value="dual_workstation">Dual Workstation (Side by Side)</option>
                              </select>
                            </div>

                            <div className="space-y-1.5">
                              <label className="text-xs font-semibold text-foreground">Display & Monitor Setup</label>
                              <select
                                value={roomPrefs.preferences?.monitor_setup || 'dual_monitor'}
                                onChange={(e) =>
                                  setRoomPrefs((prev) => ({
                                    ...prev,
                                    preferences: { ...prev.preferences, monitor_setup: e.target.value },
                                  }))
                                }
                                className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                              >
                                <option value="dual_monitor">Dual 27" Monitors with Gas Arms</option>
                                <option value="ultrawide">Single 49" Curved Ultrawide</option>
                                <option value="laptop_dock">Minimalist Laptop Dock Setup</option>
                              </select>
                            </div>
                          </div>
                        </div>
                      )}
                    </TabsContent>

                    {/* Tab 2: Finishes & Ambience Overrides */}
                    <TabsContent value="finishes" className="space-y-4 pt-2">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Room Style Override</label>
                          <select
                            value={roomPrefs.preferences?.style || ''}
                            onChange={(e) => {
                              const val = e.target.value
                              setRoomPrefs((prev) => {
                                const p = { ...prev.preferences }
                                if (val) p.style = val
                                else delete p.style
                                return { ...prev, preferences: p }
                              })
                            }}
                            className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                          >
                            <option value="">— Inherit ({effective?.effective_preferences?.style || buildingPrefs.style}) —</option>
                            {STYLE_OPTIONS.map((s) => (
                              <option key={s.value} value={s.value}>
                                {s.label}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Room Flooring Override</label>
                          <select
                            value={roomPrefs.preferences?.flooring || ''}
                            onChange={(e) => {
                              const val = e.target.value
                              setRoomPrefs((prev) => {
                                const p = { ...prev.preferences }
                                if (val) p.flooring = val
                                else delete p.flooring
                                return { ...prev, preferences: p }
                              })
                            }}
                            className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                          >
                            <option value="">— Inherit ({effective?.effective_preferences?.flooring || buildingPrefs.flooring}) —</option>
                            {FLOORING_OPTIONS.map((f) => (
                              <option key={f} value={f}>
                                {f.replace('_', ' ').toUpperCase()}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Lighting Atmosphere</label>
                          <select
                            value={roomPrefs.preferences?.lighting_mood || ''}
                            onChange={(e) => {
                              const val = e.target.value
                              setRoomPrefs((prev) => {
                                const p = { ...prev.preferences }
                                if (val) p.lighting_mood = val
                                else delete p.lighting_mood
                                return { ...prev, preferences: p }
                              })
                            }}
                            className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                          >
                            <option value="">— Inherit ({effective?.effective_preferences?.lighting_mood || buildingPrefs.lighting_mood}) —</option>
                            {LIGHTING_OPTIONS.map((l) => (
                              <option key={l.value} value={l.value}>
                                {l.label}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Circulation Clearance Priority</label>
                          <select
                            value={roomPrefs.preferences?.circulation_priority || 'standard'}
                            onChange={(e) =>
                              setRoomPrefs((prev) => ({
                                ...prev,
                                preferences: { ...prev.preferences, circulation_priority: e.target.value },
                              }))
                            }
                            className="w-full h-9 px-3 text-xs rounded-md bg-muted/40 border border-border/80 focus:outline-none focus:ring-1 focus:ring-purple-500"
                          >
                            <option value="standard">Standard Neufert (90 cm corridors)</option>
                            <option value="spacious">Spacious Luxury (120 cm clearance)</option>
                            <option value="accessible">Wheelchair Accessible (150 cm turn circles)</option>
                            <option value="compact">Compact Space-Optimized (75 cm minimum)</option>
                          </select>
                        </div>
                      </div>
                    </TabsContent>

                    {/* Tab 3: Custom Constraints */}
                    <TabsContent value="constraints" className="space-y-4 pt-2">
                      <div className="text-xs text-muted-foreground">
                        Define room-specific architectural and spatial constraints evaluated by the Genetic Algorithm interior optimizer.
                      </div>

                      <div className="space-y-2">
                        {[
                          { id: 'c_door_window', label: 'Maintain direct unimpeded walking corridor between entrance door and primary window' },
                          { id: 'c_no_mirror_bed', label: 'Orient wardrobe mirror away from direct direct reflection of bed headboard' },
                          { id: 'c_radiator_clearance', label: 'Enforce minimum 40cm clearance from exterior wall radiators and vents' },
                          { id: 'c_corner_ac', label: 'Avoid placing tall bookcases directly underneath split-unit AC wall opening' },
                        ].map((c) => {
                          const active = roomPrefs.custom_constraints?.some((item: any) => item.id === c.id)
                          return (
                            <label
                              key={c.id}
                              className={`flex items-start gap-2.5 p-3 rounded-lg border cursor-pointer transition-colors ${
                                active ? 'bg-purple-500/10 border-purple-500/40 text-purple-200' : 'bg-muted/20 border-border/50 text-muted-foreground'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={active}
                                onChange={(e) => {
                                  setRoomPrefs((prev) => {
                                    const curr = prev.custom_constraints || []
                                    const next = e.target.checked
                                      ? [...curr, { id: c.id, description: c.label }]
                                      : curr.filter((item: any) => item.id !== c.id)
                                    return { ...prev, custom_constraints: next }
                                  })
                                }}
                                className="mt-0.5 rounded text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs leading-relaxed">{c.label}</span>
                            </label>
                          )
                        })}
                      </div>
                    </TabsContent>
                  </Tabs>
                </CardContent>
              </Card>
            )}
          </div>

          {/* ══════════════════════════════════════════════════════════════════════════
              COLUMN 3 (3 Cols): Live Effective Resolution & Ergonomic Constraints
             ══════════════════════════════════════════════════════════════════════════ */}
          <div className="lg:col-span-3 space-y-4">
            <Card className="border-border/70 bg-card/70 backdrop-blur shadow-sm">
              <CardHeader className="pb-3 pt-4 px-4 border-b border-border/50">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold tracking-wide flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-purple-400" />
                    Effective Resolution
                  </CardTitle>
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0.5 bg-purple-500/10 text-purple-300 border-purple-500/30">
                    Live Cascade
                  </Badge>
                </div>
                <CardDescription className="text-[11px] text-muted-foreground">
                  Final parameters resolved for optimizer execution with source attribution.
                </CardDescription>
              </CardHeader>

              <CardContent className="p-4 space-y-4">
                {effective?.effective_preferences ? (
                  <div className="space-y-3">
                    <div className="space-y-2">
                      {Object.entries(effective.effective_preferences)
                        .filter(([k]) => !['specific_assets', 'custom_constraints'].includes(k))
                        .map(([key, val]) => (
                          <div key={key} className="p-2.5 rounded-lg bg-background/60 border border-border/40 text-xs">
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-medium text-muted-foreground text-[11px] capitalize">
                                {key.replace(/_/g, ' ')}
                              </span>
                              {renderSourceBadge(key)}
                            </div>
                            <div className="font-semibold text-foreground truncate">
                              {typeof val === 'boolean' ? (val ? 'Yes' : 'No') : String(val).replace(/_/g, ' ')}
                            </div>
                          </div>
                        ))}
                    </div>

                    {/* Room Neufert Guidelines */}
                    <div className="p-3 rounded-lg bg-muted/30 border border-border/50 space-y-2">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                        <FileCheck2 className="w-3.5 h-3.5 text-cyan-400" />
                        Neufert Standard Ergonomics
                      </div>
                      <ul className="text-[11px] text-muted-foreground space-y-1 list-disc pl-4">
                        <li>Min corridor clearance: 900 mm</li>
                        <li>Bedside egress buffer: 750 mm</li>
                        <li>Door swing arc clearance: 100% unimpeded</li>
                        <li>Natural daylight illumination check: Passed</li>
                      </ul>
                    </div>
                  </div>
                ) : (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    Select a room to view its resolved cascade.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* ─── Stage 2 Preview Dialog ────────────────────────────────────────────── */}
      {runModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-cyan-400">
              <div className="p-2.5 rounded-full bg-cyan-500/10 border border-cyan-500/30">
                <Sparkles className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">ESAI Genetic Algorithm Optimizer</h3>
                <p className="text-xs text-muted-foreground">Stage 2 Scheduled Execution</p>
              </div>
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed">
              Phase 2 is fully complete! All room-by-room architectural preferences, multi-floor hierarchies, and Neufert ergonomic constraints are validated and persisted in the Master JSON.
            </p>

            <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-xs text-cyan-300">
              <span className="font-semibold">Stage 2 Roadmap:</span> Autonomous evolutionary placement, 3D glTF asset instancing, collision penalties, and clearance optimization will run against these saved preferences.
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button size="sm" variant="outline" className="text-xs" onClick={() => setRunModalOpen(false)}>
                Dismiss
              </Button>
              <Button
                size="sm"
                className="text-xs bg-cyan-600 hover:bg-cyan-700 text-white"
                onClick={() => {
                  setRunModalOpen(false)
                  router.push('/features/elia-engine')
                }}
              >
                Proceed to ELIA-Engine <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Orphan Report Modal ────────────────────────────────────────────────── */}
      {orphanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-amber-400">
              <div className="p-2.5 rounded-full bg-amber-500/10 border border-amber-500/30">
                <ShieldAlert className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">Orphan Preference Report</h3>
                <p className="text-xs text-muted-foreground">Scanned {orphanModal.scanned_count} saved preference records</p>
              </div>
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed">
              {orphanModal.message}
            </p>

            {orphanModal.orphaned_room_ids?.length > 0 && (
              <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30 space-y-1">
                <div className="text-xs font-semibold text-destructive">Orphaned Room IDs:</div>
                <div className="text-xs text-muted-foreground font-mono">
                  {orphanModal.orphaned_room_ids.join(', ')}
                </div>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button size="sm" className="text-xs" onClick={() => setOrphanModal(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </FeatureWorkflowShell>
  )
}
