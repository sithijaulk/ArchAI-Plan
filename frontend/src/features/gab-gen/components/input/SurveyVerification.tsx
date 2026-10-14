"use client";

import React, { useState } from 'react';
import { Compass, Plus, Trash2, CheckCircle2, Sliders } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ManualSurveyData, SurveyEdge } from '../../types';

interface SurveyVerificationProps {
  surveyData: ManualSurveyData;
  onChange: (data: ManualSurveyData) => void;
  onSave: () => Promise<void>;
  isSaving: boolean;
}

export const SurveyVerification: React.FC<SurveyVerificationProps> = ({
  surveyData,
  onChange,
  onSave,
  isSaving,
}) => {
  const loadPreset = (presetName: string) => {
    if (presetName === 'colombo_10_perch') {
      onChange({
        north_angle: 0,
        reference_edge: 'E01',
        source: 'fixture',
        edges: [
          {
            edge_id: 'E01',
            distance: { value: 14.5, unit: 'm' },
            bearing: { raw: '090°00\'00"', normalized_degrees: 90.0 },
            edge_type: 'road_front',
            source: 'fixture',
          },
          {
            edge_id: 'E02',
            distance: { value: 17.44, unit: 'm' },
            bearing: { raw: '180°00\'00"', normalized_degrees: 180.0 },
            edge_type: 'side_right',
            source: 'fixture',
          },
          {
            edge_id: 'E03',
            distance: { value: 14.5, unit: 'm' },
            bearing: { raw: '270°00\'00"', normalized_degrees: 270.0 },
            edge_type: 'rear',
            source: 'fixture',
          },
          {
            edge_id: 'E04',
            distance: { value: 17.44, unit: 'm' },
            bearing: { raw: '000°00\'00"', normalized_degrees: 0.0 },
            edge_type: 'side_left',
            source: 'fixture',
          },
        ]
      });
    }
  };

  const updateEdge = (index: number, updates: Partial<SurveyEdge>) => {
    const newEdges = [...surveyData.edges];
    newEdges[index] = { ...newEdges[index], ...updates };
    onChange({ ...surveyData, edges: newEdges });
  };

  const addEdge = () => {
    const nextIdx = surveyData.edges.length + 1;
    const newEdge: SurveyEdge = {
      edge_id: `E0${nextIdx}`,
      distance: { value: 10.0, unit: 'm' },
      bearing: { raw: '090°', normalized_degrees: 90.0 },
      edge_type: 'side',
      source: 'manual',
    };
    onChange({ ...surveyData, edges: [...surveyData.edges, newEdge] });
  };

  const removeEdge = (index: number) => {
    onChange({
      ...surveyData,
      edges: surveyData.edges.filter((_, i) => i !== index),
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-foreground">Survey Boundary Data</h4>
          <p className="text-[11px] text-muted-foreground">
            Stage-1 Normalized Survey Input. Normalized contract matches future EasyOCR extraction.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => loadPreset('colombo_10_perch')}
          className="text-xs h-8 text-primary border-primary/40 hover:bg-primary/10"
        >
          Load 10-Perch Fixture
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-card border border-border">
        <div>
          <Label className="text-xs font-semibold mb-1 block">North Orientation Angle</Label>
          <div className="flex items-center gap-2">
            <Compass className="w-4 h-4 text-primary" />
            <Input
              type="number"
              min="0"
              max="359.9"
              value={surveyData.north_angle}
              onChange={(e) => onChange({ ...surveyData, north_angle: parseFloat(e.target.value) || 0 })}
              className="text-xs"
            />
            <span className="text-xs text-muted-foreground">deg</span>
          </div>
        </div>

        <div>
          <Label className="text-xs font-semibold mb-1 block">Source Extraction Mode</Label>
          <div className="p-2 bg-muted/30 rounded border border-border/50 text-xs">
            <span className="font-semibold text-primary">{surveyData.source.toUpperCase()}</span> (Deterministic Stage 1)
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-semibold">Boundary Edges ({surveyData.edges.length})</Label>
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

        <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
          {surveyData.edges.map((edge, idx) => (
            <div
              key={edge.edge_id || idx}
              className="flex items-center gap-2 p-2 rounded-lg bg-card border border-border text-xs"
            >
              <span className="font-bold text-primary w-8">{edge.edge_id}</span>

              <div className="flex items-center gap-1">
                <span className="text-[10px] text-muted-foreground">Dist:</span>
                <input
                  type="number"
                  step="0.01"
                  min="1"
                  value={edge.distance.value}
                  onChange={(e) =>
                    updateEdge(idx, {
                      distance: { ...edge.distance, value: parseFloat(e.target.value) || 0 },
                    })
                  }
                  className="w-16 px-1.5 py-1 text-xs bg-background border border-border rounded"
                />
                <span className="text-[10px] text-muted-foreground">{edge.distance.unit}</span>
              </div>

              <div className="flex items-center gap-1">
                <span className="text-[10px] text-muted-foreground">Deg:</span>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="359.9"
                  value={edge.bearing.normalized_degrees}
                  onChange={(e) =>
                    updateEdge(idx, {
                      bearing: {
                        raw: `${e.target.value}°`,
                        normalized_degrees: parseFloat(e.target.value) || 0,
                      },
                    })
                  }
                  className="w-16 px-1.5 py-1 text-xs bg-background border border-border rounded"
                />
              </div>

              <select
                value={edge.edge_type || 'side'}
                onChange={(e) => updateEdge(idx, { edge_type: e.target.value as any })}
                className="bg-background border border-border rounded px-2 py-1 text-foreground text-[11px] ml-auto"
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
                className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </div>

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
