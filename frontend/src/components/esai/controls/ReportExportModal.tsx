'use client';

import React, { useState, useEffect } from 'react';
import { esaiApi } from '@/lib/api/esai';
import {
  FloorDTO,
  RoomDTO,
  ReportScope,
  ReportMode,
  ReportSection,
  PdfReportRequest,
  ReportOptionsResponse,
} from '@/types/esai';

interface ReportExportModalProps {
  projectId: string;
  projectName?: string;
  floors: FloorDTO[];
  selectedFloorId: string | null;
  selectedRoomId: string | null;
  isOpen: boolean;
  onClose: () => void;
  hasUnsavedChanges?: boolean;
  onSaveFirst?: () => Promise<any>;
  captureCurrent3DView?: () => string | null; // Returns base64 data URL from Three.js canvas
}

export const ReportExportModal: React.FC<ReportExportModalProps> = ({
  projectId,
  projectName = 'Project',
  floors,
  selectedFloorId,
  selectedRoomId,
  isOpen,
  onClose,
  hasUnsavedChanges = false,
  onSaveFirst,
  captureCurrent3DView,
}) => {
  const [scope, setScope] = useState<ReportScope>('building');
  const [mode, setMode] = useState<ReportMode>('draft');
  const [targetFloorId, setTargetFloorId] = useState<string>(selectedFloorId || (floors[0]?.floor_id || ''));
  const [targetRoomId, setTargetRoomId] = useState<string>(selectedRoomId || '');
  const [include2D, setInclude2D] = useState<boolean>(true);
  const [include3D, setInclude3D] = useState<boolean>(true);
  const [authorName, setAuthorName] = useState<string>('ArchAI-Plan ESAI-Engine');
  const [customNotes, setCustomNotes] = useState<string>('');
  const [selectedSections, setSelectedSections] = useState<Set<ReportSection>>(
    new Set<ReportSection>([
      'cover',
      'project_overview',
      'layout_drawings',
      'furniture_schedule',
      'electrical_schedule',
      'plumbing_schedule',
      'finish_schedule',
      'ergonomic_validation',
      'optimization_summary',
      'disclaimers',
    ])
  );

  const [loading, setLoading] = useState<boolean>(false);
  const [optionsLoading, setOptionsLoading] = useState<boolean>(false);
  const [optionsData, setOptionsData] = useState<ReportOptionsResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Load report options and staleness audit from API
  useEffect(() => {
    if (!isOpen) return;
    setErrorMessage(null);
    setSuccessMessage(null);
    setOptionsLoading(true);

    esaiApi
      .getReportOptions(projectId)
      .then((data) => {
        setOptionsData(data);
        if (data.staleness?.is_stale) {
          // If design is stale, default to draft mode so user is not blocked
          setMode('draft');
        }
      })
      .catch((err) => {
        console.error('Failed to load report options:', err);
      })
      .finally(() => setOptionsLoading(false));
  }, [isOpen, projectId]);

  // Sync target floor / room when selection changes
  useEffect(() => {
    if (selectedFloorId) setTargetFloorId(selectedFloorId);
    if (selectedRoomId) setTargetRoomId(selectedRoomId);
  }, [selectedFloorId, selectedRoomId]);

  if (!isOpen) return null;

  const currentFloorRooms: RoomDTO[] = targetFloorId
    ? floors.find((f) => f.floor_id === targetFloorId)?.rooms || []
    : floors.flatMap((f) => f.rooms);

  const toggleSection = (sec: ReportSection) => {
    const next = new Set(selectedSections);
    if (next.has(sec)) {
      next.delete(sec);
    } else {
      next.add(sec);
    }
    setSelectedSections(next);
  };

  const handleDownloadPdf = async () => {
    try {
      setLoading(true);
      setErrorMessage(null);
      setSuccessMessage(null);

      // 1. Capture 3D view snapshot if requested
      const captures: Record<string, string> = {};
      if (include3D && captureCurrent3DView && selectedRoomId) {
        const snap = captureCurrent3DView();
        if (snap) {
          captures[selectedRoomId] = snap;
        }
      }

      const req: PdfReportRequest = {
        scope,
        mode,
        target_floor_id: scope === 'floor' ? targetFloorId : undefined,
        target_room_id: scope === 'room' ? (targetRoomId || currentFloorRooms[0]?.room_id) : undefined,
        sections: Array.from(selectedSections),
        include_2d_drawings: include2D,
        include_3d_views: include3D,
        view_captures: captures,
        author_name: authorName,
        notes: customNotes || undefined,
      };

      const blob = await esaiApi.downloadPdfReport(projectId, req);

      // Trigger browser download
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const cleanProj = projectName.replace(/[^a-zA-Z0-9_\-]/g, '_');
      link.download = `ESAI_Report_${cleanProj}_${scope}_${mode}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      setSuccessMessage('Professional Interior Design PDF report generated and downloaded successfully!');
    } catch (err: any) {
      console.error('PDF Export failed:', err);
      let message = 'Failed to generate PDF report. Please verify project design status.';
      try {
        if (err.response?.data instanceof Blob) {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          message = parsed.detail?.message || (typeof parsed.detail === 'string' ? parsed.detail : message);
        } else if (err.response?.data?.detail) {
          const detail = err.response.data.detail;
          message = typeof detail === 'object' ? detail.message || JSON.stringify(detail) : detail;
        }
      } catch (e) {
        // fallback to default message
      }
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  };

  const handleExportJson = async () => {
    try {
      setLoading(true);
      setErrorMessage(null);
      setSuccessMessage(null);

      const req: PdfReportRequest = {
        scope,
        mode,
        target_floor_id: scope === 'floor' ? targetFloorId : undefined,
        target_room_id: scope === 'room' ? (targetRoomId || currentFloorRooms[0]?.room_id) : undefined,
      };

      const data = await esaiApi.exportReportData(projectId, req);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const cleanProj = projectName.replace(/[^a-zA-Z0-9_\-]/g, '_');
      link.download = `ESAI_Export_${cleanProj}_${scope}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      setSuccessMessage('Structured ESAI design JSON exported successfully!');
    } catch (err: any) {
      console.error('JSON Export failed:', err);
      setErrorMessage('Failed to export structured JSON data.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <span className="text-cyan-400">ArchAI-Plan</span>
              <span className="text-slate-400 text-sm">| Professional Report & Export</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Export verified room schedules, MEP provisions, 2D vector layouts, and GA provenance to PDF.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5 overflow-y-auto flex-1 text-xs text-slate-300">
          {/* Unsaved Changes Alert */}
          {hasUnsavedChanges && (
            <div className="bg-amber-950/40 border border-amber-600/50 rounded-xl p-3 flex items-start justify-between gap-3 text-amber-200">
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold text-sm">⚠</span>
                <div>
                  <div className="font-semibold text-amber-300">Unsaved Customization Edits Detected</div>
                  <div className="text-[11px] text-amber-200/80 mt-0.5">
                    The report is derived strictly from saved project designs. Your unsaved Phase 7 edits will not be in the PDF until saved.
                  </div>
                </div>
              </div>
              {onSaveFirst && (
                <button
                  onClick={async () => {
                    await onSaveFirst();
                    setSuccessMessage('Changes saved! Now exporting updated design.');
                  }}
                  className="px-2.5 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold rounded-md transition text-xs shrink-0"
                >
                  Save Now
                </button>
              )}
            </div>
          )}

          {/* Staleness Warning Banner */}
          {optionsData?.staleness?.is_stale && (
            <div className="bg-rose-950/30 border border-rose-600/40 rounded-xl p-3 text-rose-200">
              <div className="font-semibold text-rose-300 flex items-center gap-1.5">
                <span>⚠</span> Structural Geometry Staleness Detected
              </div>
              <div className="text-[11px] text-rose-200/80 mt-1">
                The authoritative floor plan was modified after this interior layout was saved. Final validated PDF export is blocked. You may export in <strong>Draft Mode</strong> with prominent staleness watermarks.
              </div>
            </div>
          )}

          {/* Scope & Mode Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Report Scope */}
            <div className="bg-slate-800/60 p-3.5 rounded-xl border border-slate-800">
              <label className="block text-slate-300 font-semibold mb-2">Report Scope</label>
              <div className="flex gap-2">
                {(['building', 'floor', 'room'] as ReportScope[]).map((sc) => (
                  <button
                    key={sc}
                    onClick={() => setScope(sc)}
                    className={`flex-1 py-1.5 rounded-lg border font-medium capitalize transition ${
                      scope === sc
                        ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50'
                        : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                    }`}
                  >
                    {sc}
                  </button>
                ))}
              </div>

              {scope === 'floor' && (
                <div className="mt-3">
                  <label className="block text-slate-400 text-[11px] mb-1">Select Floor:</label>
                  <select
                    value={targetFloorId}
                    onChange={(e) => setTargetFloorId(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
                  >
                    {floors.map((f) => (
                      <option key={f.floor_id} value={f.floor_id}>
                        {f.floor_name || f.floor_id} ({f.rooms.length} rooms)
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {scope === 'room' && (
                <div className="mt-3 space-y-2">
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1">Select Room:</label>
                    <select
                      value={targetRoomId}
                      onChange={(e) => setTargetRoomId(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
                    >
                      {currentFloorRooms.map((r) => (
                        <option key={r.room_id} value={r.room_id}>
                          {r.name} ({r.room_type})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
            </div>

            {/* Report Mode */}
            <div className="bg-slate-800/60 p-3.5 rounded-xl border border-slate-800">
              <label className="block text-slate-300 font-semibold mb-2">Export Mode</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setMode('final')}
                  disabled={Boolean(optionsData?.staleness?.is_stale)}
                  className={`flex-1 py-1.5 rounded-lg border font-medium transition ${
                    mode === 'final'
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                      : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed'
                  }`}
                  title={optionsData?.staleness?.is_stale ? 'Blocked due to geometry staleness' : 'Formal verified report'}
                >
                  Final Validated
                </button>
                <button
                  onClick={() => setMode('draft')}
                  className={`flex-1 py-1.5 rounded-lg border font-medium transition ${
                    mode === 'draft'
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                      : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                  }`}
                  title="Draft watermark report with staleness/incomplete warnings"
                >
                  Draft (Watermarked)
                </button>
              </div>
              <p className="text-[11px] text-slate-400 mt-2">
                {mode === 'final'
                  ? 'Strict verification: requires current, valid geometry. Suitable for formal project delivery.'
                  : 'Permissive draft: includes prominent watermark and warning banners for review.'}
              </p>
            </div>
          </div>

          {/* Visual Drawings & 3D Views */}
          <div className="bg-slate-800/60 p-3.5 rounded-xl border border-slate-800">
            <label className="block text-slate-300 font-semibold mb-2">Visual Layout & Perspective Views</label>
            <div className="grid grid-cols-2 gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={include2D}
                  onChange={(e) => setInclude2D(e.target.checked)}
                  className="rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0"
                />
                <span>Include 2D Vector Layout Drawings</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={include3D}
                  onChange={(e) => setInclude3D(e.target.checked)}
                  className="rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0"
                />
                <span>Include 3D Perspective Snapshot</span>
              </label>
            </div>
          </div>

          {/* Configurable Sections */}
          <div className="bg-slate-800/60 p-3.5 rounded-xl border border-slate-800">
            <div className="flex items-center justify-between mb-2">
              <label className="text-slate-300 font-semibold">Included Report Sections</label>
              <div className="flex gap-2">
                <button
                  onClick={() =>
                    setSelectedSections(
                      new Set<ReportSection>([
                        'cover',
                        'project_overview',
                        'layout_drawings',
                        'furniture_schedule',
                        'kitchen_schedule',
                        'bathroom_schedule',
                        'lighting_schedule',
                        'electrical_schedule',
                        'plumbing_schedule',
                        'finish_schedule',
                        'ergonomic_validation',
                        'optimization_summary',
                        'disclaimers',
                      ])
                    )
                  }
                  className="text-[11px] text-cyan-400 hover:underline"
                >
                  Select All
                </button>
                <span className="text-slate-600">|</span>
                <button
                  onClick={() => setSelectedSections(new Set<ReportSection>(['cover', 'furniture_schedule', 'disclaimers']))}
                  className="text-[11px] text-slate-400 hover:underline"
                >
                  Minimal
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px]">
              {[
                { id: 'cover', label: 'Cover Page' },
                { id: 'project_overview', label: 'Project Overview' },
                { id: 'layout_drawings', label: '2D Layout Drawings' },
                { id: 'furniture_schedule', label: 'Furniture Schedule' },
                { id: 'kitchen_schedule', label: 'Kitchen Schedule' },
                { id: 'bathroom_schedule', label: 'Bathroom Schedule' },
                { id: 'lighting_schedule', label: 'Lighting Schedule' },
                { id: 'electrical_schedule', label: 'Electrical (MEP)' },
                { id: 'plumbing_schedule', label: 'Plumbing (MEP)' },
                { id: 'finish_schedule', label: 'Finishes & Materials' },
                { id: 'ergonomic_validation', label: 'Neufert Ergonomics' },
                { id: 'optimization_summary', label: 'GA Optimization' },
                { id: 'disclaimers', label: 'Disclaimers & Notes' },
              ].map((s) => (
                <label key={s.id} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedSections.has(s.id as ReportSection)}
                    onChange={() => toggleSection(s.id as ReportSection)}
                    className="rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0"
                  />
                  <span>{s.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Author & Custom Notes */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-slate-400 text-[11px] mb-1">Author / Firm Name:</label>
              <input
                type="text"
                value={authorName}
                onChange={(e) => setAuthorName(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
                placeholder="ArchAI-Plan ESAI-Engine"
              />
            </div>
            <div>
              <label className="block text-slate-400 text-[11px] mb-1">Custom Project Notes (Optional):</label>
              <input
                type="text"
                value={customNotes}
                onChange={(e) => setCustomNotes(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
                placeholder="Client review copy"
              />
            </div>
          </div>

          {/* Messages */}
          {errorMessage && (
            <div className="bg-rose-950/40 border border-rose-500/50 rounded-xl p-3 text-rose-200">
              <span className="font-bold">Error:</span> {errorMessage}
            </div>
          )}
          {successMessage && (
            <div className="bg-emerald-950/40 border border-emerald-500/50 rounded-xl p-3 text-emerald-200">
              {successMessage}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-950/80">
          <div></div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              disabled={loading}
              className="px-3 py-1.5 bg-transparent hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg transition text-xs"
            >
              Cancel
            </button>
            <button
              onClick={handleDownloadPdf}
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold rounded-lg shadow-lg shadow-cyan-900/30 transition disabled:opacity-50 text-xs"
            >
              {loading ? (
                <>
                  <span className="animate-spin inline-block mr-1">⏳</span> Generating PDF...
                </>
              ) : (
                <>
                  <span>📥</span> Download PDF Report
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
