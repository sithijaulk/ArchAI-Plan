"use client";

import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DownloadImageButton, DownloadPdfButton, DownloadJsonButton } from '@/components/output/DownloadButtons';
import { Button } from '@/components/ui/button';
import { Layers, AlertTriangle, CheckCircle2, FileCode } from 'lucide-react';
import { PlanPreview2D } from './PlanPreview2D';
import { PlanPreview3D } from './PlanPreview3D';
import { GabGenMasterJson } from '../../types';

interface BlueprintViewerProps {
  data: GabGenMasterJson | null;
  projectName: string;
}

export const BlueprintViewer: React.FC<BlueprintViewerProps> = ({ data, projectName }) => {
  const [selectedFloor, setSelectedFloor] = useState<number | 'all'>('all');
  const [exploded3D, setExploded3D] = useState(false);
  const [activeTab, setActiveTab] = useState<'2d' | '3d' | 'json'>('2d');

  const floors = data?.floor_plan?.floors || [];
  const validation = data?.gab_gen_validation;

  return (
    <div className="space-y-4">
      {/* Top Header & Export Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xl font-bold text-foreground">GAB-Gen Blueprint Output</h3>
          <p className="text-xs text-muted-foreground">
            Stage 1 Vector Blueprint & Centralized Master JSON Architecture
          </p>
        </div>

        <div className="flex items-center gap-2">
          <DownloadImageButton
            filename={`${projectName || 'gab'}-blueprint-2d.png`}
            targetId="gab-2d-canvas"
            disabled={!data}
          />
          <DownloadPdfButton
            filename={`${projectName || 'gab'}-specification.pdf`}
            targetId="gab-2d-canvas"
            disabled={!data}
          />
          <DownloadJsonButton
            filename={`${projectName || 'gab'}-master-json.json`}
            data={data}
          />
        </div>
      </div>

      {/* Status & Validation Banner */}
      {validation && (
        <div
          className={`p-3 rounded-xl border flex items-center justify-between text-xs ${
            validation.status === 'completed'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : validation.status === 'needs_verification'
              ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
              : 'bg-destructive/10 border-destructive/30 text-destructive'
          }`}
        >
          <div className="flex items-center gap-2">
            {validation.status === 'completed' ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <AlertTriangle className="w-4 h-4" />
            )}
            <span>
              Status:{' '}
              <strong className="uppercase">{validation.status.replace(/_/g, ' ')}</strong>
              {validation.warnings?.length > 0 && ` — ${validation.warnings[0]}`}
              {validation.violations?.length > 0 && ` — ${validation.violations[0]}`}
            </span>
          </div>

          <div className="flex items-center gap-4 text-[11px] opacity-90">
            <span>
              Reconstructed: <strong>{data?.land_info?.reconstructed_area?.toFixed(1)} m²</strong>
            </span>
            <span>
              Buildable: <strong>{data?.buildable_footprint?.area?.toFixed(1)} m²</strong>
            </span>
          </div>
        </div>
      )}

      {/* Floor Selector Bar (for Multi-Storey) */}
      {floors.length > 1 && (
        <div className="flex items-center gap-2 bg-card p-1.5 rounded-lg border border-border w-fit text-xs">
          <span className="text-[11px] text-muted-foreground px-2 font-medium flex items-center gap-1">
            <Layers className="w-3.5 h-3.5" /> Floor Level:
          </span>
          <Button
            size="sm"
            variant={selectedFloor === 'all' ? 'default' : 'ghost'}
            className="h-7 text-xs"
            onClick={() => setSelectedFloor('all')}
          >
            All Floors
          </Button>
          {floors.map((fl) => (
            <Button
              key={fl.floor_id}
              size="sm"
              variant={selectedFloor === fl.floor_index ? 'default' : 'ghost'}
              className="h-7 text-xs"
              onClick={() => setSelectedFloor(fl.floor_index)}
            >
              {fl.name}
            </Button>
          ))}
        </div>
      )}

      {/* Main Preview Tabs: 2D, 3D, and Master JSON Inspector */}
      <Tabs value={activeTab} onValueChange={(v: any) => setActiveTab(v)} className="w-full">
        <div className="flex items-center justify-between mb-3">
          <TabsList className="grid w-64 grid-cols-3">
            <TabsTrigger value="2d" className="text-xs">
              2D Vector
            </TabsTrigger>
            <TabsTrigger value="3d" className="text-xs">
              3D View
            </TabsTrigger>
            <TabsTrigger value="json" className="text-xs">
              Master JSON
            </TabsTrigger>
          </TabsList>

          {activeTab === '3d' && floors.length > 1 && (
            <Button
              size="sm"
              variant={exploded3D ? 'secondary' : 'outline'}
              className="h-7 text-xs"
              onClick={() => setExploded3D(!exploded3D)}
            >
              {exploded3D ? 'Compact View' : 'Exploded Levels'}
            </Button>
          )}
        </div>

        {/* Keep 2D canvas mounted or visible so export does not capture blank */}
        <div id="gab-2d-canvas" className={activeTab === '2d' ? 'block' : 'hidden'}>
          <PlanPreview2D data={data} selectedFloorIndex={selectedFloor} />
        </div>

        {activeTab === '3d' && (
          <PlanPreview3D
            data={data}
            selectedFloorIndex={selectedFloor}
            explodedMode={exploded3D}
          />
        )}

        {activeTab === 'json' && (
          <div className="bg-card/70 border border-border p-4 rounded-xl min-h-[480px] max-h-[520px] overflow-auto">
            <pre className="text-xs text-primary-foreground/90 font-mono">
              {data ? JSON.stringify(data, null, 2) : 'No component output is available yet.'}
            </pre>
          </div>
        )}
      </Tabs>
    </div>
  );
};
