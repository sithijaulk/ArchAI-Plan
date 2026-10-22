"use client"

import React, { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useProjectStore } from '@/store/projectStore'
import { projectsApi } from '@/lib/api/projects'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from '@/components/ui/card'
import { ArrowRight, Upload, CheckCircle2, Compass, Home, Sparkles, Loader2, FileJson } from 'lucide-react'
import { SpatialSummary } from '@/types/project'

interface UploadResult {
  filename: string
  file_saved_path: string | null
  spatial_summary: SpatialSummary
}

export default function StartProjectPage() {
  const router = useRouter()
  const { createProject, loadProject } = useProjectStore()
  const [projectName, setProjectName] = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
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
    } finally {
      setLoading(false)
    }
  }

  const processFile = async (file: File) => {
    if (!file) return
    setError('')
    if (!file.name.toLowerCase().endsWith('.json')) {
      setError('Please select a valid JSON file (.json).')
      return
    }

    setIsUploading(true)
    try {
      const response = await projectsApi.uploadMasterJson(file)
      loadProject(response.project)
      setUploadResult({
        filename: response.filename,
        file_saved_path: response.file_saved_path,
        spatial_summary: response.spatial_summary,
      })
    } catch (uploadError: any) {
      setError(
        uploadError?.response?.data?.detail ||
        uploadError?.message ||
        'Unable to upload the Master JSON file.'
      )
    } finally {
      setIsUploading(false)
    }
  }

  const handleUploadChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      await processFile(file)
    }
    event.target.value = ''
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) {
      await processFile(file)
    }
  }

  return (
    <div className="container px-4 py-16 min-h-[85vh] flex flex-col items-center justify-center">
      <div className="text-center mb-10 max-w-xl">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-medium text-primary mb-4">
          <Sparkles className="w-3.5 h-3.5" />
          Multi-Agent Spatial AI Workflow
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-3">Start a Project</h1>
        <p className="text-muted-foreground text-base leading-relaxed">
          Begin a new spatial analysis workflow from scratch or continue from an existing Master JSON file.
        </p>
      </div>

      {error && (
        <div className="w-full max-w-4xl mb-6 p-4 rounded-lg bg-destructive/15 border border-destructive/30 text-destructive text-sm">
          {error}
        </div>
      )}

      {/* Success Preview Card when JSON is uploaded */}
      {uploadResult && (
        <Card className="w-full max-w-4xl mb-8 border-green-500/30 bg-card/60 backdrop-blur shadow-xl animate-in fade-in slide-in-from-top-4 duration-300">
          <CardHeader className="pb-3 border-b border-border/40">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-full bg-green-500/10 text-green-500">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <div>
                  <CardTitle className="text-lg text-foreground flex items-center gap-2">
                    Master JSON Uploaded Successfully
                  </CardTitle>
                  <CardDescription className="text-xs text-muted-foreground">
                    File: <span className="font-mono text-primary">{uploadResult.filename}</span>
                    {uploadResult.file_saved_path && (
                      <span className="ml-2 text-muted-foreground">
                        (Stored at: <code className="bg-muted px-1 rounded">{uploadResult.file_saved_path}</code>)
                      </span>
                    )}
                  </CardDescription>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 flex items-center gap-1">
                  <Sparkles className="w-3.5 h-3.5" /> Spatial Metadata Ready
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-4 pb-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-3 rounded-lg bg-muted/40 border border-border/40">
                <div className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                  <Compass className="w-4 h-4 text-primary" /> Orientation &amp; Road
                </div>
                <div className="font-medium text-sm">
                  {uploadResult.spatial_summary.orientation}
                </div>
                <div className="text-xs text-muted-foreground">
                  Facing: {uploadResult.spatial_summary.road_facing}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-muted/40 border border-border/40">
                <div className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                  <Home className="w-4 h-4 text-primary" /> Floor Plan Geometry
                </div>
                <div className="font-medium text-sm">
                  {uploadResult.spatial_summary.room_count} Rooms Detected
                </div>
                <div className="text-xs text-muted-foreground">
                  {uploadResult.spatial_summary.structural_elements_count} Structural elements
                </div>
              </div>

              <div className="p-3 rounded-lg bg-muted/40 border border-border/40">
                <div className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                  <FileJson className="w-4 h-4 text-primary" /> Land Area
                </div>
                <div className="font-medium text-sm">
                  {uploadResult.spatial_summary.area_sqft ? `${uploadResult.spatial_summary.area_sqft.toLocaleString()} sqft` : 'Geometry Provided'}
                </div>
                <div className="text-xs text-muted-foreground">
                  {uploadResult.spatial_summary.boundary_points_count} Boundary points
                </div>
              </div>
            </div>

            {uploadResult.spatial_summary.rooms.length > 0 && (
              <div className="mt-4 pt-3 border-t border-border/30">
                <div className="text-xs text-muted-foreground mb-2">Detected Rooms:</div>
                <div className="flex flex-wrap gap-1.5">
                  {uploadResult.spatial_summary.rooms.map((room, idx) => (
                    <span key={idx} className="text-xs px-2.5 py-1 rounded bg-secondary/70 text-secondary-foreground border border-border/50">
                      {room.name || room.type} ({room.points_count} pts)
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
          <CardFooter className="pt-2 pb-4 flex flex-col sm:flex-row gap-3 justify-end border-t border-border/30 bg-muted/10">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push('/features/gab-gen')}
            >
              Go to GAB-Gen (Component 01)
            </Button>
            <Button
              size="sm"
              className="electric-glow"
              onClick={() => router.push('/features/vsai-rectifier')}
            >
              Continue to VSAI-Rectifier (Component 02) <ArrowRight className="w-4 h-4 ml-1.5" />
            </Button>
          </CardFooter>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full max-w-4xl">
        <Card className="bg-card/50 backdrop-blur border-primary/20 shadow-lg shadow-primary/5">
          <CardHeader>
            <CardTitle>Create New Project</CardTitle>
            <CardDescription>Start from the beginning with GAB-Gen</CardDescription>
          </CardHeader>
          <form onSubmit={handleCreateNew}>
            <CardContent className="space-y-4">
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

        <Card 
          className={`bg-card/30 border-border/50 transition-all ${
            isDragging ? 'border-primary ring-2 ring-primary/20 bg-primary/5' : ''
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <CardHeader>
            <CardTitle>Load Existing Project</CardTitle>
            <CardDescription>Upload a compatible Master JSON file to resume</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center justify-center py-8">
            <div className={`w-20 h-20 rounded-full flex items-center justify-center mb-6 transition-colors border-2 border-dashed ${
              isDragging ? 'bg-primary/20 border-primary text-primary' : 'bg-muted border-border text-muted-foreground'
            }`}>
              {isUploading ? (
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
              ) : (
                <Upload className="w-8 h-8" />
              )}
            </div>
            <p className="text-sm text-center text-muted-foreground mb-4">
              {isUploading
                ? 'Uploading and processing Master JSON...'
                : 'Drag and drop your Master JSON file here, or click to browse.'}
            </p>
            <input 
              ref={fileInputRef} 
              type="file" 
              accept=".json,application/json" 
              className="hidden" 
              onChange={handleUploadChange} 
              disabled={isUploading}
            />
            <Button 
              variant="outline" 
              type="button" 
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Uploading...
                </>
              ) : (
                'Select File'
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
