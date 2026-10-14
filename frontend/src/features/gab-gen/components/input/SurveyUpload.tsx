"use client";

import React, { useRef, useState } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface SurveyUploadProps {
  onUploadSuccess: (fileMeta: any) => void;
  isUploading: boolean;
  uploadedMeta: any;
  onUploadFile: (file: File) => Promise<void>;
}

export const SurveyUpload: React.FC<SurveyUploadProps> = ({
  isUploading,
  uploadedMeta,
  onUploadFile,
}) => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const validateAndSet = (file: File) => {
    setErrorMsg(null);
    const validExtensions = ['.jpg', '.jpeg', '.png', '.pdf'];
    const name = file.name.toLowerCase();
    const isValid = validExtensions.some(ext => name.endsWith(ext));

    if (!isValid) {
      setErrorMsg("Please upload a valid survey plan file (.jpg, .jpeg, .png, or .pdf).");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setErrorMsg("File exceeds the maximum 15MB limit.");
      return;
    }

    setSelectedFile(file);
    onUploadFile(file).catch((err) => {
      setErrorMsg(err.response?.data?.detail || "Upload failed. Please check the file and try again.");
    });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSet(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      validateAndSet(e.target.files[0]);
    }
  };

  return (
    <div className="space-y-4">
      <div
        className={`relative border-2 border-dashed rounded-xl p-6 transition-all duration-200 text-center flex flex-col items-center justify-center min-h-[220px] ${
          dragActive
            ? "border-primary bg-primary/10 shadow-lg"
            : "border-border/70 bg-card/40 hover:bg-card/70 hover:border-border"
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.pdf"
          className="hidden"
          onChange={handleChange}
        />

        <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3">
          <UploadCloud className="w-6 h-6" />
        </div>

        <p className="font-semibold text-sm mb-1 text-foreground">
          Upload Deed / Survey Plan
        </p>
        <p className="text-xs text-muted-foreground max-w-xs mb-4">
          Drag & drop your survey plan image or PDF, or click browse (up to 15MB)
        </p>

        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
          className="text-xs"
        >
          {isUploading ? "Uploading..." : "Browse Files"}
        </Button>
      </div>

      {errorMsg && (
        <div className="flex items-center gap-2 p-3 text-xs bg-destructive/10 text-destructive rounded-lg border border-destructive/20">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {uploadedMeta && (
        <div className="flex items-center justify-between p-3 rounded-xl bg-card border border-border/80 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground truncate max-w-[200px]">
                {uploadedMeta.original_filename || selectedFile?.name}
              </p>
              <p className="text-[10px] text-muted-foreground">
                {uploadedMeta.size_bytes ? `${(uploadedMeta.size_bytes / 1024).toFixed(1)} KB` : "Uploaded"} • Ready for extraction
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1 text-emerald-500 text-xs font-medium">
            <CheckCircle className="w-4 h-4" />
            <span>Uploaded</span>
          </div>
        </div>
      )}

      <div className="p-3 bg-muted/40 rounded-lg border border-border/40 text-[11px] text-muted-foreground">
        <p className="font-medium text-foreground mb-0.5">Stage-1 Notice:</p>
        <p>
          Automatic OCR survey recognition will activate in Stage 2. For Stage 1,
          boundary extraction is driven deterministically via manual verification or reference parcel fixtures.
        </p>
      </div>
    </div>
  );
};
