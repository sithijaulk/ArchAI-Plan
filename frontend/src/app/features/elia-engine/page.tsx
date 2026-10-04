"use client"
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell'
import { OutputPreview } from '@/components/output/OutputPreview'
import { useProjectStore } from '@/store/projectStore'
import { eliaApi, LiveSolarConditions, SriLankaLocation } from '@/lib/api/elia'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoaderCircle, MapPin, Search, Sun } from 'lucide-react'

export default function EliaEnginePage() {
  const router = useRouter()
  const { projectId, projectName, setComponentStatus, setOutput, outputs } = useProjectStore()
  const [isProcessing, setIsProcessing] = useState(false)
  const [cityQuery, setCityQuery] = useState('')
  const [locations, setLocations] = useState<SriLankaLocation[]>([])
  const [selectedLocation, setSelectedLocation] = useState<SriLankaLocation | null>(null)
  const [solar, setSolar] = useState<LiveSolarConditions | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [isLoadingSolar, setIsLoadingSolar] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [runError, setRunError] = useState('')

  React.useEffect(() => {
    if (!projectId) router.push('/start')
  }, [projectId, router])

  if (!projectId) return null;

  const handleLocationSearch = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (cityQuery.trim().length < 2) return
    setIsSearching(true)
    setLocationError('')
    setSelectedLocation(null)
    setSolar(null)
    try {
      const response = await eliaApi.searchLocations(cityQuery.trim())
      setLocations(response.results)
      if (response.results.length === 0) setLocationError('No matching Sri Lankan locations. Try a nearby town or district.')
    } catch {
      setLocations([])
      setLocationError('Location search is unavailable. Please try again.')
    } finally {
      setIsSearching(false)
    }
  }

  const handleSolarLookup = async () => {
    if (!selectedLocation) return
    setIsLoadingSolar(true)
    setLocationError('')
    try {
      setSolar(await eliaApi.currentSolar(projectId, selectedLocation))
    } catch {
      setSolar(null)
      setLocationError('Current solar conditions could not be loaded. Please try again.')
    } finally {
      setIsLoadingSolar(false)
    }
  }

  const handleProcess = async () => {
    setIsProcessing(true)
    setRunError('')
    try {
      if (!selectedLocation) throw new Error('Select a Sri Lankan city or locality first.')
      const response = await eliaApi.run(projectId, {
        requirements: {
          location: {
            latitude: selectedLocation.latitude,
            longitude: selectedLocation.longitude,
            timezone: selectedLocation.timezone,
            city: selectedLocation.name,
          },
          include_live_solar: true,
        },
      })
      setOutput('elia_engine', response.exterior_landscape)
      setComponentStatus('elia_engine', 'completed')
      if (response.outcome === 'infeasible') {
        setRunError(response.exterior_landscape?.validation_summary?.reason || 'The site could not satisfy all exterior constraints.')
      }
    } catch (error) {
      setComponentStatus('elia_engine', 'failed')
      setRunError(error instanceof Error ? error.message : 'ELIA could not complete this run.')
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <FeatureWorkflowShell
      componentId="elia_engine"
      title="ELIA-Engine: Eco-Spatial Landscape Intelligence"
      number="04"
      description="Generates exterior spatial planning including access, safety zoning, shading and adaptive greenery."
      onPrev={() => router.push('/features/esai-engine')}
    >
      <div className="p-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 border-r border-border/50 pr-8">
            <h3 className="text-xl font-bold mb-4">Input Panel</h3>
            <div className="space-y-4 mb-6">
              <form onSubmit={handleLocationSearch} className="space-y-3">
                <Label htmlFor="elia-city">House location in Sri Lanka</Label>
                <div className="flex gap-2">
                  <Input
                    id="elia-city"
                    value={cityQuery}
                    onChange={(event) => setCityQuery(event.target.value)}
                    placeholder="Colombo, Malabe, Kaduwela..."
                    autoComplete="off"
                    maxLength={100}
                  />
                  <Button type="submit" variant="outline" size="icon" aria-label="Search Sri Lankan locations" disabled={isSearching || cityQuery.trim().length < 2}>
                    {isSearching ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  </Button>
                </div>
              </form>

              {locations.length > 0 && (
                <div className="max-h-52 space-y-1 overflow-y-auto rounded-md border border-border p-1" aria-label="Matching Sri Lankan locations">
                  {locations.map((location) => {
                    const isSelected = selectedLocation?.id === location.id
                    return (
                      <button
                        key={`${location.id}-${location.latitude}-${location.longitude}`}
                        type="button"
                        onClick={() => { setSelectedLocation(location); setSolar(null); setLocationError('') }}
                        aria-pressed={isSelected}
                        className={`w-full rounded-sm px-3 py-2 text-left transition-colors ${isSelected ? 'bg-primary/10 text-primary' : 'hover:bg-muted'}`}
                      >
                        <span className="flex items-center gap-2 text-sm font-medium"><MapPin className="h-4 w-4 shrink-0" />{location.name}</span>
                        <span className="mt-1 block pl-6 text-xs text-muted-foreground">{location.admin2 ? `${location.admin2}, ` : ''}{location.admin1 || location.country}</span>
                      </button>
                    )
                  })}
                </div>
              )}

              {selectedLocation && (
                <div className="space-y-3 rounded-md border border-border bg-muted/40 p-3">
                  <div className="text-sm">
                    <div className="font-medium">{selectedLocation.display_name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {selectedLocation.latitude.toFixed(5)}, {selectedLocation.longitude.toFixed(5)}
                    </div>
                  </div>
                  <Button type="button" variant="outline" className="w-full" onClick={handleSolarLookup} disabled={isLoadingSolar}>
                    {isLoadingSolar ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Sun className="mr-2 h-4 w-4" />}
                    {isLoadingSolar ? 'Loading solar data...' : 'Get current solar data'}
                  </Button>
                </div>
              )}

              {solar && (
                <section className="space-y-3 rounded-md border border-border p-3" aria-live="polite">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold">Solar conditions</h4>
                    <time className="text-xs text-muted-foreground">{new Date(solar.timestamp).toLocaleString()}</time>
                  </div>
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                    <div><dt className="text-xs text-muted-foreground">Shortwave</dt><dd className="font-medium">{solar.irradiance_w_m2.shortwave_radiation ?? '—'} W/m²</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Direct normal</dt><dd className="font-medium">{solar.irradiance_w_m2.direct_normal_irradiance ?? '—'} W/m²</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Sun elevation</dt><dd className="font-medium">{solar.solar_position.elevation_degrees.toFixed(1)}°</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Sun azimuth</dt><dd className="font-medium">{solar.solar_position.azimuth_degrees.toFixed(1)}°</dd></div>
                  </dl>
                  <p className="text-xs text-muted-foreground">Near-current weather-model estimate, not a rooftop sensor reading.</p>
                </section>
              )}

              <p className="text-xs text-muted-foreground">
                Location data: <a className="underline underline-offset-2" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
              </p>

              {locationError && <p role="alert" className="text-sm text-destructive">{locationError}</p>}
              {runError && <p role="alert" className="text-sm text-destructive">{runError}</p>}

              <div className="border-t border-border pt-3 text-xs text-muted-foreground">
                Master project geometry and previous component data remain the source of truth.
              </div>
            </div>
            <Button className="w-full electric-glow" onClick={handleProcess} disabled={isProcessing || !selectedLocation}>
              {isProcessing ? 'Processing...' : 'Generate Landscape'}
            </Button>
          </div>
          <div className="lg:col-span-2">
            <OutputPreview projectName={projectName} component="elia-engine" data={outputs['elia_engine']} />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  )
}
