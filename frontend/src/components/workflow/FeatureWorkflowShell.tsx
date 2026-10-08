"use client"
import React, { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useProjectStore } from '@/store/projectStore'
import { CheckCircle2, Circle, ArrowRight, ArrowLeft, SkipForward } from 'lucide-react'

const steps = [
  { id: 'gab-gen', name: 'GAB-Gen', num: '01' },
  { id: 'vsai-rectifier', name: 'VSAI', num: '02' },
  { id: 'esai-engine', name: 'ESAI', num: '03' },
  { id: 'elia-engine', name: 'ELIA', num: '04' }
]

interface WorkflowShellProps {
  componentId: 'gab_gen' | 'vsai_rectifier' | 'esai_engine' | 'elia_engine';
  title: string;
  number: string;
  description: string;
  children: React.ReactNode;
  onNext?: () => void;
  onPrev?: () => void;
  onSkip?: () => void;
}

export function FeatureWorkflowShell({ 
  componentId, title, number, description, children, onNext, onPrev, onSkip 
}: WorkflowShellProps) {
  const { masterJson, componentStatuses } = useProjectStore()
  
  return (
    <div className="container px-4 py-12 max-w-6xl mx-auto">
      <div className="mb-8">
        <div className="flex items-center gap-4 mb-4">
          <span className="text-4xl font-extrabold text-primary/30">{number}</span>
          <h1 className="text-3xl font-bold">{title}</h1>
        </div>
        <p className="text-muted-foreground text-lg max-w-3xl">{description}</p>
      </div>

      {/* Stepper */}
      <div className="flex items-center justify-between mb-12 relative">
        <div className="absolute left-0 top-1/2 w-full h-[2px] bg-border -z-10"></div>
        {steps.map((step, idx) => {
          const dbId = step.id.replace('-', '_');
          const status = componentStatuses[dbId as keyof typeof componentStatuses];
          const isCompleted = status === 'completed';
          const isSkipped = status === 'skipped';
          const isActive = componentId === dbId;
          
          return (
            <div key={step.id} className="flex flex-col items-center gap-2 bg-background px-2">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 
                ${isActive ? 'border-primary bg-primary/20 text-primary' : 
                  isCompleted ? 'border-green-500 bg-green-500/20 text-green-500' : 
                  isSkipped ? 'border-orange-500 bg-orange-500/20 text-orange-500' : 'border-border bg-card text-muted-foreground'}`}>
                {isCompleted ? <CheckCircle2 className="w-5 h-5" /> : 
                 isSkipped ? <SkipForward className="w-5 h-5" /> : 
                 <span className="text-sm font-bold">{step.num}</span>}
              </div>
              <span className={`text-xs font-medium ${isActive ? 'text-primary' : 'text-muted-foreground'}`}>
                {step.name}
              </span>
            </div>
          )
        })}
      </div>

      <div className="bg-card border border-border/50 rounded-2xl shadow-lg overflow-hidden">
        {children}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between mt-8">
        <Button variant="outline" onClick={onPrev} disabled={!onPrev}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Previous
        </Button>
        <div className="flex gap-4">
          {onSkip && (
            <Button variant="ghost" onClick={onSkip}>
              Skip <SkipForward className="w-4 h-4 ml-2" />
            </Button>
          )}
          <Button onClick={onNext} disabled={!onNext} className="electric-glow">
            Continue <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </div>
      </div>
    </div>
  )
}
