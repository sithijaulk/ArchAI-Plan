"use client"
import React, { createContext, useContext, useState } from 'react'

interface TabsContextValue {
  activeTab: string
  setActiveTab: (val: string) => void
}

const TabsContext = createContext<TabsContextValue | undefined>(undefined)

export function Tabs({
  defaultValue,
  value,
  onValueChange,
  children,
  className = "",
}: {
  defaultValue?: string
  value?: string
  onValueChange?: (value: string) => void
  children?: React.ReactNode
  className?: string
}) {
  const [internalTab, setInternalTab] = useState(defaultValue || "")
  const isControlled = value !== undefined
  const activeTab = isControlled ? value : internalTab

  const handleTabChange = (val: string) => {
    if (!isControlled) {
      setInternalTab(val)
    }
    if (onValueChange) {
      onValueChange(val)
    }
  }

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab: handleTabChange }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({
  children,
  className = "",
}: {
  children?: React.ReactNode
  className?: string
  activeTab?: string
  setActiveTab?: (val: string) => void
}) {
  return (
    <div
      className={`inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground ${className}`}
    >
      {children}
    </div>
  )
}

export function TabsTrigger({
  value,
  children,
  className = "",
  disabled = false,
}: {
  value: string
  children?: React.ReactNode
  className?: string
  disabled?: boolean
  activeTab?: string
  setActiveTab?: (val: string) => void
}) {
  const context = useContext(TabsContext)
  const isActive = context?.activeTab === value

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => context?.setActiveTab(value)}
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
        isActive ? 'bg-background text-foreground shadow-sm' : 'hover:bg-background/50 text-muted-foreground'
      } ${disabled ? 'pointer-events-none opacity-50' : ''} ${className}`}
    >
      {children}
    </button>
  )
}

export function TabsContent({
  value,
  children,
  className = "",
  id,
}: {
  value: string
  children?: React.ReactNode
  className?: string
  id?: string
  activeTab?: string
}) {
  const context = useContext(TabsContext)
  if (context?.activeTab !== value) return null

  return (
    <div
      id={id}
      className={`mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${className}`}
    >
      {children}
    </div>
  )
}
