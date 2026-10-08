import { useEffect, useState } from 'react'
import { settingsApi } from '@/lib/api/settings'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

const fields = [['contact_email', 'Contact email'], ['contact_phone', 'Contact phone'], ['contact_address', 'Contact address'], ['facebook_url', 'Facebook URL'], ['linkedin_url', 'LinkedIn URL']] as const

export default function AdminSettingsPage() {
  const [values, setValues] = useState<Record<string, string>>({ site_description: '' })
  const [status, setStatus] = useState('')

  useEffect(() => {
    settingsApi.getAdmin().then(setValues).catch(() => setStatus('Unable to load settings.'))
  }, [])

  const update = (key: string, value: string) => setValues((current) => ({ ...current, [key]: value }))
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    try {
      await settingsApi.update(values)
      setStatus('Settings saved.')
    } catch {
      setStatus('Unable to save settings.')
    }
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Website Settings</h1>
        <p className="text-muted-foreground mt-1">Manage public contact details served by the API.</p>
      </div>
      <form onSubmit={save} className="space-y-5 bg-card border border-border/50 rounded-xl p-8">
        {fields.map(([key, label]) => <div key={key} className="space-y-2"><Label htmlFor={key}>{label}</Label><Input id={key} value={values[key] ?? ''} onChange={(event) => update(key, event.target.value)} /></div>)}
        <div className="space-y-2"><Label htmlFor="site_description">Site description</Label><Textarea id="site_description" value={values.site_description ?? ''} onChange={(event) => update('site_description', event.target.value)} rows={5} /></div>
        <div className="flex items-center gap-4"><Button type="submit">Save settings</Button>{status && <span className="text-sm text-muted-foreground">{status}</span>}</div>
      </form>
    </div>
  )
}
