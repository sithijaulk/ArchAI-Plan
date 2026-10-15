"use client"
import React, { useEffect, useState } from 'react'
import { adminApi } from '@/lib/api/admin'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Images, Mail, Eye, Activity } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<any>(null)
  
  useEffect(() => {
    adminApi.getStats().then(data => setStats(data)).catch(console.error)
  }, [])

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard Overview</h1>
        <p className="text-muted-foreground mt-2">Welcome to the ArchAI-Plan administrative console.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Total Projects" value={stats?.totalProjects || 0} subtitle={`${stats?.publishedProjects || 0} published`} icon={<Images className="h-4 w-4 text-muted-foreground" />} />
        <StatCard title="Published" value={stats?.publishedProjects || 0} subtitle="Live on public gallery" icon={<Eye className="h-4 w-4 text-green-500" />} />
        <StatCard title="Gallery Images" value={stats?.totalImages || 0} subtitle="Across all projects" icon={<Activity className="h-4 w-4 text-blue-500" />} />
        <StatCard title="Unread Messages" value={stats?.unreadMessages || 0} subtitle="From contact form" icon={<Mail className="h-4 w-4 text-orange-500" />} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="bg-card">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base font-semibold">Recent Projects</CardTitle>
            <Link href="/admin/gallery">
              <Button variant="ghost" size="sm" className="text-xs h-8">View All</Button>
            </Link>
          </CardHeader>
          <CardContent>
            {stats?.recentProjects && stats.recentProjects.length > 0 ? (
              <div className="space-y-4">
                {stats.recentProjects.map((p: any) => (
                  <div key={p.id} className="flex items-center justify-between border-b border-border/50 pb-2 last:border-0 last:pb-0">
                    <div className="truncate pr-4">
                      <p className="text-sm font-medium truncate">{p.title}</p>
                      <p className="text-xs text-muted-foreground">{new Date(p.created_at).toLocaleDateString()}</p>
                    </div>
                    <div>
                      {p.published ? 
                        <span className="text-[10px] uppercase font-bold text-green-500 bg-green-500/10 px-2 py-1 rounded">Published</span> : 
                        <span className="text-[10px] uppercase font-bold text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded">Draft</span>
                      }
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">No projects found.</p>
            )}
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base font-semibold">Recent Messages</CardTitle>
            <Link href="/admin/messages">
              <Button variant="ghost" size="sm" className="text-xs h-8">View All</Button>
            </Link>
          </CardHeader>
          <CardContent>
            {stats?.recentMessages && stats.recentMessages.length > 0 ? (
              <div className="space-y-4">
                {stats.recentMessages.map((m: any) => (
                  <div key={m.id} className="flex items-center justify-between border-b border-border/50 pb-2 last:border-0 last:pb-0">
                    <div className="truncate pr-4">
                      <p className={`text-sm truncate ${m.is_read ? 'text-muted-foreground' : 'font-medium'}`}>{m.subject}</p>
                      <p className="text-xs text-muted-foreground">{m.full_name}</p>
                    </div>
                    <div>
                      {!m.is_read && <div className="w-2 h-2 rounded-full bg-primary"></div>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">No recent messages.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function StatCard({ title, value, subtitle, icon }: any) {
  return (
    <Card className="bg-card border-border/50">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </CardContent>
    </Card>
  )
}
