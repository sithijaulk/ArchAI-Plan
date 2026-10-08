"use client"
import React, { useState } from 'react'

export function Tabs({ defaultValue, children, className = "" }: any) {
  const [activeTab, setActiveTab] = useState(defaultValue)

  const mappedChildren = React.Children.map(children, (child) => {
    if (React.isValidElement(child)) {
      if (child.type === TabsList) {
        return React.cloneElement(child as any, { activeTab, setActiveTab })
      }
      if (child.type === TabsContent) {
        return React.cloneElement(child as any, { activeTab })
      }
    }
    return child
  })

  return <div className={className}>{mappedChildren}</div>
}

export function TabsList({ children, className = "", activeTab, setActiveTab }: any) {
  const mappedChildren = React.Children.map(children, (child) => {
    if (React.isValidElement(child)) {
      return React.cloneElement(child as any, { activeTab, setActiveTab })
    }
    return child
  })
  return (
    <div className={`inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground ${className}`}>
      {mappedChildren}
    </div>
  )
}

export function TabsTrigger({ value, children, activeTab, setActiveTab, className = "" }: any) {
  const isActive = activeTab === value
  return (
    <button
      onClick={() => setActiveTab(value)}
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
        isActive ? 'bg-background text-foreground shadow-sm' : 'hover:bg-background/50'
      } ${className}`}
    >
      {children}
    </button>
  )
}

export function TabsContent({ value, children, activeTab, className = "" }: any) {
  if (activeTab !== value) return null
  return <div className={`mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${className}`}>{children}</div>
}
