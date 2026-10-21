"use client";

import React, { useState } from 'react';
import { Compass, Plus, Trash2, Eye, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ManualSurveyData, SurveyEdge } from '../../types';
import { gabGenExtendedApi } from '../../api';

interface SurveyVerificationProps {
  projectId: string;
  surveyData: ManualSurveyData;
  onChange: (data: ManualSurveyData) => void;
  onSave: () => Promise<void>;
  isSaving: boolean;
}

export const SurveyVerification: React.FC<SurveyVerificationProps> = ({
  projectId,
  surveyData,
  onChange,
  onSave,
  isSaving,
}) => {
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const loadDevFixture = async () => {
    try {
      const res = await gabGenExtendedApi.loadTestFixture(projectId, 'standard_10_perch');
      onChange(res.survey_extraction);
    } catch (e: any) {
      alert("Failed to load dev fixture: " + (e.response?.data?.detail || e.message));
    }
  };

  const updateEdge = (index: number, updates: Partial<SurveyEdge>) => {
    const newEdges = [...surveyData.edges];
    // Modifying any edge switches source provenance from 'fixture' to 'manual'
    newEdges[index] = { ...newEdges[index], ...updates, source: 'manual' };
    onChange({ ...surveyData, source: 'manual', edges: newEdges });
  };

  const addEdge = () => {
    const nextIdx = surveyData.edges.length + 1;
    const newEdge: SurveyEdge = {
      edge_id: `E0${nextIdx}`,
      distance: { value: 12.0, unit: 'm' },
      bearing: { raw: '090°', normalized_degrees: 90.0 },
      edge_type: 'side',
      source: 'manual',
    };
    onChange({ ...surveyData, source: 'manual', edges: [...surveyData.edges, newEdge] });
  };

  const removeEdge = (index: number) => {
    onChange({
      ...surveyData,
      source: 'manual',
      edges: surveyData.edges.filter((_, i) => i !== index),
    });
  };

  const handlePreviewLand = async () => {
    if (surveyData.edges.length < 3) {
      setPreviewError("At least 3 boundary edges are required to preview land polygon.");
      return;
    }
    setIsPreviewing(true);
    setPreviewError(null);
    try {
      const res = await gabGenExtendedApi.validateLand(projectId, surveyData);
      setPreviewResult(res);
    } catch (err: any) {
      setPreviewError(err.response?.data?.detail || "Land preview failed.");
    } finally {
      setIsPreviewing(false);
    }
  };

  const [isExtractingOcr, setIsExtractingOcr] = useState(false);

  const handleExtractOcr = async () => {
    setIsExtractingOcr(true);
    setPreviewError(null);
    try {
      const pageToExtract = surveyData.selected_page_number || 1;
      const res = await gabGenExtendedApi.extractSurvey(projectId, pageToExtract);
      if (res.survey_extraction) {
        onChange(res.survey_extraction);
      }
    } catch (err: any) {
      setPreviewError(err.response?.data?.detail || "Automated OCR extraction failed. Please enter or verify boundaries manually.");
    } finally {
      setIsExtractingOcr(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-foreground">Survey Boundary Data</h4>
          <p className="text-[11px] text-muted-foreground">
            Extracted from deed/survey plan with OpenCV & EasyOCR. Inspect and verify below.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleExtractOcr}
            disabled={isExtractingOcr}
            className="text-[11px] h-7 border-primary/40 text-primary hover:bg-primary/10"
          >
            {isExtractingOcr ? "Extracting OCR..." : "Auto-Extract from Deed (EasyOCR)"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={loadDevFixture}
            className="text-[11px] h-7 border-amber-500/40 text-amber-500 hover:bg-amber-500/10"
          >
            Dev: Fixture
          </Button>
        </div>
      </div>


      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 p-3 rounded-xl bg-card border border-border">
        <div className="min-w-0">
          <Label className="text-xs font-semibold mb-1 block">Plan North Angle</Label>
          <div className="flex items-center gap-1.5">
            <Compass className="w-4 h-4 text-primary shrink-0" />
            <Input
              type="number"
              min="0"
              max="359.9"
              value={surveyData.north_angle}
              onChange={(e) => onChange({ ...surveyData, north_angle: parseFloat(e.target.value) || 0, north_angle_origin: 'user' })}
              className="text-xs h-8 flex-1 min-w-0"
            />
            <span className="text-[10px] text-muted-foreground shrink-0">deg</span>
          </div>
          <span className="text-[9px] text-muted-foreground block mt-1 truncate">
            Origin: {surveyData.north_angle_origin || 'default_unknown'}
          </span>
        </div>

        <div className="min-w-0">
          <Label className="text-xs font-semibold mb-1 block">Drawing Scale</Label>
          <Input
            type="text"
            placeholder="e.g. 1:100, 1:200"
            value={surveyData.drawing_scale || ''}
            onChange={(e) => onChange({ ...surveyData, drawing_scale: e.target.value, drawing_scale_origin: 'user' })}
            className="text-xs h-8 w-full"
          />
          <span className="text-[9px] text-muted-foreground block mt-1 truncate">
            Origin: {surveyData.drawing_scale_origin || 'unknown'}
          </span>
        </div>

        <div className="min-w-0">
          <Label className="text-xs font-semibold mb-1 block">Selected Page</Label>
          <div className="flex items-center gap-1.5">
            <Input
              type="number"
              min="1"
              max={surveyData.total_pages || 1}
              value={surveyData.selected_page_number || 1}
              onChange={(e) => onChange({ ...surveyData, selected_page_number: parseInt(e.target.value) || 1 })}
              className="text-xs h-8 w-20"
            />
            <span className="text-[10px] text-muted-foreground shrink-0">of {surveyData.total_pages || 1}</span>
          </div>
        </div>

        <div className="min-w-0">
          <Label className="text-xs font-semibold mb-1 block">Status & Origin</Label>
          <div className="min-h-8 px-2 py-1 bg-muted/30 rounded-lg border border-border/50 text-[10px] flex items-center justify-between gap-1 flex-wrap">
            <span className="font-semibold uppercase text-primary text-[10px] truncate max-w-[80px]">
              {surveyData.source}
            </span>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-background font-mono text-muted-foreground border border-border/40 whitespace-nowrap">
              {surveyData.verification_status || 'unverified'}
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <Label className="text-xs font-semibold">Boundary Edges ({surveyData.edges.length})</Label>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handlePreviewLand}
              disabled={isPreviewing}
              className="text-xs h-7 gap-1"
            >
              <Eye className="w-3.5 h-3.5" />
              {isPreviewing ? "Calculating..." : "Preview Land"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={addEdge}
              className="text-xs h-7 text-primary hover:bg-primary/10"
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> Add Edge
            </Button>
          </div>
        </div>

        {surveyData.edges.length === 0 ? (
          <div className="text-center py-6 border border-dashed rounded-xl border-border bg-card/20 text-xs text-muted-foreground">
            No survey boundaries entered. Add boundary edges above or load development fixture.
          </div>
        ) : (
          <div className="space-y-2 max-h-[340px] overflow-y-auto overflow-x-auto pr-1 pb-1">
            {surveyData.edges.map((edge, idx) => (
              <div
                key={edge.edge_id || idx}
                className="flex items-center gap-2 p-2 rounded-lg bg-card border border-border text-xs min-w-[460px] sm:min-w-0"
              >
                <div className="flex items-center gap-1 shrink-0">
                  <input
                    type="text"
                    value={edge.edge_id}
                    onChange={(e) => updateEdge(idx, { edge_id: e.target.value })}
                    className="w-12 px-1.5 py-1 text-xs font-bold text-primary bg-background border border-border rounded text-center"
                  />
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <span className="text-[10px] text-muted-foreground">Dist:</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0.1"
                    value={edge.distance.value}
                    onChange={(e) =>
                      updateEdge(idx, {
                        distance: { ...edge.distance, value: parseFloat(e.target.value) || 0 },
                      })
                    }
                    className="w-16 px-1.5 py-1 text-xs bg-background border border-border rounded text-center"
                  />
                  <select
                    value={edge.distance.unit}
                    onChange={(e) =>
                      updateEdge(idx, {
                        distance: { ...edge.distance, unit: e.target.value as any }
                      })
                    }
                    className="text-[10px] bg-background border border-border rounded px-1 py-1"
                  >
                    <option value="m">m</option>
                    <option value="ft">ft</option>
                  </select>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <span className="text-[10px] text-muted-foreground">Bearing:</span>
                  <input
                    type="text"
                    value={edge.bearing.raw}
                    onChange={(e) =>
                      updateEdge(idx, {
                        bearing: {
                          raw: e.target.value,
                          normalized_degrees: parseFloat(e.target.value) || edge.bearing.normalized_degrees,
                        },
                      })
                    }
                    placeholder="e.g. 090°"
                    className="w-20 px-1.5 py-1 text-xs bg-background border border-border rounded text-center"
                  />
                </div>

                <div className="ml-auto flex items-center gap-2 shrink-0">
                  <select
                    value={edge.edge_type || 'side'}
                    onChange={(e) => updateEdge(idx, { edge_type: e.target.value as any })}
                    className="bg-background border border-border rounded px-2 py-1 text-foreground text-[11px]"
                  >
                    <option value="road_front">Road Front</option>
                    <option value="rear">Rear</option>
                    <option value="side">Side</option>
                    <option value="side_left">Side (Left)</option>
                    <option value="side_right">Side (Right)</option>
                  </select>

                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeEdge(idx)}
                    className="h-7 w-7 p-0 shrink-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Preview Land Diagnostic Card */}
      {previewResult && (
        <div className="p-3 rounded-xl bg-card border border-border space-y-1.5 text-xs">
          <div className="flex items-center justify-between pb-1 border-b border-border/40">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              {previewResult.is_valid ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-amber-500" />
              )}
              Vector Reconstruction Preview
            </span>
            <span className="text-[10px] text-muted-foreground font-mono">
              Closure Error: {previewResult.closure_error}m
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div>
              Reconstructed Area: <strong>{previewResult.reconstructed_area} m²</strong>
            </div>
            <div>
              Perimeter: <strong>{previewResult.perimeter} m</strong>
            </div>
          </div>

          {previewResult.warnings?.length > 0 && (
            <div className="text-[10px] text-amber-500 bg-amber-500/10 p-1.5 rounded">
              {previewResult.warnings[0]}
            </div>
          )}
        </div>
      )}

      {previewError && (
        <div className="text-xs text-destructive bg-destructive/10 p-2 rounded-lg">
          {previewError}
        </div>
      )}

      <Button
        type="button"
        onClick={onSave}
        disabled={isSaving}
        className="w-full electric-glow text-xs"
      >
        {isSaving ? "Saving..." : "Verify & Save Survey Boundaries"}
      </Button>
    </div>
  );
};
