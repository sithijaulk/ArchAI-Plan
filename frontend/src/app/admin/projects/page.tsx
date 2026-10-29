"use client"
import React, { useEffect, useState, useMemo } from 'react'
import { projectsApi } from '@/lib/api/projects'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  FolderKanban,
  Search,
  RefreshCw,
  ExternalLink,
  Trash2,
  Layers,
  Calendar,
  CheckCircle2,
  Clock,
  Compass,
  FileCode2,
  AlertCircle
} from 'lucide-react'
import Link from 'next/link'

interface ProjectItem {
  id: string
  project_name: string
  description?: string
  current_component?: string
  master_json?: any
  revision: number
  created_at: string
  updated_at: string
}

export default function AdminProjectsPage() {
  const [projects, setProjects] = useState<ProjectItem[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [selectedJsonProject, setSelectedJsonProject] = useState<ProjectItem | null>(null)

  const fetchProjects = async () => {
    setLoading(true)
    try {
      const data = await projectsApi.listProjects()
      setProjects(data as ProjectItem[])
    } catch (err) {
      console.error('Failed to load generated projects:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProjects()
  }, [])

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete project "${name}"? This action cannot be undone.`)) {
      return
    }
    setDeletingId(id)
    try {
      await projectsApi.deleteProject(id)
      setProjects((prev) => prev.filter((p) => p.id !== id))
      if (selectedJsonProject?.id === id) {
        setSelectedJsonProject(null)
      }
    } catch (err) {
      alert('Failed to delete project. Please check backend logs.')
    } finally {
      setDeletingId(null)
    }
  }

  const filteredProjects = useMemo(() => {
    if (!searchQuery.trim()) return projects
    const q = searchQuery.toLowerCase()
    return projects.filter(
      (p) =>
        p.project_name?.toLowerCase().includes(q) ||
        p.id?.toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q)
    )
  }, [projects, searchQuery])

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FolderKanban className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold tracking-tight">Generated Architectural Projects</h1>
          </div>
          <p className="text-muted-foreground mt-1">
            Complete registry of all projects created across GAB-Gen, VSAI-Rectifier, ESAI, and ELIA engines.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchProjects}
            disabled={loading}
            className="flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Link href="/start" target="_blank">
            <Button size="sm" className="flex items-center gap-2 bg-primary text-primary-foreground">
              <ExternalLink className="w-4 h-4" />
              New Project
            </Button>
          </Link>
        </div>
      </div>

      {/* METRICS OVERVIEW */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-card border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Total Created Projects</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">{projects.length}</div>
            <p className="text-xs text-muted-foreground mt-1">All stored in PostgreSQL database</p>
          </CardContent>
        </Card>

        <Card className="bg-card border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">With Structural CAD Plan</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-400">
              {projects.filter((p) => p.master_json?.floor_plan?.rooms?.length > 0).length}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Vectorized floor plans generated</p>
          </CardContent>
        </Card>

        <Card className="bg-card border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Vastu Rectified Plans</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-400">
              {projects.filter((p) => p.master_json?.structural_rectification?.rectified_floor_plan).length}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Component 2 completed</p>
          </CardContent>
        </Card>

        <Card className="bg-card border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Interior / Landscape</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-purple-400">
              {projects.filter((p) => (p.master_json?.interior_layout?.placed_furniture?.length > 0 || p.master_json?.exterior_landscape?.elements?.length > 0)).length}
            </div>
            <p className="text-xs text-muted-foreground mt-1">ESAI / ELIA downstream data</p>
          </CardContent>
        </Card>
      </div>

      {/* SEARCH BAR */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by project name, ID, or description..."
            className="pl-9 bg-card border-border/60"
          />
        </div>
      </div>

      {/* PROJECTS TABLE */}
      <Card className="bg-card border-border/50 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/30 border-b border-border text-xs uppercase tracking-wider text-muted-foreground font-semibold">
              <tr>
                <th className="py-3 px-4">Project Name & ID</th>
                <th className="py-3 px-4">Geometry & Specs</th>
                <th className="py-3 px-4">Engine Pipeline Status</th>
                <th className="py-3 px-4">Revision / Date</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {loading ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-muted-foreground">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-primary" />
                    Loading architectural projects...
                  </td>
                </tr>
              ) : filteredProjects.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-muted-foreground">
                    <AlertCircle className="w-6 h-6 mx-auto mb-2 text-muted-foreground/60" />
                    No projects found matching your search.
                  </td>
                </tr>
              ) : (
                filteredProjects.map((proj) => {
                  const mj = proj.master_json || {}
                  const roomsCount = mj.floor_plan?.rooms?.length || 0
                  const doorsCount = mj.floor_plan?.doors?.length || 0
                  const windowsCount = mj.floor_plan?.windows?.length || 0
                  const hasRect = !!mj.structural_rectification?.rectified_floor_plan
                  const proc = mj.processing || {}
                  const gabStatus = proc.gab_gen?.status || 'pending'
                  const vsaiStatus = proc.vsai_rectifier?.status || 'pending'
                  const esaiStatus = proc.esai_engine?.status || 'pending'
                  const eliaStatus = proc.elia_engine?.status || 'pending'

                  return (
                    <tr key={proj.id} className="hover:bg-muted/15 transition-colors">
                      {/* Name & ID */}
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-foreground flex items-center gap-2">
                          {proj.project_name || 'Untitled Project'}
                        </div>
                        <div className="text-[11px] text-muted-foreground font-mono mt-0.5 select-all">
                          {proj.id}
                        </div>
                        {proj.description && (
                          <div className="text-xs text-muted-foreground/80 mt-1 line-clamp-1">
                            {proj.description}
                          </div>
                        )}
                      </td>

                      {/* Specs */}
                      <td className="py-3.5 px-4">
                        <div className="text-xs space-y-1">
                          <div className="flex items-center gap-1.5 text-foreground">
                            <Layers className="w-3.5 h-3.5 text-blue-400" />
                            <span>
                              {roomsCount > 0 ? (
                                <strong className="text-emerald-400">{roomsCount} Rooms</strong>
                              ) : (
                                <span className="text-muted-foreground">No rooms</span>
                              )}
                              {doorsCount > 0 && ` • ${doorsCount} Doors`}
                              {windowsCount > 0 && ` • ${windowsCount} Windows`}
                            </span>
                          </div>
                          {mj.land_info?.orientation && (
                            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                              <Compass className="w-3 h-3 text-amber-400" />
                              <span>Facing: {mj.land_info.orientation}</span>
                            </div>
                          )}
                          {hasRect && (
                            <span className="inline-block text-[10px] font-semibold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20">
                              Vastu Rectified
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Pipeline Status */}
                      <td className="py-3.5 px-4">
                        <div className="flex flex-wrap gap-1.5 text-[10px] font-medium">
                          <StatusBadge label="GAB" status={gabStatus} />
                          <StatusBadge label="VSAI" status={vsaiStatus} />
                          <StatusBadge label="ESAI" status={esaiStatus} />
                          <StatusBadge label="ELIA" status={eliaStatus} />
                        </div>
                      </td>

                      {/* Revision & Date */}
                      <td className="py-3.5 px-4 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5" />
                          <span>
                            {proj.created_at
                              ? new Date(proj.created_at).toLocaleDateString()
                              : 'Recent'}
                          </span>
                        </div>
                        <div className="text-[11px] text-muted-foreground/70 mt-0.5">
                          Rev #{proj.revision || 1}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 text-xs gap-1 border-border/60 hover:bg-muted"
                            onClick={() => setSelectedJsonProject(proj)}
                            title="Inspect Master JSON"
                          >
                            <FileCode2 className="w-3.5 h-3.5 text-blue-400" />
                            JSON
                          </Button>
                          <Link href={`/features/vsai-rectifier?projectId=${proj.id}`}>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 text-xs gap-1 text-primary hover:text-primary hover:bg-primary/10"
                              title="Open in VSAI Rectifier"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                              Open
                            </Button>
                          </Link>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={deletingId === proj.id}
                            className="h-8 text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
                            onClick={() => handleDelete(proj.id, proj.project_name)}
                            title="Delete Project"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* MASTER JSON INSPECTION MODAL */}
      {selectedJsonProject && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-xl max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-border">
              <div>
                <h3 className="font-bold text-base text-foreground flex items-center gap-2">
                  <FileCode2 className="w-5 h-5 text-primary" />
                  Master JSON: {selectedJsonProject.project_name}
                </h3>
                <p className="text-xs text-muted-foreground font-mono mt-0.5">
                  ID: {selectedJsonProject.id} • Revision #{selectedJsonProject.revision}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    const blob = new Blob(
                      [JSON.stringify(selectedJsonProject.master_json, null, 2)],
                      { type: 'application/json' }
                    )
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `${selectedJsonProject.project_name || 'project'}-master.json`
                    a.click()
                  }}
                >
                  Download JSON
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSelectedJsonProject(null)}
                >
                  Close
                </Button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-4 bg-muted/20 font-mono text-xs">
              <pre className="text-slate-300 whitespace-pre-wrap break-all">
                {JSON.stringify(selectedJsonProject.master_json, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ label, status }: { label: string; status: string }) {
  let badgeColor = 'bg-muted text-muted-foreground border-border/50'
  if (status === 'completed') {
    badgeColor = 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
  } else if (status === 'skipped') {
    badgeColor = 'bg-amber-500/15 text-amber-400 border-amber-500/30'
  } else if (status === 'processing') {
    badgeColor = 'bg-blue-500/15 text-blue-400 border-blue-500/30 animate-pulse'
  } else if (status === 'failed') {
    badgeColor = 'bg-rose-500/15 text-rose-400 border-rose-500/30'
  }

  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] uppercase font-semibold ${badgeColor}`}
    >
      {label}: {status}
    </span>
  )
}
