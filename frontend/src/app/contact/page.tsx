"use client"
import React, { useState } from 'react'
import { contactApi } from '@/lib/api/contact'
import { settingsApi } from '@/lib/api/settings'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Mail, Phone, MapPin, CheckCircle2 } from 'lucide-react'

export default function ContactPage() {
  const [siteSettings, setSiteSettings] = useState<Record<string, string>>({})
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    phone: '',
    subject: '',
    message: ''
  })
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  React.useEffect(() => {
    settingsApi.getPublic().then(setSiteSettings).catch(() => setSiteSettings({}))
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    
    try {
      await contactApi.submitForm(formData)
      setSuccess(true)
      setFormData({ full_name: '', email: '', phone: '', subject: '', message: '' })
    } catch (err) {
      setError('Failed to send message. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container px-4 py-24 min-h-screen">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Contact ArchAI-Plan</h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Get in touch regarding academic research, platform capabilities, or institutional collaboration.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
          {/* Contact Information */}
          <div className="lg:col-span-1 space-y-8">
            <div className="bg-card/40 p-8 rounded-xl border border-border/50 h-full">
              <h3 className="text-2xl font-bold mb-6">Contact Details</h3>
              
              <div className="space-y-6">
                {siteSettings.contact_email && <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <Mail className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h4 className="font-semibold mb-1">Email</h4>
                    <p className="text-muted-foreground text-sm">{siteSettings.contact_email}</p>
                  </div>
                </div>}
                
                {siteSettings.contact_phone && <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <Phone className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h4 className="font-semibold mb-1">Phone</h4>
                    <p className="text-muted-foreground text-sm">{siteSettings.contact_phone}</p>
                  </div>
                </div>}
                
                {siteSettings.contact_address && <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <MapPin className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h4 className="font-semibold mb-1">Address</h4>
                    <p className="text-muted-foreground text-sm whitespace-pre-line">{siteSettings.contact_address}</p>
                  </div>
                </div>}
              </div>
            </div>
          </div>

          {/* Contact Form */}
          <div className="lg:col-span-2">
            <Card className="bg-card/40 border-border/50 backdrop-blur">
              <CardContent className="p-8">
                {success ? (
                  <div className="py-12 text-center flex flex-col items-center">
                    <div className="w-16 h-16 bg-primary/20 rounded-full flex items-center justify-center mb-6">
                      <CheckCircle2 className="w-8 h-8 text-primary" />
                    </div>
                    <h3 className="text-2xl font-bold mb-2">Message Sent</h3>
                    <p className="text-muted-foreground max-w-md mx-auto">
                      Thank you for contacting the ArchAI-Plan research team. We will review your enquiry and respond shortly.
                    </p>
                    <Button variant="outline" className="mt-8" onClick={() => setSuccess(false)}>
                      Send Another Message
                    </Button>
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-6">
                    <h3 className="text-2xl font-bold mb-6">Send an Enquiry</h3>
                    
                    {error && (
                      <div className="p-4 bg-destructive/10 text-destructive border border-destructive/20 rounded-md">
                        {error}
                      </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="full_name">Full Name *</Label>
                        <Input 
                          id="full_name" 
                          name="full_name" 
                          value={formData.full_name} 
                          onChange={handleChange} 
                          required 
                          className="bg-background/50"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="email">Email Address *</Label>
                        <Input 
                          id="email" 
                          name="email" 
                          type="email" 
                          value={formData.email} 
                          onChange={handleChange} 
                          required 
                          className="bg-background/50"
                        />
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="phone">Phone Number (Optional)</Label>
                        <Input 
                          id="phone" 
                          name="phone" 
                          value={formData.phone} 
                          onChange={handleChange} 
                          className="bg-background/50"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="subject">Subject *</Label>
                        <Input 
                          id="subject" 
                          name="subject" 
                          value={formData.subject} 
                          onChange={handleChange} 
                          required 
                          className="bg-background/50"
                        />
                      </div>
                    </div>
                    
                    <div className="space-y-2">
                      <Label htmlFor="message">Your Message *</Label>
                      <Textarea 
                        id="message" 
                        name="message" 
                        rows={6} 
                        value={formData.message} 
                        onChange={handleChange} 
                        required 
                        className="bg-background/50 resize-none"
                      />
                    </div>
                    
                    <Button type="submit" className="w-full md:w-auto electric-glow" disabled={loading}>
                      {loading ? 'Sending...' : 'Send Message'}
                    </Button>
                  </form>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
