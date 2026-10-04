"use client"
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Menu, X } from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { name: 'Home', href: '/' },
  { name: 'Gallery', href: '/gallery' },
  { name: 'Features', href: '/features' },
  { name: 'About Us', href: '/about' },
  { name: 'Contact Us', href: '/contact' },
]

export default function Navbar() {
  const pathname = usePathname()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        <div className="flex gap-6 md:gap-10">
          <Link href="/" className="flex items-center space-x-2">
            <span className="inline-block font-bold text-xl tracking-tight text-white">
              ArchAI<span className="text-primary">-Plan</span>
            </span>
          </Link>
          <nav className="hidden md:flex gap-6">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center text-sm font-medium transition-colors hover:text-foreground/80",
                  pathname === item.href ? "text-foreground" : "text-foreground/60"
                )}
              >
                {item.name}
              </Link>
            ))}
          </nav>
        </div>
        <div className="hidden md:flex items-center space-x-4">
          <Link href="/admin/login">
            <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-white">
              Admin Login
            </Button>
          </Link>
          <Link href="/start">
            <Button size="sm" className="electric-glow">
              Start Project
            </Button>
          </Link>
        </div>
        <button
          className="md:hidden p-2 text-foreground"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>
      
      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-border/40 bg-background">
          <nav className="container flex flex-col space-y-4 py-4">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "text-sm font-medium transition-colors",
                  pathname === item.href ? "text-foreground" : "text-foreground/60"
                )}
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.name}
              </Link>
            ))}
            <div className="pt-4 flex flex-col gap-2">
              <Link href="/start" onClick={() => setMobileMenuOpen(false)}>
                <Button className="w-full electric-glow">Start Project</Button>
              </Link>
              <Link href="/admin/login" onClick={() => setMobileMenuOpen(false)}>
                <Button variant="outline" className="w-full">Admin Login</Button>
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  )
}
