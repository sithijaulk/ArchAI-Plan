"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ShieldCheck,
  Building,
  CheckCircle2,
  AlertCircle,
  FileText,
  UserCheck,
  Send,
  Eye,
  RefreshCw,
  Compass,
  Layers,
  HelpCircle,
} from 'lucide-react';

interface ReviewPackage {
  package_id: string;
  candidate_anonymous_id: string;
  candidate_fingerprint: string;
  site_family_id: string;
  site_category: string;
  site_extent_perches: number;
  num_floors: number;
  requirements_summary: any;
  floor_plans: any[];
  doors_summary: any[];
  windows_summary: any[];
  roof_summary?: any;
  created_at: string;
}

export default function ExpertReviewPage() {
  const [packages, setPackages] = useState<ReviewPackage[]>([]);
  const [selectedPkg, setSelectedPkg] = useState<ReviewPackage | null>(null);
  const [selectedFloorIdx, setSelectedFloorIdx] = useState<number>(0);
  const [submittedReviews, setSubmittedReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Review Form State
  const [reviewerId, setReviewerId] = useState<string>('ARCH-SLIA-');
  const [reviewerQualification, setReviewerQualification] = useState<string>('SLIA_CHARTERED');
  const [functionalArrangement, setFunctionalArrangement] = useState<number>(0.80);
  const [circulationQuality, setCirculationQuality] = useState<number>(0.80);
  const [roomUsability, setRoomUsability] = useState<number>(0.80);
  const [adjacencyPrivacy, setAdjacencyPrivacy] = useState<number>(0.80);
  const [spatialOrganization, setSpatialOrganization] = useState<number>(0.80);
  const [overallScore, setOverallScore] = useState<number>(0.80);
  const [reviewNotes, setReviewNotes] = useState<string>('');

  // Internal Research-Only Preview State
  const [showExperimentalPreview, setShowExperimentalPreview] = useState<boolean>(false);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const [previewData, setPreviewData] = useState<any>(null);

  const fetchExperimentalPreview = async (pkgId: string) => {
    setPreviewLoading(true);
    setPreviewData(null);
    try {
      const res = await fetch(`/api/research/cubicasa/preview-package-prediction/${pkgId}`);
      if (res.ok) {
        const data = await res.json();
        setPreviewData(data);
      }
    } catch (err) {
      console.error('Preview error:', err);
    } finally {
      setPreviewLoading(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [pkgRes, revRes] = await Promise.all([
        fetch('/api/research/cubicasa/review-packages'),
        fetch('/api/research/cubicasa/reviews'),
      ]);
      if (pkgRes.ok) {
        const pkgData = await pkgRes.json();
        setPackages(pkgData.packages || []);
        if (pkgData.packages && pkgData.packages.length > 0 && !selectedPkg) {
          setSelectedPkg(pkgData.packages[0]);
        }
      }
      if (revRes.ok) {
        const revData = await revRes.json();
        setSubmittedReviews(revData.reviews || []);
      }
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: 'Failed to load review packages: ' + err.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPkg) return;

    if (!reviewerId.trim() || reviewerId.trim().length < 5) {
      setStatusMsg({ type: 'error', text: 'Please enter a valid, identifiable reviewer registration ID.' });
      return;
    }

    setIsSubmitting(true);
    setStatusMsg(null);

    const submissionPayload = {
      submission_id: "SUB-" + Date.now().toString(36).toUpperCase(),
      package_id: selectedPkg.package_id,
      candidate_anonymous_id: selectedPkg.candidate_anonymous_id,
      reviewer_id: reviewerId.trim(),
      reviewer_qualification: reviewerQualification,
      is_synthetic_test: false,
      submission_timestamp: new Date().toISOString(),
      functional_arrangement_score: Number(functionalArrangement),
      circulation_quality_score: Number(circulationQuality),
      room_usability_score: Number(roomUsability),
      adjacency_privacy_score: Number(adjacencyPrivacy),
      spatial_organization_score: Number(spatialOrganization),
      overall_quality_score: Number(overallScore),
      confidence: 1.0,
      review_notes: reviewNotes.trim() || null,
    };

    try {
      const res = await fetch('/api/research/cubicasa/reviews/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(submissionPayload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail?.errors?.join(', ') || data.detail || 'Submission failed');
      }

      setStatusMsg({
        type: 'success',
        text: "Review successfully registered for candidate " + selectedPkg.candidate_anonymous_id + "!",
      });
      setReviewNotes('');
      await loadData();
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Render 2D SVG preview of candidate floor plan
  const renderFloorSvg = (floor: any) => {
    if (!floor || !floor.rooms || floor.rooms.length === 0) {
      return (
        <div className="h-64 flex items-center justify-center text-muted-foreground text-sm">
          No room polygons available for this floor.
        </div>
      );
    }

    const allPts: { x: number; y: number }[] = [];
    floor.rooms.forEach((r: any) => {
      (r.polygon || []).forEach((p: any) => allPts.push(p));
    });

    const minX = allPts.length > 0 ? Math.min(...allPts.map((p) => p.x)) : 0;
    const maxX = allPts.length > 0 ? Math.max(...allPts.map((p) => p.x)) : 20;
    const minY = allPts.length > 0 ? Math.min(...allPts.map((p) => p.y)) : 0;
    const maxY = allPts.length > 0 ? Math.max(...allPts.map((p) => p.y)) : 20;

    const width = Math.max(1, maxX - minX);
    const height = Math.max(1, maxY - minY);
    const padding = 2;

    const viewBox = (minX - padding) + " " + (minY - padding) + " " + (width + padding * 2) + " " + (height + padding * 2);

    return (
      <div className="bg-slate-950 p-4 rounded-lg border border-border flex flex-col items-center justify-center">
        <svg
          viewBox={viewBox}
          className="w-full max-h-[420px] select-none"
          style={{ transform: 'scaleY(-1)' }}
        >
          {/* Room polygons */}
          {floor.rooms.map((room: any, idx: number) => {
            const pts = (room.polygon || []).map((p: any) => p.x + "," + p.y).join(" ");
            const isHabitable = !['corridor', 'utility', 'parking'].includes(room.type);
            const fillColor = isHabitable ? '#1e293b' : '#0f172a';
            const strokeColor = '#38bdf8';

            // Centroid approximation
            const cx = room.polygon.reduce((sum: number, p: any) => sum + p.x, 0) / room.polygon.length;
            const cy = room.polygon.reduce((sum: number, p: any) => sum + p.y, 0) / room.polygon.length;

            return (
              <g key={room.room_id || idx}>
                <polygon
                  points={pts}
                  fill={fillColor}
                  stroke={strokeColor}
                  strokeWidth="0.15"
                  className="hover:fill-sky-900/40 transition-colors"
                />
                <text
                  x={cx}
                  y={cy}
                  fill="#f8fafc"
                  fontSize="0.8"
                  fontWeight="600"
                  textAnchor="middle"
                  dominantBaseline="central"
                  style={{ transform: "scaleY(-1)", transformOrigin: cx + "px " + cy + "px" }}
                >
                  {room.name || room.type} ({room.area_sqm} m²)
                </text>
              </g>
            );
          })}
        </svg>
        <div className="mt-2 text-xs text-muted-foreground flex items-center gap-4">
          <span className="flex items-center gap-1"><Compass size={14} className="text-sky-400" /> Metric P0 Coordinate System (True Survey North)</span>
          <span>Gross Usable Area: {floor.gross_floor_area_sqm || 0} m²</span>
        </div>
      </div>
    );
  };

  const activeFloor = selectedPkg?.floor_plans?.[selectedFloorIdx] || selectedPkg?.floor_plans?.[0];

  return (
    <div className="space-y-8 p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="text-primary h-7 w-7" />
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Architectural Expert Review Portal
            </h1>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Phase 10.1: Blind evaluation workflow for SLIA / registered architectural peer-review of GAB-Gen floor plans.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/30 px-3 py-1">
            Blind Review Active (Heuristic Scores Hidden)
          </Badge>
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
            <RefreshCw className={"h-4 w-4 mr-2 " + (loading ? "animate-spin" : "")} />
            Refresh
          </Button>
        </div>
      </div>

      {statusMsg && (
        <div
          className={"p-4 rounded-lg flex items-center gap-3 border " + (statusMsg.type === "success" ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-300" : "bg-rose-950/40 border-rose-500/30 text-rose-300")}
        >
          {statusMsg.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <span className="text-sm font-medium">{statusMsg.text}</span>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Package Selector & Candidate Plans */}
        <div className="lg:col-span-8 space-y-6">
          {/* Candidate Selection Tabs */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center justify-between">
                <span>Assigned Candidate Packages ({packages.length})</span>
                <span className="text-xs text-muted-foreground font-normal">
                  {submittedReviews.length} Reviews Submitted
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                {packages.map((pkg) => {
                  const isSelected = selectedPkg?.package_id === pkg.package_id;
                  const isReviewed = submittedReviews.some((r) => r.package_id === pkg.package_id);

                  return (
                    <button
                      key={pkg.package_id}
                      onClick={() => {
                        setSelectedPkg(pkg);
                        setSelectedFloorIdx(0);
                      }}
                      className={"p-3 text-left rounded-lg border transition-all " + (isSelected ? "border-primary bg-primary/10 shadow-sm" : "border-border/60 bg-muted/20 hover:border-border")}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-semibold text-white">
                          {pkg.candidate_anonymous_id}
                        </span>
                        {isReviewed ? (
                          <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 text-[10px] px-1.5 py-0">
                            Reviewed
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-slate-800 text-slate-400 text-[10px] px-1.5 py-0">
                            Pending
                          </Badge>
                        )}
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-2">
                        <div>Site: {pkg.site_family_id}</div>
                        <div>Type: {pkg.site_category} ({pkg.site_extent_perches} P)</div>
                        <div>Storeys: {pkg.num_floors} Floor(s)</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Plan Drawing & Geometry Viewer */}
          {selectedPkg && (
            <Card className="bg-card border-border">
              <CardHeader className="pb-3 flex flex-row items-center justify-between border-b border-border/50">
                <div>
                  <CardTitle className="text-lg font-bold text-white flex items-center gap-2">
                    <Building size={18} className="text-sky-400" />
                    <span>Candidate Drawing: {selectedPkg.candidate_anonymous_id}</span>
                  </CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Deterministic geometry generated on {selectedPkg.site_category} site family.
                  </p>
                </div>
                {/* Floor Selector if multi-storey */}
                {selectedPkg.num_floors > 1 && (
                  <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-md border border-border">
                    {selectedPkg.floor_plans.map((fl: any, idx: number) => (
                      <Button
                        key={idx}
                        variant={selectedFloorIdx === idx ? 'default' : 'ghost'}
                        size="sm"
                        className="h-7 text-xs px-2.5"
                        onClick={() => setSelectedFloorIdx(idx)}
                      >
                        Floor {fl.floor_index + 1}
                      </Button>
                    ))}
                  </div>
                )}
              </CardHeader>
              <CardContent className="pt-4 space-y-4">
                {renderFloorSvg(activeFloor)}

                {/* Optional Internal Research-Only Preview (Strictly Isolated & Anti-Anchoring Guarded) */}
                {(() => {
                  const isReviewed = submittedReviews.some((r) => r.package_id === selectedPkg?.package_id);
                  return (
                    <div className="mt-4 p-4 rounded-lg border border-amber-500/30 bg-amber-500/5 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Layers className="h-4 w-4 text-amber-400" />
                          <span className="text-xs font-semibold text-amber-300">
                            Experimental XGBoost Research Preview (Post-Review Only)
                          </span>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
                          disabled={!isReviewed}
                          onClick={() => {
                            const nextState = !showExperimentalPreview;
                            setShowExperimentalPreview(nextState);
                            if (nextState && selectedPkg) {
                              fetchExperimentalPreview(selectedPkg.package_id);
                            }
                          }}
                        >
                          {!isReviewed ? 'Locked (Submit Review First)' : (showExperimentalPreview ? 'Hide Preview' : 'Run Experimental Preview')}
                        </Button>
                      </div>

                      {!isReviewed && (
                        <div className="p-2.5 rounded bg-slate-900/60 border border-border text-[11px] text-muted-foreground flex items-center gap-2">
                          <ShieldCheck size={14} className="text-amber-400 shrink-0" />
                          <span>
                            <strong>Anti-Anchoring Protocol Active:</strong> Model predictions and heuristic scores are strictly hidden from architects prior to evaluation to prevent cognitive anchoring bias.
                          </span>
                        </div>
                      )}

                      {isReviewed && showExperimentalPreview && (
                        <div className="pt-2 border-t border-amber-500/20 space-y-3">
                          <div className="p-2.5 rounded bg-amber-950/40 border border-amber-500/40 text-[11px] text-amber-200 flex items-start gap-2">
                            <AlertCircle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                            <div>
                              <div className="font-bold">
                                Experimental AI-Assisted Proxy Score — not a licensed architect assessment or statutory compliance decision.
                              </div>
                              <div className="text-amber-300/80 mt-0.5 text-[10px]">
                                Model trained strictly on CubiCasa5K geometric heuristics as an algorithmic emulator. Production candidate ranking and regulatory compliance remain 100% deterministic.
                              </div>
                            </div>
                          </div>

                          {previewLoading && (
                            <div className="text-xs text-muted-foreground flex items-center gap-2 py-2">
                              <RefreshCw className="h-3.5 w-3.5 animate-spin text-amber-400" />
                              Evaluating 24D scale-independent features through experimental XGBoost regressor...
                            </div>
                          )}

                          {previewData && (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
                              <div className="p-3 bg-slate-900 rounded border border-border">
                                <div className="text-[10px] text-muted-foreground">XGBoost Proxy Prediction</div>
                                <div className="text-lg font-bold text-sky-400 mt-0.5">
                                  {previewData.experimental_xgboost_prediction?.toFixed(4)}
                                </div>
                                <div className="text-[10px] text-muted-foreground mt-0.5">Scale: 0.00 to 1.00</div>
                              </div>
                              <div className="p-3 bg-slate-900 rounded border border-border">
                                <div className="text-[10px] text-muted-foreground">Deterministic Formula Target</div>
                                <div className="text-lg font-bold text-slate-200 mt-0.5">
                                  {previewData.deterministic_proxy_target?.toFixed(4)}
                                </div>
                                <div className="text-[10px] text-muted-foreground mt-0.5">Ground-truth proxy rubric</div>
                              </div>
                              <div className="p-3 bg-slate-900 rounded border border-border">
                                <div className="text-[10px] text-muted-foreground">Emulator Difference (Residual)</div>
                                <div className="text-lg font-bold text-amber-400 mt-0.5">
                                  {previewData.prediction_difference > 0 ? '+' : ''}{previewData.prediction_difference?.toFixed(4)}
                                </div>
                                <div className="text-[10px] text-muted-foreground mt-0.5">Approximation error</div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()}



                {/* Spatial Schedule Table */}
                <div className="mt-4 border border-border rounded-lg overflow-hidden">
                  <div className="bg-muted/40 px-3 py-2 text-xs font-semibold text-slate-300 border-b border-border flex justify-between">
                    <span>Room Schedule (Floor {activeFloor?.floor_index + 1 || 1})</span>
                    <span>Total Rooms: {activeFloor?.rooms?.length || 0}</span>
                  </div>
                  <div className="divide-y divide-border/40 text-xs">
                    {activeFloor?.rooms?.map((r: any, idx: number) => (
                      <div key={idx} className="px-3 py-2 flex items-center justify-between hover:bg-muted/10">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-sky-400"></span>
                          <span className="font-medium text-white">{r.name || r.type}</span>
                          <span className="text-muted-foreground text-[11px]">({r.type})</span>
                        </div>
                        <div className="flex items-center gap-4 text-muted-foreground">
                          {r.width_m && r.length_m && (
                            <span>{r.width_m}m × {r.length_m}m</span>
                          )}
                          <span className="font-semibold text-slate-200">{r.area_sqm} m²</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: Rubric Scoring Form */}
        <div className="lg:col-span-4 space-y-6">
          <Card className="bg-card border-border shadow-md">
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="text-base font-bold text-white flex items-center gap-2">
                <FileText size={18} className="text-primary" />
                <span>5-Axis Quality Assessment</span>
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-1">
                Strict SLIA 5-point Likert rubric normalized from 0.0 (Unacceptable) to 1.0 (Excellent).
              </p>
            </CardHeader>
            <CardContent className="pt-4">
              <form onSubmit={handleSubmitReview} className="space-y-4">
                {/* Reviewer Credentials */}
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-300">Architect Registration ID</Label>
                  <Input
                    value={reviewerId}
                    onChange={(e) => setReviewerId(e.target.value)}
                    placeholder="e.g. ARCH-SLIA-1042"
                    className="h-8 text-xs font-mono bg-muted/20"
                    required
                  />
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-300">Professional Qualification</Label>
                  <select
                    value={reviewerQualification}
                    onChange={(e) => setReviewerQualification(e.target.value)}
                    className="w-full h-8 text-xs bg-muted/20 border border-input rounded-md px-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="SLIA_CHARTERED">SLIA Chartered Architect</option>
                    <option value="AIA_CHARTERED">AIA Licensed Architect</option>
                    <option value="RIBA_CHARTERED">RIBA Chartered Architect</option>
                    <option value="ACADEMIC_PEER">Architectural Researcher / Academic</option>
                  </select>
                </div>

                <div className="border-t border-border/60 my-3 pt-3 space-y-4">
                  {/* Axis 1: Functional Arrangement */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-slate-300">1. Functional Arrangement</span>
                      <span className="font-bold text-sky-400">{functionalArrangement.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={functionalArrangement}
                      onChange={(e) => setFunctionalArrangement(parseFloat(e.target.value))}
                      className="w-full accent-sky-500"
                    />
                    <p className="text-[10px] text-muted-foreground">Spatial planning, room proportions & functional zoning.</p>
                  </div>

                  {/* Axis 2: Circulation Quality */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-slate-300">2. Circulation Flow</span>
                      <span className="font-bold text-sky-400">{circulationQuality.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={circulationQuality}
                      onChange={(e) => setCirculationQuality(parseFloat(e.target.value))}
                      className="w-full accent-sky-500"
                    />
                    <p className="text-[10px] text-muted-foreground">Corridor efficiency, direct access paths & staircase ergonomics.</p>
                  </div>

                  {/* Axis 3: Room Usability */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-slate-300">3. Room Usability</span>
                      <span className="font-bold text-sky-400">{roomUsability.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={roomUsability}
                      onChange={(e) => setRoomUsability(parseFloat(e.target.value))}
                      className="w-full accent-sky-500"
                    />
                    <p className="text-[10px] text-muted-foreground">Usable area, furniture layout flexibility & minimum dimensions.</p>
                  </div>

                  {/* Axis 4: Adjacency & Privacy */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-slate-300">4. Adjacency & Privacy</span>
                      <span className="font-bold text-sky-400">{adjacencyPrivacy.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={adjacencyPrivacy}
                      onChange={(e) => setAdjacencyPrivacy(parseFloat(e.target.value))}
                      className="w-full accent-sky-500"
                    />
                    <p className="text-[10px] text-muted-foreground">Segregation of private bedroom suites from public entertaining.</p>
                  </div>

                  {/* Axis 5: Spatial Organization */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-slate-300">5. Structural / Ventilation Logic</span>
                      <span className="font-bold text-sky-400">{spatialOrganization.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={spatialOrganization}
                      onChange={(e) => setSpatialOrganization(parseFloat(e.target.value))}
                      className="w-full accent-sky-500"
                    />
                    <p className="text-[10px] text-muted-foreground">Plumbing alignment, daylight access & cross-ventilation potential.</p>
                  </div>

                  {/* Target Overall Score */}
                  <div className="p-3 bg-muted/30 rounded-lg border border-border/80 space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-white">Overall Target Score</span>
                      <span className="font-extrabold text-primary text-sm">{overallScore.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.02"
                      value={overallScore}
                      onChange={(e) => setOverallScore(parseFloat(e.target.value))}
                      className="w-full accent-primary"
                    />
                    <p className="text-[10px] text-muted-foreground">Independent architectural quality target for supervised training.</p>
                  </div>

                  {/* Review Notes */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-300">Architectural Feedback / Notes</Label>
                    <Textarea
                      rows={3}
                      value={reviewNotes}
                      onChange={(e) => setReviewNotes(e.target.value)}
                      placeholder="Critique on room placement, circulation bottlenecks, or natural ventilation..."
                      className="text-xs bg-muted/20"
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full text-xs font-semibold"
                  disabled={isSubmitting || !selectedPkg}
                >
                  <Send className="h-3.5 w-3.5 mr-2" />
                  {isSubmitting ? 'Registering...' : 'Submit Expert Review'}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
