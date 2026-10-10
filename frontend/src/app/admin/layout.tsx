"use client"
import React, { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { authApi } from '@/lib/api/auth'
import { LayoutDashboard, Images, Mail, Settings, LogOut, Menu, X, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [isMobileOpen, setIsMobileOpen] = useState(false)
  const [authorized, setAuthorized] = useState<boolean | null>(null)

  React.useEffect(() => {
    if (pathname === '/admin/login') return
    authApi.getMe().then(() => setAuthorized(true)).catch(() => router.replace('/admin/login'))
  }, [pathname, router])
  
  if (pathname === '/admin/login') {
    return <>{children}</>
  }
  if (!authorized) return null

  const handleLogout = async () => {
    try {
      await authApi.logout()
    } catch(e) {}
    router.push('/admin/login')
  }

  const navItems = [
    { name: 'Dashboard', href: '/admin', icon: <LayoutDashboard size={20} /> },
    { name: 'Gallery Projects', href: '/admin/gallery', icon: <Images size={20} /> },
    { name: 'Messages', href: '/admin/messages', icon: <Mail size={20} /> },
    { name: 'Website Settings', href: '/admin/settings', icon: <Settings size={20} /> },
  ]

  return (
    <div className="flex min-h-screen bg-muted/20">
      <div className="md:hidden fixed top-4 right-4 z-50">
        <Button variant="outline" size="icon" onClick={() => setIsMobileOpen(!isMobileOpen)} className="bg-background">
          {isMobileOpen ? <X /> : <Menu />}
        </Button>
      </div>

      <aside className={cn(
        "fixed inset-y-0 left-0 z-40 w-64 bg-card border-r border-border transition-transform duration-300 md:translate-x-0 md:static flex flex-col",
        isMobileOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="p-6 border-b border-border/50 flex flex-col gap-1">
          <span className="font-bold text-xl tracking-tight text-white">ArchAI-Plan</span>
          <span className="text-xs font-semibold text-primary">ADMIN CONSOLE</span>
        </div>
        
        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (pathname.startsWith(`${item.href}/`) && item.href !== '/admin');
            return (
              <Link key={item.href} href={item.href} onClick={() => setIsMobileOpen(false)}>
                <div className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                  isActive 
                    ? "bg-primary text-primary-foreground" 
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}>
                  {item.icon}
                  {item.name}
                </div>
              </Link>
            )
          })}
        </nav>
        
        <div className="p-4 border-t border-border/50 space-y-2">
          <a href="/" target="_blank" rel="noopener noreferrer">
            <Button variant="outline" className="w-full justify-start text-muted-foreground hover:text-foreground">
              <ExternalLink size={16} className="mr-2" /> View Website
            </Button>
          </a>
          <Button variant="ghost" className="w-full justify-start text-muted-foreground hover:text-foreground" onClick={handleLogout}>
            <LogOut size={16} className="mr-2" /> Logout
          </Button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-h-screen overflow-x-hidden">
        <div className="flex-1 p-4 md:p-8 pt-16 md:pt-8 max-w-7xl mx-auto w-full">
          {children}
        </div>
      </main>
    </div>
  )
}
