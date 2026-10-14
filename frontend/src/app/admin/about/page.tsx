'use client'

import { useEffect, useState } from 'react'
import { aboutApi, TeamMember } from '@/lib/api/about'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, ImagePlus, Save, Trash2, Upload } from 'lucide-react'

type Document = { id: string; title: string; description?: string; original_filename: string; file_url: string }

const emptyMember = (sort_order: number): TeamMember => ({ name: '', role: '', bio: '', sort_order })

export default function AdminAboutPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [members, setMembers] = useState<TeamMember[]>([])
  const [documentTitle, setDocumentTitle] = useState('')
  const [documentDescription, setDocumentDescription] = useState('')
  const [documentFile, setDocumentFile] = useState<File | null>(null)
  const [status, setStatus] = useState('')

  const load = async () => {
    const [loadedDocuments, loadedMembers] = await Promise.all([aboutApi.getDocuments(), aboutApi.getMembers()])
    setDocuments(loadedDocuments)
    setMembers(loadedMembers)
  }

  useEffect(() => { load().catch(() => setStatus('Unable to load About content.')) }, [])

  const slots = Array.from({ length: Math.max(4, members.length) }, (_, index) => members[index] || emptyMember(index))
  const updateMember = (index: number, patch: Partial<TeamMember>) => {
    setMembers(current => {
      const next = [...current]
      next[index] = { ...(next[index] || emptyMember(index)), ...patch, sort_order: index }
      return next
    })
  }

  const uploadDocument = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!documentTitle.trim() || !documentFile) return
    try {
      await aboutApi.uploadDocument(documentTitle, documentDescription, documentFile)
      setDocumentTitle(''); setDocumentDescription(''); setDocumentFile(null)
      const input = document.getElementById('research-file') as HTMLInputElement | null
      if (input) input.value = ''
      setStatus('Research document uploaded.')
      await load()
    } catch { setStatus('Unable to upload the document.') }
  }

  const saveMember = async (index: number, image?: File) => {
    const member = slots[index]
    if (!member.name.trim() || !member.role.trim()) { setStatus('Each member needs a name and role.'); return }
    try {
      const saved = await aboutApi.saveMember(member, image)
      setMembers(current => { const next = [...current]; next[index] = saved; return next })
      setStatus(`${member.name} saved.`)
    } catch { setStatus('Unable to save this team member.') }
  }

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">About Us Management</h1>
        <p className="text-muted-foreground mt-1">Manage research documents and the four visible research team profiles.</p>
      </div>
      {status && <p className="text-sm text-primary">{status}</p>}

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Research Documents</h2>
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={uploadDocument} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] items-end">
              <div className="space-y-2"><Label htmlFor="document-title">Title</Label><Input id="document-title" value={documentTitle} onChange={event => setDocumentTitle(event.target.value)} required /></div>
              <div className="space-y-2"><Label htmlFor="document-description">Description</Label><Input id="document-description" value={documentDescription} onChange={event => setDocumentDescription(event.target.value)} /></div>
              <div className="flex gap-2"><Input id="research-file" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.md,.json,.zip" onChange={event => setDocumentFile(event.target.files?.[0] || null)} required /><Button type="submit"><Upload className="w-4 h-4 mr-2" />Upload</Button></div>
            </form>
          </CardContent>
        </Card>
        <div className="space-y-2">
          {documents.map(document => <div key={document.id} className="flex items-center justify-between gap-4 bg-card border border-border/50 rounded-lg p-4"><a href={document.file_url} target="_blank" rel="noreferrer" className="flex items-center gap-3 min-w-0 hover:text-primary"><FileText className="w-5 h-5 shrink-0" /><span className="truncate"><strong>{document.title}</strong><span className="block text-xs text-muted-foreground">{document.original_filename}</span></span></a><Button variant="ghost" size="icon" onClick={async () => { await aboutApi.deleteDocument(document.id); await load() }}><Trash2 className="w-4 h-4 text-destructive" /></Button></div>)}
          {documents.length === 0 && <p className="text-sm text-muted-foreground">No research documents uploaded yet.</p>}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Research Team</h2>
        <div className="grid gap-6 md:grid-cols-2">
          {slots.slice(0, 4).map((member, index) => <MemberCard key={member.id || index} member={member} onChange={patch => updateMember(index, patch)} onSave={image => saveMember(index, image)} />)}
        </div>
      </section>
    </div>
  )
}

function MemberCard({ member, onChange, onSave }: { member: TeamMember; onChange: (patch: Partial<TeamMember>) => void; onSave: (image?: File) => void }) {
  const [image, setImage] = useState<File>()
  const [preview, setPreview] = useState(member.image_url || '')
  useEffect(() => setPreview(member.image_url || ''), [member.image_url])
  return <Card>
    <CardHeader><CardTitle className="text-base">Member {member.sort_order + 1}</CardTitle></CardHeader>
    <CardContent className="space-y-4">
      <div className="flex gap-4 items-center"><div className="w-20 h-20 rounded-full overflow-hidden bg-muted border border-border flex items-center justify-center">{preview ? <img src={preview} alt="" className="w-full h-full object-cover" /> : <ImagePlus className="w-6 h-6 text-muted-foreground" />}</div><Input type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (file) { setImage(file); setPreview(URL.createObjectURL(file)) } }} /></div>
      <div className="space-y-2"><Label>Name</Label><Input value={member.name} onChange={event => onChange({ name: event.target.value })} /></div>
      <div className="space-y-2"><Label>Role</Label><Input value={member.role} onChange={event => onChange({ role: event.target.value })} placeholder="Supervisor / Co-Supervisor / Researcher" /></div>
      <div className="space-y-2"><Label>Bio</Label><Textarea value={member.bio || ''} onChange={event => onChange({ bio: event.target.value })} rows={3} /></div>
      <Button className="w-full" onClick={() => onSave(image)}><Save className="w-4 h-4 mr-2" />Save Member</Button>
    </CardContent>
  </Card>
}