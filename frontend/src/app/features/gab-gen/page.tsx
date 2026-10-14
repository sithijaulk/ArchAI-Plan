"use client";

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell';
import { useProjectStore } from '@/store/projectStore';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { UploadCloud, CheckCircle2, Sliders, Play, FileText } from 'lucide-react';

import { SurveyUpload } from '@/features/gab-gen/components/input/SurveyUpload';
import { RequirementsForm } from '@/features/gab-gen/components/input/RequirementsForm';
import { SurveyVerification } from '@/features/gab-gen/components/input/SurveyVerification';
import { BlueprintViewer } from '@/features/gab-gen/components/preview/BlueprintViewer';
import { gabGenExtendedApi } from '@/features/gab-gen/api';
import {
  ClientRequirements,
  ManualSurveyData,
  GabGenMasterJson,
} from '@/features/gab-gen/types';

const defaultRequirements: ClientRequirements = {
  declared_land_extent: 10.0,
  declared_land_unit: 'perches',
  building_type: 'residential_house',
  storey_count: 2,
  rooms: [
    {
      id: 'rm_living',
      type: 'living_room',
      quantity: 1,
      required: true,
      preferred_min_area: 22,
      floor_preference: 'ground',
      priority: 'high',
      custom_name: 'Living Room',
    },
    {
      id: 'rm_dining',
      type: 'dining_area',
      quantity: 1,
      required: true,
      preferred_min_area: 14,
      floor_preference: 'ground',
      priority: 'high',
      custom_name: 'Dining Area',
    },
    {
      id: 'rm_kitchen',
      type: 'kitchen',
      quantity: 1,
      required: true,
      preferred_min_area: 12,
      floor_preference: 'ground',
      priority: 'high',
      custom_name: 'Kitchen',
    },
    {
      id: 'rm_master',
      type: 'master_bedroom',
      quantity: 1,
      required: true,
      preferred_min_area: 16,
      floor_preference: 'first',
      priority: 'high',
      custom_name: 'Master Bedroom',
    },
    {
      id: 'rm_bed2',
      type: 'bedroom',
      quantity: 1,
      required: true,
      preferred_min_area: 12,
      floor_preference: 'first',
      priority: 'high',
      custom_name: 'Bedroom 02',
    },
    {
      id: 'rm_bath_g',
      type: 'common_bathroom',
      quantity: 1,
      required: true,
      preferred_min_area: 4.5,
      floor_preference: 'ground',
      priority: 'high',
      custom_name: 'Common Bathroom (Ground)',
    },
    {
      id: 'rm_bath_f',
      type: 'attached_bathroom',
      quantity: 1,
      required: true,
      preferred_min_area: 4.5,
      floor_preference: 'first',
      priority: 'high',
      custom_name: 'Bathroom (Upper)',
    },
  ],
};

const defaultSurveyData: ManualSurveyData = {
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
  ],
};

export default function GabGenPage() {
  const router = useRouter();
  const { projectId, projectName, setOutput, setComponentStatus, skipComponent } = useProjectStore();

  const [activeStep, setActiveStep] = useState<'upload' | 'requirements' | 'survey' | 'generate'>('upload');
  const [requirements, setRequirements] = useState<ClientRequirements>(defaultRequirements);
  const [surveyData, setSurveyData] = useState<ManualSurveyData>(defaultSurveyData);
  const [uploadedFileMeta, setUploadedFileMeta] = useState<any>(null);
  const [outputData, setOutputData] = useState<GabGenMasterJson | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [isSavingReq, setIsSavingReq] = useState(false);
  const [isSavingSurvey, setIsSavingSurvey] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  // Redirect if no project
  useEffect(() => {
    if (!projectId) {
      router.push('/start');
      return;
    }

    // Load existing context if available
    gabGenExtendedApi.getContext(projectId).then((ctx) => {
      if (ctx.input_metadata?.source_file) {
        setUploadedFileMeta(ctx.input_metadata.source_file);
      }
      if (ctx.client_requirements?.rooms) {
        setRequirements(ctx.client_requirements);
      }
      if (ctx.survey_extraction?.edges) {
        setSurveyData(ctx.survey_extraction);
      }
    }).catch(() => {
      // Ignore if new project
    });

    // Check if result already generated
    gabGenExtendedApi.getResult(projectId).then((res) => {
      if (res?.floor_plan?.floors) {
        setOutputData(res);
        setOutput('gab_gen', res);
      }
    }).catch(() => {
      // Not yet generated
    });
  }, [projectId, router, setOutput]);

  if (!projectId) return null;

  const handleUploadFile = async (file: File) => {
    setIsUploading(true);
    try {
      const res = await gabGenExtendedApi.uploadSurvey(projectId, file);
      setUploadedFileMeta(res.file_metadata);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSaveRequirements = async () => {
    setIsSavingReq(true);
    try {
      await gabGenExtendedApi.saveRequirements(projectId, requirements);
      setActiveStep('survey');
    } finally {
      setIsSavingReq(false);
    }
  };

  const handleSaveSurvey = async () => {
    setIsSavingSurvey(true);
    try {
      await gabGenExtendedApi.saveManualSurveyData(projectId, surveyData);
      setActiveStep('generate');
    } finally {
      setIsSavingSurvey(false);
    }
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      // First ensure requirements and survey are saved
      await gabGenExtendedApi.saveRequirements(projectId, requirements);
      await gabGenExtendedApi.saveManualSurveyData(projectId, surveyData);

      const res = await gabGenExtendedApi.generate(projectId);
      setOutputData(res);
      setOutput('gab_gen', res);
      setComponentStatus('gab_gen', 'completed');
    } catch (err: any) {
      alert(err.response?.data?.detail || "Generation failed. Please verify inputs.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSkip = async () => {
    await skipComponent('gab_gen');
    router.push('/features/vsai-rectifier');
  };

  return (
    <FeatureWorkflowShell
      componentId="gab_gen"
      title="GAB-Gen: Geo-Spatial AI Blueprint Generator"
      number="01"
      description="Reconstructs parcel geometry from survey measurements, enforces verified UDA setbacks, and deterministically allocates structural residential blueprint floor plans."
      onNext={() => router.push('/features/vsai-rectifier')}
      onSkip={handleSkip}
    >
      <div className="p-6 md:p-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left Column: Interactive Input & Verification Controls */}
          <div className="lg:col-span-5 border-r border-border/50 pr-0 lg:pr-8 space-y-6">
            <div className="flex items-center justify-between pb-2 border-b border-border/40">
              <h3 className="text-lg font-bold text-foreground">Design Inputs & Survey</h3>
              <span className="text-xs text-muted-foreground font-mono">Stage 1 Deterministic</span>
            </div>

            <Tabs value={activeStep} onValueChange={(v: string) => setActiveStep(v as any)} className="w-full">
              <TabsList className="grid grid-cols-3 mb-4 w-full">
                <TabsTrigger value="upload" className="text-xs">
                  1. Deed Plan
                </TabsTrigger>
                <TabsTrigger value="requirements" className="text-xs">
                  2. Programme
                </TabsTrigger>
                <TabsTrigger value="survey" className="text-xs">
                  3. Boundaries
                </TabsTrigger>
              </TabsList>

              <TabsContent value="upload" className="mt-0">
                <SurveyUpload
                  uploadedMeta={uploadedFileMeta}
                  isUploading={isUploading}
                  onUploadSuccess={setUploadedFileMeta}
                  onUploadFile={handleUploadFile}
                />
                <div className="mt-4 flex justify-end">
                  <Button
                    size="sm"
                    onClick={() => setActiveStep('requirements')}
                    className="text-xs"
                  >
                    Next: Building Programme
                  </Button>
                </div>
              </TabsContent>

              <TabsContent value="requirements" className="mt-0">
                <RequirementsForm
                  requirements={requirements}
                  onChange={setRequirements}
                  onSave={handleSaveRequirements}
                  isSaving={isSavingReq}
                />
              </TabsContent>

              <TabsContent value="survey" className="mt-0">
                <SurveyVerification
                  surveyData={surveyData}
                  onChange={setSurveyData}
                  onSave={handleSaveSurvey}
                  isSaving={isSavingSurvey}
                />
                <div className="mt-4 flex justify-between">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setActiveStep('requirements')}
                    className="text-xs"
                  >
                    Back
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => setActiveStep('generate')}
                    className="text-xs"
                  >
                    Ready to Generate
                  </Button>
                </div>
              </TabsContent>
            </Tabs>

            {/* Execute Generation Button */}
            <div className="pt-2 border-t border-border/40">
              <Button
                className="w-full electric-glow py-5 text-sm font-semibold flex items-center justify-center gap-2"
                onClick={handleGenerate}
                disabled={isGenerating}
              >
                <Play className="w-4 h-4 fill-current" />
                {isGenerating ? 'Processing Blueprint Geometry...' : 'Generate Blueprint Geometry'}
              </Button>
            </div>
          </div>

          {/* Right Column: 2D/3D Multi-Floor Blueprint Viewer */}
          <div className="lg:col-span-7">
            <BlueprintViewer data={outputData} projectName={projectName} />
          </div>
        </div>
      </div>
    </FeatureWorkflowShell>
  );
}
