"use client"
import React, { useState } from "react"
import { Button } from "@/components/ui/button"
import { FileImage, FileText, FileJson, Loader2 } from "lucide-react"
import html2canvas from "html2canvas"
import jsPDF from "jspdf"

interface DownloadProps {
  filename: string;
  data?: any;
  targetId?: string; // HTML element ID for canvas/pdf export
  disabled?: boolean;
}

async function captureElementToCanvas(targetElement: HTMLElement): Promise<HTMLCanvasElement> {
  // 1. If targetElement itself is a canvas (e.g. Three.js WebGL canvas), return it or copy it
  if (targetElement instanceof HTMLCanvasElement) {
    const copyCanvas = document.createElement('canvas')
    copyCanvas.width = targetElement.width
    copyCanvas.height = targetElement.height
    const ctx = copyCanvas.getContext('2d')
    if (ctx) ctx.drawImage(targetElement, 0, 0)
    return copyCanvas
  }

  // 2. If it contains a Three.js canvas in 3D view
  const nestedCanvas = targetElement.querySelector('canvas')
  const nestedSvg = targetElement.querySelector('svg')
  if (nestedCanvas instanceof HTMLCanvasElement && !nestedSvg) {
    const copyCanvas = document.createElement('canvas')
    copyCanvas.width = nestedCanvas.width || 1280
    copyCanvas.height = nestedCanvas.height || 720
    const ctx = copyCanvas.getContext('2d')
    if (ctx) {
      ctx.fillStyle = '#0f172a'
      ctx.fillRect(0, 0, copyCanvas.width, copyCanvas.height)
      ctx.drawImage(nestedCanvas, 0, 0)
    }
    return copyCanvas
  }

  // 3. If it contains an SVG element (e.g. 2D Plan View)
  if (nestedSvg) {
    try {
      const clonedSvg = nestedSvg.cloneNode(true) as SVGSVGElement
      const rect = nestedSvg.getBoundingClientRect()
      const width = Math.max(Math.round(rect.width) || 1000, 1000) * 2
      const height = Math.max(Math.round(rect.height) || 700, 700) * 2
      clonedSvg.setAttribute('width', String(width))
      clonedSvg.setAttribute('height', String(height))

      const xml = new XMLSerializer().serializeToString(clonedSvg)
      const svgBlob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' })
      const url = URL.createObjectURL(svgBlob)

      const img = new Image()
      img.crossOrigin = 'anonymous'

      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve()
        img.onerror = () => reject(new Error('SVG rasterization failed'))
        img.src = url
      })

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.fillStyle = '#09100d' // sleek CAD slate background
        ctx.fillRect(0, 0, width, height)
        ctx.drawImage(img, 0, 0, width, height)
      }
      URL.revokeObjectURL(url)
      return canvas
    } catch (svgErr) {
      console.warn('SVG-to-canvas direct capture failed, trying html2canvas fallback:', svgErr)
    }
  }

  // 4. Fallback to html2canvas with resilient options
  return await html2canvas(targetElement, {
    backgroundColor: '#09100d',
    scale: 2,
    useCORS: true,
    allowTaint: true,
    logging: false,
    ignoreElements: (element) => element.classList.contains('no-export'),
  })
}

function resolveTarget(targetId?: string): HTMLElement | null {
  if (targetId) {
    const el = document.getElementById(targetId)
    if (el && (el.offsetWidth > 0 || el.offsetHeight > 0)) return el
  }
  // Fallbacks: Look for active 2D SVG or 3D WebGL canvas in document
  const cadSvg = document.querySelector('#elia-output-preview svg') || document.querySelector('.elia-cad-canvas')
  if (cadSvg instanceof SVGElement && cadSvg.parentElement) return cadSvg.parentElement
  const webglCanvas = document.querySelector('#elia-scene-container canvas') || document.querySelector('canvas')
  if (webglCanvas instanceof HTMLCanvasElement && webglCanvas.parentElement) return webglCanvas.parentElement
  return targetId ? document.getElementById(targetId) : null
}

export function DownloadImageButton({ filename, targetId, disabled }: DownloadProps) {
  const [isExporting, setIsExporting] = useState(false)

  const handleDownload = async () => {
    const target = resolveTarget(targetId)
    if (!target) {
      alert('Unable to find output view to export image.')
      return
    }
    try {
      setIsExporting(true)
      const canvas = await captureElementToCanvas(target)
      const link = document.createElement('a')
      link.download = sanitizeFilename(filename.endsWith('.png') ? filename : `${filename}.png`)
      link.href = canvas.toDataURL('image/png')
      link.click()
    } catch (err: any) {
      console.error('Image export failed:', err)
      alert('Failed to generate PNG image: ' + (err?.message || 'Unknown error'))
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={handleDownload} disabled={disabled || isExporting}>
      {isExporting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FileImage className="w-4 h-4 mr-2" />}
      {isExporting ? 'Generating PNG...' : 'Download PNG'}
    </Button>
  )
}

export function DownloadPdfButton({ filename, targetId, disabled }: DownloadProps) {
  const [isExporting, setIsExporting] = useState(false)

  const handleDownload = async () => {
    const target = resolveTarget(targetId)
    if (!target) {
      alert('Unable to find output view to export PDF.')
      return
    }
    try {
      setIsExporting(true)
      const canvas = await captureElementToCanvas(target)
      
      const isLandscape = canvas.width >= canvas.height
      const pdf = new jsPDF({
        orientation: isLandscape ? 'landscape' : 'portrait',
        unit: 'mm',
        format: 'a4',
      })

      const pageWidth = pdf.internal.pageSize.getWidth()
      const pageHeight = pdf.internal.pageSize.getHeight()
      const margin = 10
      const availWidth = pageWidth - margin * 2
      const availHeight = pageHeight - margin * 2

      const ratio = Math.min(availWidth / canvas.width, availHeight / canvas.height)
      const imgWidth = canvas.width * ratio
      const imgHeight = canvas.height * ratio
      const posX = (pageWidth - imgWidth) / 2
      const posY = (pageHeight - imgHeight) / 2

      // Render dark page background for clean CAD look
      pdf.setFillColor(9, 16, 13)
      pdf.rect(0, 0, pageWidth, pageHeight, 'F')

      // Add image
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', posX, posY, imgWidth, imgHeight)

      // Add professional header & footer
      pdf.setTextColor(200, 220, 210)
      pdf.setFontSize(10)
      pdf.text('ARCHAI-PLAN · ELIA EXTERIOR LANDSCAPE PLAN', margin, margin - 3)
      pdf.setFontSize(8)
      pdf.setTextColor(120, 140, 130)
      pdf.text(`Generated: ${new Date().toLocaleDateString()} | Authoritative Multi-Projection CAD`, margin, pageHeight - 4)

      pdf.save(sanitizeFilename(filename.endsWith('.pdf') ? filename : `${filename}.pdf`))
    } catch (err: any) {
      console.error('PDF export failed:', err)
      alert('Failed to generate PDF: ' + (err?.message || 'Unknown error'))
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={handleDownload} disabled={disabled || isExporting}>
      {isExporting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FileText className="w-4 h-4 mr-2" />}
      {isExporting ? 'Generating PDF...' : 'Download PDF'}
    </Button>
  )
}

export function DownloadJsonButton({ filename, data }: DownloadProps) {
  const handleDownload = () => {
    if (!data) return
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = sanitizeFilename(filename.endsWith('.json') ? filename : `${filename}.json`)
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
  return (
    <Button variant="outline" size="sm" onClick={handleDownload} disabled={!data}>
      <FileJson className="w-4 h-4 mr-2" /> Download JSON
    </Button>
  )
}

function sanitizeFilename(filename: string) {
  return filename.replace(/[^a-z0-9._-]+/gi, '-').replace(/-+/g, '-').replace(/^-|-$/g, '')
}
