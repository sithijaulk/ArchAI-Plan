"use client";

import React from 'react';
import { CheckCircle2, AlertTriangle, Layers, Maximize2, Sparkles, Compass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FloorPlanCandidate } from '../../types';

interface CandidateComparisonProps {
  candidates: FloorPlanCandidate[];
  selectedCandidateId: string | null;
  onSelectCandidate: (candidateId: string) => Promise<void>;
  isLoading?: boolean;
}

export const CandidateComparison: React.FC<CandidateComparisonProps> = ({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  isLoading = false,
}) => {
  if (!candidates || candidates.length === 0) {
    return null;
  }

  return (
    <div className="mb-4 bg-card/70 border border-border rounded-xl p-3.5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <h4 className="text-sm font-semibold text-foreground">
            Generated Blueprint Candidates ({candidates.length})
          </h4>
        </div>
        <span className="text-[11px] text-muted-foreground">
          Ranked by explainable multi-dimensional heuristic baseline
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {candidates.map((cand) => {
          const isSelected = cand.candidate_id === selectedCandidateId;
          const isFeasible = cand.feasibility_status === 'FEASIBLE_VERIFIED_CONSTRAINTS';
          const scorePercent = Math.round(cand.heuristic_score * 100);

          return (
            <div
              key={cand.candidate_id}
              className={`p-3 rounded-lg border transition-all duration-200 flex flex-col justify-between ${
                isSelected
                  ? 'bg-primary/10 border-primary ring-1 ring-primary/40 shadow-sm'
                  : 'bg-background/60 border-border hover:border-border/90'
              }`}
            >
              <div className="space-y-2">
                {/* Header: Rank, Name, Score */}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-muted text-foreground">
                        #{cand.rank}
                      </span>
                      <strong className="text-xs text-foreground font-semibold line-clamp-1">
                        {cand.display_name}
                      </strong>
                    </div>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {cand.candidate_id}
                    </span>
                  </div>

                  <div className="text-right">
                    <span className="text-xs font-bold text-primary font-mono">
                      {scorePercent}%
                    </span>
                    <div className="text-[9px] text-muted-foreground uppercase">Score</div>
                  </div>
                </div>

                {/* Footprint & Area Metrics */}
                <div className="grid grid-cols-2 gap-1.5 py-1.5 border-y border-border/40 text-[11px]">
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Footprint</span>
                    <span className="font-medium text-foreground">
                      {cand.building_footprint_area_sqm.toFixed(1)} m²
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Usable Area</span>
                    <span className="font-medium text-foreground">
                      {cand.features.total_usable_room_area_sqm.toFixed(1)} m²
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Utilization</span>
                    <span className="font-medium text-foreground">
                      {Math.round(cand.features.area_utilization_ratio * 100)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Adjacency</span>
                    <span className="font-medium text-foreground">
                      {Math.round(cand.features.adjacency_satisfaction_ratio * 100)}%
                    </span>
                  </div>
                </div>

                {/* Score Breakdown Bars */}
                <div className="space-y-1 text-[10px]">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Space & Circulation:</span>
                    <span>
                      {Math.round((cand.score_breakdown.space_utilization + cand.score_breakdown.circulation_efficiency) * 50)}%
                    </span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-1 overflow-hidden">
                    <div
                      className="bg-primary h-full rounded-full transition-all"
                      style={{ width: `${Math.min(100, Math.max(10, scorePercent))}%` }}
                    />
                  </div>
                </div>

                {/* Regulatory / Feasibility Status Indicator */}
                <div className="flex items-center gap-1.5 pt-1 text-[10px]">
                  {isFeasible ? (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Feasible & Verified
                    </span>
                  ) : (
                    <span className="text-amber-400 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> {cand.feasibility_status.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
              </div>

              {/* Selection Button */}
              <div className="pt-2.5 mt-2 border-t border-border/40">
                <Button
                  size="sm"
                  variant={isSelected ? 'default' : 'outline'}
                  className="w-full h-7 text-xs font-medium"
                  disabled={isLoading || isSelected}
                  onClick={() => onSelectCandidate(cand.candidate_id)}
                >
                  {isSelected ? 'Active Layout' : 'Select This Candidate'}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
