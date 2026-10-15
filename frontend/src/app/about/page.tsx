'use client'

import { useEffect, useState } from 'react'
import { FileText, Users } from 'lucide-react'
import { aboutApi, TeamMember } from '@/lib/api/about'

type Document = { id: string; title: string; description?: string; original_filename: string; file_url: string }

export default function AboutPage() {
  const [members, setMembers] = useState<TeamMember[]>([])
  const [documents, setDocuments] = useState<Document[]>([])

  useEffect(() => {
    aboutApi.getContent().then(content => {
      setMembers(content.members || [])
      setDocuments(content.documents || [])
    }).catch(() => undefined)
  }, [])

  return (
    <div className="container px-4 py-24 max-w-5xl mx-auto min-h-screen">
      <h1 className="text-4xl md:text-5xl font-bold mb-12 text-center">About ArchAI-Plan</h1>
      <div className="prose prose-invert max-w-none space-y-12">
        <section><h2 className="text-2xl font-semibold mb-4 text-primary">Research Vision</h2><p className="text-lg text-muted-foreground leading-relaxed">ArchAI-Plan represents a paradigm shift in how computational architecture approaches residential design. By treating architectural planning not as a single generative act, but as a multi-agent negotiation of space, we aim to produce structurally sound, culturally aware, and ergonomically optimized living spaces.</p></section>
        <section><h2 className="text-2xl font-semibold mb-4 text-primary">The Problem</h2><p className="text-lg text-muted-foreground leading-relaxed">Current generative AI models in architecture often focus on pixel-based rendering rather than structured, vectorized spatial relationships. This results in visually appealing but fundamentally unbuildable designs that ignore site constraints, structural realities, cultural requirements, and human ergonomics.</p></section>
        <section><h2 className="text-2xl font-semibold mb-4 text-primary">Our Approach</h2><p className="text-lg text-muted-foreground leading-relaxed">We propose a sequential, state-driven multi-agent architecture. By separating spatial reasoning into specialized domains, each agent can focus on optimizing specific constraints without destroying the underlying architectural logic.</p></section>
        <section><h2 className="text-2xl font-semibold mb-6 text-primary">Four Research Components</h2><div className="grid grid-cols-1 md:grid-cols-2 gap-6">{[['GAB-Gen', 'Focuses on boundary interpretation, setback compliance, and initial floorplate generation based on raw land data.'], ['VSAI-Rectifier', 'Applies complex geometric constraints rooted in structural and cultural norms to adjust spatial topology.'], ['ESAI-Engine', 'Models human movement and functional clearances for future interior asset layout optimization.'], ['ELIA-Engine', 'Evaluates exterior microclimates, access paths, and shading to deploy responsive landscape strategies.']].map(([title, description], index) => <div key={title} className="p-6 bg-card/40 rounded-xl border border-border/50"><h3 className="font-bold text-lg mb-2">{index + 1}. {title}</h3><p className="text-sm text-muted-foreground">{description}</p></div>)}</div></section>
      </div>

      <section className="mt-20">
        <div className="flex items-center gap-3 mb-6"><Users className="text-primary" /><h2 className="text-2xl font-semibold text-primary">Research Team</h2></div>
        {members.length > 0 ? <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">{members.map(member => <article key={member.id} className="bg-card/40 border border-border/50 rounded-xl p-5 flex gap-4"><div className="w-20 h-20 shrink-0 rounded-full overflow-hidden bg-muted border border-border/50 flex items-center justify-center">{member.image_url ? <img src={member.image_url} alt={member.name} className="w-full h-full object-cover" /> : <Users className="text-muted-foreground" />}</div><div><h3 className="font-semibold text-lg">{member.name}</h3><p className="text-primary text-sm">{member.role}</p>{member.bio && <p className="text-sm text-muted-foreground mt-2">{member.bio}</p>}</div></article>)}</div> : <p className="text-muted-foreground">Research team profiles will be published here.</p>}
      </section>

      <section className="mt-20">
        <h2 className="text-2xl font-semibold mb-6 text-primary">Research Documents</h2>
        {documents.length > 0 ? <div className="space-y-3">{documents.map(document => <a key={document.id} href={document.file_url} target="_blank" rel="noreferrer" className="flex items-center gap-4 rounded-xl border border-border/50 bg-card/40 p-4 transition-colors hover:border-primary/60 hover:bg-card"><FileText className="w-5 h-5 text-primary shrink-0" /><span className="min-w-0"><strong className="block truncate">{document.title}</strong><span className="text-sm text-muted-foreground">{document.description || document.original_filename}</span></span></a>)}</div> : <p className="text-muted-foreground">Research documents will be published here.</p>}
      </section>
    </div>
  )
}