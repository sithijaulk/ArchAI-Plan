"use client"
import { Button } from "@/components/ui/button"
import { FileImage, FileText, FileJson } from "lucide-react"
import html2canvas from "html2canvas"
import jsPDF from "jspdf"

interface DownloadProps {
  filename: string;
  data?: any;
  targetId?: string; // HTML element ID for canvas/pdf export
  disabled?: boolean;
}

export function DownloadImageButton({ filename, targetId, disabled }: DownloadProps) {
  const handleDownload = async () => {
    const target = targetId ? document.getElementById(targetId) : null
    if (!target) return
    const canvas = await html2canvas(target)
    const link = document.createElement('a')
    link.download = sanitizeFilename(filename)
    link.href = canvas.toDataURL('image/png')
    link.click()
  }
  return (
    <Button variant="outline" size="sm" onClick={handleDownload} disabled={disabled}>
      <FileImage className="w-4 h-4 mr-2" /> Download PNG
    </Button>
  )
}

export function DownloadPdfButton({ filename, targetId, disabled }: DownloadProps) {
  const handleDownload = async () => {
    const target = targetId ? document.getElementById(targetId) : null
    if (!target) return
    const canvas = await html2canvas(target)
    const pdf = new jsPDF({ orientation: 'landscape', unit: 'px', format: [canvas.width, canvas.height] })
    pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, canvas.width, canvas.height)
    pdf.save(sanitizeFilename(filename))
  }
  return (
    <Button variant="outline" size="sm" onClick={handleDownload} disabled={disabled}>
      <FileText className="w-4 h-4 mr-2" /> Download PDF
    </Button>
  )
}

export function DownloadJsonButton({ filename, data }: DownloadProps) {
  const handleDownload = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = sanitizeFilename(filename);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
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
