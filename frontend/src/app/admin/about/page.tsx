'use client'

import { useEffect, useState } from 'react'
import { aboutApi, TeamMember } from '@/lib/api/about'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { FileText, ImagePlus, Plus, Save, Trash2, Upload, UserCheck, Users } from 'lucide-react'

type Document = { id: string; title: string; description?: string; original_filename: string; file_url: string }

const emptySlot = (category: string, sort_order: number): TeamMember => ({
  name: '',
  role: '',
  category,
  bio: '',
  sort_order,
})

export default function AdminAboutPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [members, setMembers] = useState<TeamMember[]>([])
  const [documentTitle, setDocumentTitle] = useState('')
  const [documentDescription, setDocumentDescription] = useState('')
  const [documentFile, setDocumentFile] = useState<File | null>(null)
  const [status, setStatus] = useState('')

  // Supervisor & Co-Supervisor local draft states
  const [supervisor, setSupervisor] = useState<TeamMember>(emptySlot('supervisor', 0))
  const [coSupervisor, setCoSupervisor] = useState<TeamMember>(emptySlot('co_supervisor', 1))

  // Team members list
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([])

  const load = async () => {
    try {
      const [loadedDocuments, loadedMembers] = await Promise.all([
        aboutApi.getDocuments(),
        aboutApi.getMembers(),
      ])
      setDocuments(loadedDocuments)
      setMembers(loadedMembers)

      // Find supervisor
      const sup = loadedMembers.find(m => m.category === 'supervisor')
      setSupervisor(sup || emptySlot('supervisor', 0))

      // Find co-supervisor
      const coSup = loadedMembers.find(m => m.category === 'co_supervisor')
      setCoSupervisor(coSup || emptySlot('co_supervisor', 1))

      // Filter team members
      const tm = loadedMembers.filter(m => m.category === 'member' || !m.category)
      // Ensure at least 4 slots for team members if fewer
      const padded: TeamMember[] = Array.from(
        { length: Math.max(4, tm.length) },
        (_, i) => tm[i] || emptySlot('member', i)
      )
      setTeamMembers(padded)
    } catch {
      setStatus('Unable to load About content.')
    }
  }

  useEffect(() => {
    load()
  }, [])

  const uploadDocument = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!documentTitle.trim() || !documentFile) return
    try {
      await aboutApi.uploadDocument(documentTitle, documentDescription, documentFile)
      setDocumentTitle('')
      setDocumentDescription('')
      setDocumentFile(null)
      const input = document.getElementById('research-file') as HTMLInputElement | null
      if (input) input.value = ''
      setStatus('Research document uploaded.')
      await load()
    } catch {
      setStatus('Unable to upload the document.')
    }
  }

  const saveSupervisor = async (image?: File) => {
    if (!supervisor.name.trim() || !supervisor.role.trim()) {
      setStatus('Supervisor requires a Name and Role / Designation.')
      return
    }
    try {
      const saved = await aboutApi.saveMember({ ...supervisor, category: 'supervisor' }, image)
      setSupervisor(saved)
      setStatus(`Supervisor "${saved.name}" saved successfully.`)
      await load()
    } catch {
      setStatus('Unable to save Supervisor.')
    }
  }

  const deleteSupervisor = async () => {
    if (!supervisor.id) {
      setSupervisor(emptySlot('supervisor', 0))
      return
    }
    if (!confirm('Are you sure you want to remove the Supervisor?')) return
    try {
      await aboutApi.deleteMember(supervisor.id)
      setSupervisor(emptySlot('supervisor', 0))
      setStatus('Supervisor removed.')
      await load()
    } catch {
      setStatus('Unable to remove Supervisor.')
    }
  }

  const saveCoSupervisor = async (image?: File) => {
    if (!coSupervisor.name.trim() || !coSupervisor.role.trim()) {
      setStatus('Co-Supervisor requires a Name and Role / Designation.')
      return
    }
    try {
      const saved = await aboutApi.saveMember({ ...coSupervisor, category: 'co_supervisor' }, image)
      setCoSupervisor(saved)
      setStatus(`Co-Supervisor "${saved.name}" saved successfully.`)
      await load()
    } catch {
      setStatus('Unable to save Co-Supervisor.')
    }
  }

  const deleteCoSupervisor = async () => {
    if (!coSupervisor.id) {
      setCoSupervisor(emptySlot('co_supervisor', 1))
      return
    }
    if (!confirm('Are you sure you want to remove the Co-Supervisor?')) return
    try {
      await aboutApi.deleteMember(coSupervisor.id)
      setCoSupervisor(emptySlot('co_supervisor', 1))
      setStatus('Co-Supervisor removed.')
      await load()
    } catch {
      setStatus('Unable to remove Co-Supervisor.')
    }
  }

  const saveTeamMember = async (index: number, image?: File) => {
    const member = teamMembers[index]
    if (!member.name.trim() || !member.role.trim()) {
      setStatus('Each member requires a Name and Role.')
      return
    }
    try {
      const saved = await aboutApi.saveMember({ ...member, category: 'member', sort_order: index }, image)
      setTeamMembers(current => {
        const next = [...current]
        next[index] = saved
        return next
      })
      setStatus(`Team member "${member.name}" saved.`)
      await load()
    } catch {
      setStatus('Unable to save this team member.')
    }
  }

  const deleteTeamMember = async (index: number) => {
    const member = teamMembers[index]
    if (!member.id) {
      setTeamMembers(current => current.filter((_, i) => i !== index))
      return
    }
    if (!confirm(`Delete team member "${member.name}"?`)) return
    try {
      await aboutApi.deleteMember(member.id)
      setStatus(`Team member "${member.name}" removed.`)
      await load()
    } catch {
      setStatus('Unable to delete team member.')
    }
  }

  const addTeamMemberSlot = () => {
    setTeamMembers(current => [...current, emptySlot('member', current.length)])
  }

  return (
    <div className="space-y-12 pb-16">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">About Us Management</h1>
        <p className="text-muted-foreground mt-1">
          Manage project supervisors, co-supervisors, research team members, and research documents.
        </p>
      </div>

      {status && (
        <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg text-sm text-primary">
          {status}
        </div>
      )}

      {/* ─────────────────── SUPERVISION SECTION ─────────────────── */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <UserCheck className="w-5 h-5 text-primary" />
          <h2 className="text-2xl font-semibold">Project Supervisors</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Add the research project Supervisor and Co-Supervisor profiles displayed on the About Us page.
        </p>

        <div className="grid gap-6 md:grid-cols-2">
          {/* Main Supervisor */}
          <MemberCard
            title="Project Supervisor"
            badge="Main Supervisor"
            rolePlaceholder="e.g. Senior Lecturer / Project Supervisor"
            member={supervisor}
            onChange={patch => setSupervisor(prev => ({ ...prev, ...patch }))}
            onSave={saveSupervisor}
            onDelete={supervisor.id ? deleteSupervisor : undefined}
          />

          {/* Co-Supervisor */}
          <MemberCard
            title="Co-Supervisor"
            badge="Co-Supervisor"
            rolePlaceholder="e.g. Lecturer / Co-Supervisor"
            member={coSupervisor}
            onChange={patch => setCoSupervisor(prev => ({ ...prev, ...patch }))}
            onSave={saveCoSupervisor}
            onDelete={coSupervisor.id ? deleteCoSupervisor : undefined}
          />
        </div>
      </section>

      {/* ─────────────────── RESEARCH TEAM SECTION ─────────────────── */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-primary" />
            <h2 className="text-2xl font-semibold">Research Team Members</h2>
          </div>
          <Button variant="outline" size="sm" onClick={addTeamMemberSlot}>
            <Plus className="w-4 h-4 mr-1.5" />
            Add Member
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Configure the student researchers and their specific project components.
        </p>

        <div className="grid gap-6 md:grid-cols-2">
          {teamMembers.map((member, index) => (
            <MemberCard
              key={member.id || `member-${index}`}
              title={`Team Member ${index + 1}`}
              badge={member.role || `Member ${index + 1}`}
              rolePlaceholder="e.g. Leader / Member 1 / Researcher"
              member={member}
              onChange={patch =>
                setTeamMembers(prev => {
                  const next = [...prev]
                  next[index] = { ...next[index], ...patch }
                  return next
                })
              }
              onSave={image => saveTeamMember(index, image)}
              onDelete={member.id || teamMembers.length > 4 ? () => deleteTeamMember(index) : undefined}
            />
          ))}
        </div>
      </section>

      {/* ─────────────────── RESEARCH DOCUMENTS SECTION ─────────────────── */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" />
          <h2 className="text-2xl font-semibold">Research Documents</h2>
        </div>
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={uploadDocument} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] items-end">
              <div className="space-y-2">
                <Label htmlFor="document-title">Title</Label>
                <Input
                  id="document-title"
                  placeholder="e.g. Project Charter / Research Proposal"
                  value={documentTitle}
                  onChange={event => setDocumentTitle(event.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="document-description">Description</Label>
                <Input
                  id="document-description"
                  placeholder="Brief summary or deliverable phase"
                  value={documentDescription}
                  onChange={event => setDocumentDescription(event.target.value)}
                />
              </div>
              <div className="flex gap-2">
                <Input
                  id="research-file"
                  type="file"
                  accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.md,.json,.zip"
                  onChange={event => setDocumentFile(event.target.files?.[0] || null)}
                  required
                />
                <Button type="submit">
                  <Upload className="w-4 h-4 mr-2" />
                  Upload
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-2">
          {documents.map(document => (
            <div
              key={document.id}
              className="flex items-center justify-between gap-4 bg-card border border-border/50 rounded-lg p-4"
            >
              <a
                href={document.file_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-3 min-w-0 hover:text-primary transition-colors"
              >
                <FileText className="w-5 h-5 text-primary shrink-0" />
                <span className="truncate">
                  <strong>{document.title}</strong>
                  <span className="block text-xs text-muted-foreground">{document.original_filename}</span>
                </span>
              </a>
              <Button
                variant="ghost"
                size="icon"
                onClick={async () => {
                  if (confirm(`Delete "${document.title}"?`)) {
                    await aboutApi.deleteDocument(document.id)
                    await load()
                  }
                }}
              >
                <Trash2 className="w-4 h-4 text-destructive" />
              </Button>
            </div>
          ))}
          {documents.length === 0 && (
            <p className="text-sm text-muted-foreground">No research documents uploaded yet.</p>
          )}
        </div>
      </section>
    </div>
  )
}

function MemberCard({
  title,
  badge,
  rolePlaceholder,
  member,
  onChange,
  onSave,
  onDelete,
}: {
  title: string
  badge?: string
  rolePlaceholder: string
  member: TeamMember
  onChange: (patch: Partial<TeamMember>) => void
  onSave: (image?: File) => void
  onDelete?: () => void
}) {
  const [image, setImage] = useState<File>()
  const [preview, setPreview] = useState(member.image_url || '')

  useEffect(() => {
    setPreview(member.image_url || '')
  }, [member.image_url])

  return (
    <Card className="flex flex-col justify-between">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">{title}</CardTitle>
          <div className="flex items-center gap-2">
            {badge && (
              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                {badge}
              </span>
            )}
            {onDelete && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                onClick={onDelete}
                title="Remove"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>
        </div>
        {member.id && (
          <CardDescription className="text-xs text-muted-foreground">
            Saved in database
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Photo upload and preview */}
        <div className="flex gap-4 items-center">
          <div className="w-20 h-20 shrink-0 rounded-full overflow-hidden bg-muted border border-border flex items-center justify-center">
            {preview ? (
              <img src={preview} alt="" className="w-full h-full object-cover" />
            ) : (
              <ImagePlus className="w-6 h-6 text-muted-foreground" />
            )}
          </div>
          <div className="flex-1 space-y-1">
            <Label className="text-xs text-muted-foreground">Profile Photo</Label>
            <Input
              type="file"
              accept="image/*"
              onChange={event => {
                const file = event.target.files?.[0]
                if (file) {
                  setImage(file)
                  setPreview(URL.createObjectURL(file))
                }
              }}
            />
          </div>
        </div>

        {/* Name */}
        <div className="space-y-1.5">
          <Label className="text-xs">Full Name</Label>
          <Input
            value={member.name}
            onChange={event => onChange({ name: event.target.value })}
            placeholder="e.g. Dr. Jane Doe"
          />
        </div>

        {/* Role */}
        <div className="space-y-1.5">
          <Label className="text-xs">Role / Designation</Label>
          <Input
            value={member.role}
            onChange={event => onChange({ role: event.target.value })}
            placeholder={rolePlaceholder}
          />
        </div>

        {/* Bio */}
        <div className="space-y-1.5">
          <Label className="text-xs">Bio / Component Description</Label>
          <Textarea
            value={member.bio || ''}
            onChange={event => onChange({ bio: event.target.value })}
            placeholder="Brief profile, faculty, department or component details"
            rows={2}
          />
        </div>

        {/* Save button */}
        <Button className="w-full" onClick={() => onSave(image)}>
          <Save className="w-4 h-4 mr-2" />
          {member.id ? 'Update Profile' : 'Save Profile'}
        </Button>
      </CardContent>
    </Card>
  )
}