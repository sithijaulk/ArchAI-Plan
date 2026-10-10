export default function AboutPage() {
  return (
    <div className="container px-4 py-24 max-w-4xl mx-auto min-h-screen">
      <h1 className="text-4xl md:text-5xl font-bold mb-12 text-center">About ArchAI-Plan</h1>
      
      <div className="prose prose-invert max-w-none space-y-12">
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary">Research Vision</h2>
          <p className="text-lg text-muted-foreground leading-relaxed">
            ArchAI-Plan represents a paradigm shift in how computational architecture approaches residential design. 
            By treating architectural planning not as a single generative act, but as a multi-agent negotiation of space, 
            we aim to produce structurally sound, culturally aware, and ergonomically optimized living spaces.
          </p>
        </section>

        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary">The Problem</h2>
          <p className="text-lg text-muted-foreground leading-relaxed">
            Current generative AI models in architecture often focus on pixel-based rendering rather than structured, 
            vectorized spatial relationships. This results in visually appealing but fundamentally unbuildable designs 
            that ignore site constraints, structural realities, cultural requirements, and human ergonomics.
          </p>
        </section>

        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary">Our Approach</h2>
          <p className="text-lg text-muted-foreground leading-relaxed mb-4">
            We propose a sequential, state-driven multi-agent architecture. By separating the spatial reasoning into specialized domains, 
            each agent can focus on optimizing specific constraints without destroying the underlying architectural logic.
          </p>
        </section>

        <section>
          <h2 className="text-2xl font-semibold mb-6 text-primary">Four Research Components</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-6 bg-card/40 rounded-xl border border-border/50">
              <h3 className="font-bold text-lg mb-2">1. GAB-Gen</h3>
              <p className="text-sm text-muted-foreground">Focuses on boundary interpretation, setback compliance, and initial floorplate generation based on raw land data.</p>
            </div>
            <div className="p-6 bg-card/40 rounded-xl border border-border/50">
              <h3 className="font-bold text-lg mb-2">2. VSAI-Rectifier</h3>
              <p className="text-sm text-muted-foreground">Applies complex geometric constraints rooted in structural and cultural norms (Vastu) to adjust the spatial topology.</p>
            </div>
            <div className="p-6 bg-card/40 rounded-xl border border-border/50">
              <h3 className="font-bold text-lg mb-2">3. ESAI-Engine</h3>
              <p className="text-sm text-muted-foreground">Models human movement and functional clearances for future interior asset layout optimization.</p>
            </div>
            <div className="p-6 bg-card/40 rounded-xl border border-border/50">
              <h3 className="font-bold text-lg mb-2">4. ELIA-Engine</h3>
              <p className="text-sm text-muted-foreground">Evaluates exterior microclimates, access paths, and shading to deploy responsive landscape strategies.</p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary">Academic Context</h2>
          <p className="text-lg text-muted-foreground leading-relaxed mb-4">
            This platform serves as the central demonstration environment for the ArchAI-Plan research initiative. 
            The underlying AI algorithms and dataset training methodologies will be published in forthcoming academic papers.
          </p>
        </section>
      </div>
    </div>
  )
}
