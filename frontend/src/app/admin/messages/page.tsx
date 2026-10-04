"use client"
import React, { useEffect, useState } from 'react'
import { contactApi } from '@/lib/api/contact'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Mail, CheckCircle2, Trash2 } from 'lucide-react'

export default function AdminMessagesPage() {
  const [messages, setMessages] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchMessages = async () => {
    try {
      const data = await contactApi.getMessages()
      setMessages(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMessages()
  }, [])

  const markAsRead = async (id: string, currentStatus: boolean) => {
    if (currentStatus) {
      await contactApi.markUnread(id)
    } else {
      await contactApi.markRead(id)
    }
    fetchMessages()
  }

  const deleteMessage = async (id: string) => {
    if (!confirm('Are you sure you want to delete this message?')) return
    await contactApi.deleteMessage(id)
    fetchMessages()
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Contact Messages</h1>
        <p className="text-muted-foreground mt-1">Manage enquiries from the public website.</p>
      </div>

      <div className="space-y-4">
        {loading ? (
          <p className="text-muted-foreground p-8 text-center bg-card rounded-lg">Loading messages...</p>
        ) : messages.length === 0 ? (
          <p className="text-muted-foreground p-8 text-center bg-card rounded-lg">No messages found.</p>
        ) : (
          messages.map((msg) => (
            <Card key={msg.id} className={`overflow-hidden transition-colors ${msg.is_read ? 'bg-card/50' : 'bg-card border-l-4 border-l-primary'}`}>
              <CardContent className="p-6">
                <div className="flex flex-col md:flex-row gap-6">
                  <div className="md:w-1/3 flex-shrink-0">
                    <div className="flex items-center gap-2 mb-2">
                      {!msg.is_read && <div className="w-2 h-2 rounded-full bg-primary" />}
                      <span className="font-semibold text-lg">{msg.full_name}</span>
                    </div>
                    <div className="space-y-1 text-sm text-muted-foreground">
                      <p className="flex items-center gap-2"><Mail className="w-3 h-3" /> {msg.email}</p>
                      {msg.phone && <p>📞 {msg.phone}</p>}
                      <p>📅 {new Date(msg.created_at).toLocaleString()}</p>
                    </div>
                  </div>
                  
                  <div className="md:w-2/3 flex flex-col">
                    <h3 className="font-bold text-foreground mb-2">{msg.subject}</h3>
                    <p className="text-muted-foreground text-sm whitespace-pre-wrap flex-1 bg-muted/30 p-4 rounded-md border border-border/50">
                      {msg.message}
                    </p>
                    <div className="flex justify-end gap-2 mt-4">
                      <Button 
                        variant="outline" 
                        size="sm" 
                        onClick={() => markAsRead(msg.id, msg.is_read)}
                        className={msg.is_read ? '' : 'border-primary text-primary hover:bg-primary/10'}
                      >
                        <CheckCircle2 className="w-4 h-4 mr-2" /> 
                        {msg.is_read ? 'Mark Unread' : 'Mark Read'}
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive hover:bg-destructive/10" onClick={() => deleteMessage(msg.id)}>
                        <Trash2 className="w-4 h-4 mr-2" /> Delete
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  )
}
