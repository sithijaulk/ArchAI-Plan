"use client";

import React, { Component, ReactNode, ErrorInfo } from 'react';
import { AlertTriangle, RefreshCw, Settings, Layers } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface WebGLErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  title?: string;
  className?: string;
  onRetry?: () => void;
}

interface WebGLErrorBoundaryState {
  hasError: boolean;
  errorMessage: string | null;
  supported: boolean;
}

/**
 * Checks whether WebGL / WebGL2 context can be obtained in the current browser environment.
 */
export function isWebGLAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    const gl =
      canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: false }) ||
      canvas.getContext('webgl', { failIfMajorPerformanceCaveat: false }) ||
      canvas.getContext('experimental-webgl', { failIfMajorPerformanceCaveat: false });
    return Boolean(gl && typeof (gl as any).getParameter === 'function');
  } catch {
    return false;
  }
}

export class WebGLErrorBoundary extends Component<
  WebGLErrorBoundaryProps,
  WebGLErrorBoundaryState
> {
  constructor(props: WebGLErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      errorMessage: null,
      supported: true,
    };
  }

  componentDidMount() {
    // Proactively verify WebGL context availability before Three.js / R3F initializes
    if (!isWebGLAvailable()) {
      this.setState({
        hasError: true,
        errorMessage: 'WebGL context creation is not supported or hardware acceleration is disabled in this browser.',
        supported: false,
      });
    }
  }

  static getDerivedStateFromError(error: Error): Partial<WebGLErrorBoundaryState> {
    return {
      hasError: true,
      errorMessage: error?.message || 'Error creating WebGL context.',
      supported: false,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.warn('[WebGLErrorBoundary] Caught WebGL runtime error:', error.message, errorInfo);
  }

  handleRetry = () => {
    this.setState({
      hasError: false,
      errorMessage: null,
      supported: true,
    });
    if (this.props.onRetry) {
      this.props.onRetry();
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          className={`w-full h-full min-h-[380px] flex flex-col items-center justify-center p-6 text-center bg-slate-950/95 border border-border/50 rounded-xl ${
            this.props.className || ''
          }`}
        >
          <div className="w-12 h-12 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 mb-3 shadow-lg shadow-amber-500/5">
            <AlertTriangle className="w-6 h-6" />
          </div>

          <h3 className="text-base font-semibold text-foreground mb-1">
            {this.props.title || '3D Viewport Unavailable'}
          </h3>

          <p className="text-xs text-muted-foreground max-w-md mb-4 leading-relaxed">
            WebGL context could not be created. Hardware acceleration may be disabled in your browser, or the GPU context limit was exceeded.
          </p>

          <div className="bg-slate-900/90 border border-slate-800 rounded-lg p-3.5 text-[11px] text-muted-foreground/90 max-w-md mb-4 text-left font-mono space-y-1.5">
            <div className="flex items-center gap-1.5 text-foreground font-semibold text-xs mb-1">
              <Settings className="w-3.5 h-3.5 text-primary" /> How to fix this in your browser:
            </div>
            <div>
              1. Open browser settings: <span className="text-sky-400">chrome://settings/system</span> (or Edge / Brave settings)
            </div>
            <div>
              2. Enable <span className="text-emerald-400 font-medium">&quot;Use graphics acceleration when available&quot;</span>
            </div>
            <div>3. Relaunch your browser and refresh this page.</div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={this.handleRetry}
              className="gap-2 text-xs border-border/70 hover:bg-slate-800"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry 3D View
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
