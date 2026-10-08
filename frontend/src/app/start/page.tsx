"use client"
import React, { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useProjectStore } from '@/store/projectStore'
import { projectsApi } from '@/lib/api/projects'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from '@/components/ui/card'
import { ArrowRight, Upload } from 'lucide-react'

export default function StartProjectPage() {
  const router = useRouter()
  const { createProject, loadProject } = useProjectStore()
  const [projectName, setProjectName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleCreateNew = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectName.trim()) return
    setError('')
    try {
      await createProject(projectName, description)
      router.push('/features/gab-gen')
    } catch {
      setError('Unable to create the project. Check the API connection and try again.')
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
    <div className="container px-4 py-24 min-h-[80vh] flex flex-col items-center justify-center">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4">Start a Project</h1>
        <p className="text-muted-foreground max-w-xl">
          Begin a new spatial analysis workflow from scratch or continue from an existing Master JSON file.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full max-w-4xl">
        <Card className="bg-card/50 backdrop-blur border-primary/20 shadow-lg shadow-primary/5">
          <CardHeader>
            <CardTitle>Create New Project</CardTitle>
            <CardDescription>Start from the beginning with GAB-Gen</CardDescription>
          </CardHeader>
          <form onSubmit={handleCreateNew}>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="projectName">Project Name</Label>
                <Input 
                  id="projectName" 
                  placeholder="e.g. Villa Nova Phase 1" 
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description (Optional)</Label>
                <Input 
                  id="description" 
                  placeholder="Brief description of the project"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
            </CardContent>
            <CardFooter>
              <Button type="submit" className="w-full electric-glow" disabled={!projectName.trim()}>
                Create & Continue to GAB-Gen <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </CardFooter>
          </form>
        </Card>

        <Card className="bg-card/30 border-border/50">
          <CardHeader>
            <CardTitle>Load Existing Project</CardTitle>
            <CardDescription>Upload a compatible Master JSON file to resume</CardDescription>
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
