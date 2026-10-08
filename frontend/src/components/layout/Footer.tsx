import Link from 'next/link'

export default function Footer() {
  return (
    <footer className="border-t border-border/40 bg-background pt-16 pb-8">
      <div className="container grid grid-cols-1 md:grid-cols-4 gap-8">
        <div className="md:col-span-1">
          <Link href="/" className="inline-block mb-4 font-bold text-xl tracking-tight text-white">
            ArchAI<span className="text-primary">-Plan</span>
          </Link>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
            A multi-agent spatial AI architecture designed to transform residential spatial information into structured, optimized and interactive design outputs.
          </p>
        </div>
        
        <div>
          <h4 className="font-semibold mb-4 text-foreground">Navigation</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/" className="hover:text-primary transition-colors">Home</Link></li>
            <li><Link href="/gallery" className="hover:text-primary transition-colors">Gallery</Link></li>
            <li><Link href="/features" className="hover:text-primary transition-colors">Features</Link></li>
            <li><Link href="/about" className="hover:text-primary transition-colors">About Us</Link></li>
            <li><Link href="/contact" className="hover:text-primary transition-colors">Contact Us</Link></li>
          </ul>
        </div>
        
        <div>
          <h4 className="font-semibold mb-4 text-foreground">Features</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/features/gab-gen" className="hover:text-primary transition-colors">GAB-Gen</Link></li>
            <li><Link href="/features/vsai-rectifier" className="hover:text-primary transition-colors">VSAI-Rectifier</Link></li>
            <li><Link href="/features/esai-engine" className="hover:text-primary transition-colors">ESAI-Engine</Link></li>
            <li><Link href="/features/elia-engine" className="hover:text-primary transition-colors">ELIA-Engine</Link></li>
          </ul>
        </div>
        
        <div>
          <h4 className="font-semibold mb-4 text-foreground">Legal & Research</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/privacy" className="hover:text-primary transition-colors">Privacy Policy</Link></li>
            <li><Link href="/terms" className="hover:text-primary transition-colors">Terms of Use</Link></li>
            <li><span className="text-muted-foreground/60">Research Prototype</span></li>
          </ul>
        </div>
      </div>
      
      <div className="container mt-12 pt-8 border-t border-border/40 text-center text-sm text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} ArchAI-Plan Research Platform. All rights reserved.</p>
      </div>
    </footer>
  )
}
