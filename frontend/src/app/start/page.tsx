"use client"

import React, { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useProjectStore } from '@/store/projectStore'
import { projectsApi } from '@/lib/api/projects'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from '@/components/ui/card'
import { ArrowRight, Loader2, Sparkles, Upload } from 'lucide-react'

export default function StartProjectPage() {
  const router = useRouter()
  const { createProject, loadProject } = useProjectStore()
  const [projectName, setProjectName] = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleCreateNew = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectName.trim() || loading) return
    setError('')
    setLoading(true)
    try {
      await createProject(projectName.trim(), description.trim() || undefined)
      router.push('/features/gab-gen')
    } catch {
      setError('Unable to create the project. Check the API connection and try again.')
      setLoading(false)
    }
  }

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setError('')
    try {
      if (!file.name.toLowerCase().endsWith('.json')) throw new Error('Select a JSON file.')
      const masterJson = JSON.parse(await file.text())
      if (!masterJson.project_name || !masterJson.processing) throw new Error('This is not a compatible Master JSON file.')
      const project = await projectsApi.createProject({ project_name: masterJson.project_name })
      const updated = await projectsApi.updateProject(project.id, { master_json: masterJson })
      loadProject(updated)
      router.push('/features/gab-gen')
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Unable to load the JSON file.')
    } finally {
      event.target.value = ''
    }
  }

  return (
    <div className="container px-4 py-24 min-h-[85vh] flex flex-col items-center justify-center">
      <div className="text-center mb-10 max-w-xl">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-medium text-primary mb-4">
          <Sparkles className="w-3.5 h-3.5" />
          Multi-Agent Spatial AI Workflow
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-3">Start a Project</h1>
        <p className="text-muted-foreground text-base leading-relaxed">
          Begin your residential design workflow starting from the boundary and floorplate generation with GAB-Gen.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full max-w-4xl">
        <Card className="bg-card/60 backdrop-blur-md border border-primary/20 shadow-xl shadow-primary/5">
          <CardHeader className="space-y-1.5">
            <CardTitle className="text-2xl font-bold">Create New Project</CardTitle>
            <CardDescription className="text-sm">Start from the beginning with GAB-Gen</CardDescription>
          </CardHeader>
          <form onSubmit={handleCreateNew}>
            <CardContent className="space-y-5">
              {error && (
                <div className="p-3 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="projectName" className="text-sm font-medium">
                  Project Name <span className="text-primary">*</span>
                </Label>
                <Input
                  id="projectName"
                  placeholder="e.g. Villa Nova Phase 1"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  disabled={loading}
                  required
                  autoFocus
                  className="bg-background/50"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description" className="text-sm font-medium">
                  Description <span className="text-xs text-muted-foreground">(Optional)</span>
                </Label>
                <Input
                  id="description"
                  placeholder="Brief description of the project"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={loading}
                  className="bg-background/50"
                />
              </div>
            </CardContent>

            <CardFooter className="pt-2 pb-6">
              <Button
                type="submit"
                className="w-full electric-glow text-base py-5"
                disabled={!projectName.trim() || loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Initializing GAB-Gen...
                  </>
                ) : (
                  <>
                    Create &amp; Continue to GAB-Gen
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </>
                )}
              </Button>
            </CardFooter>
          </form>
        </Card>

        <Card className="bg-card/30 border-border/50">
          <CardHeader className="space-y-1.5">
            <CardTitle className="text-2xl font-bold">Load Existing Project</CardTitle>
            <CardDescription className="text-sm">Upload a compatible Master JSON file to resume</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center justify-center py-8">
            <div className="w-20 h-20 rounded-full bg-muted flex items-center justify-center mb-6 text-muted-foreground border-2 border-dashed border-border">
              <Upload className="w-8 h-8" />
            </div>
            <p className="text-sm text-center text-muted-foreground mb-4">
              Drag and drop your Master JSON file here, or click to browse.
            </p>
            <input ref={fileInputRef} type="file" accept=".json,application/json" className="hidden" onChange={handleUpload} />
            <Button variant="outline" type="button" onClick={() => fileInputRef.current?.click()}>
              Select File
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
