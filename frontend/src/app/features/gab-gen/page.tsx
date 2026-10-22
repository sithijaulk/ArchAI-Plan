"use client";

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FeatureWorkflowShell } from '@/components/workflow/FeatureWorkflowShell';
import { useProjectStore } from '@/store/projectStore';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Play, AlertCircle, CheckCircle2 } from 'lucide-react';

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

// Empty default-neutral initial state (no sample house pre-filled)
const emptyRequirements: ClientRequirements = {
  declared_land_extent: 0,
  declared_land_unit: 'perches',
  building_type: 'residential_house',
  storey_count: 1,
  regulatory_context: {
    jurisdiction_id: 'sri_lanka_uda_standard'
  },
  rooms: [],
  occupant_count: 4,
  separate_kitchen: true,
  parking_capacity: 0,
  attached_bathroom_count: 0,
  roof_preference: {
    roof_type: 'flat_slab',
    material: 'concrete_tile',
    pitch_angle_deg: 0,
    overhang_m: 0.6,
    parapet_height_m: 1.0,
    rooftop_access: false,
    drainage_preference: 'concealed_gutters'
  }
};

// Empty default-neutral initial survey boundary state
const emptySurveyData: ManualSurveyData = {
  north_angle: 0,
  reference_edge: null,
  source: 'manual',
  edges: [],
};

export default function GabGenPage() {
  const router = useRouter();
  const { projectId, projectName, setOutput, setComponentStatus, skipComponent } = useProjectStore();

  const [activeStep, setActiveStep] = useState<'upload' | 'requirements' | 'survey' | 'generate'>('upload');
  const [requirements, setRequirements] = useState<ClientRequirements>(emptyRequirements);
  const [surveyData, setSurveyData] = useState<ManualSurveyData>(emptySurveyData);
  const [uploadedFileMeta, setUploadedFileMeta] = useState<any>(null);
  const [outputData, setOutputData] = useState<GabGenMasterJson | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [isSavingReq, setIsSavingReq] = useState(false);
  const [isSavingSurvey, setIsSavingSurvey] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Redirect if no project selected
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
      if (ctx.client_requirements && ctx.client_requirements.declared_land_extent) {
        setRequirements(ctx.client_requirements);
      }
      if (ctx.survey_extraction?.edges && ctx.survey_extraction.edges.length > 0) {
        setSurveyData(ctx.survey_extraction);
      }
    }).catch(() => {
      // New project
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
    setErrorMessage(null);
    try {
      const res = await gabGenExtendedApi.uploadSurvey(projectId, file);
      setUploadedFileMeta(res.file_metadata);
      setSuccessMessage("Survey file uploaded and content verified.");
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || "Survey file upload failed.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemoveFile = async () => {
    try {
      await gabGenExtendedApi.removeSurveyFile(projectId);
      setUploadedFileMeta(null);
      setSuccessMessage("Survey file removed.");
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || "Failed to remove survey file.");
    }
  };

  const handleSaveRequirements = async () => {
    if (!requirements.declared_land_extent || requirements.declared_land_extent <= 0) {
      setErrorMessage("Please enter a valid declared land extent (> 0).");
      return;
    }
    setIsSavingReq(true);
    setErrorMessage(null);
    try {
      await gabGenExtendedApi.saveRequirements(projectId, requirements);
      setSuccessMessage("Requirements and regulatory context saved.");
      setActiveStep('survey');
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || "Failed to save client requirements.");
    } finally {
      setIsSavingReq(false);
    }
  };

  const handleSaveSurvey = async () => {
    if (surveyData.edges.length < 3) {
      setErrorMessage("At least 3 survey boundary edges are required.");
      return;
    }
    setIsSavingSurvey(true);
    setErrorMessage(null);
    try {
      await gabGenExtendedApi.saveManualSurveyData(projectId, surveyData);
      setSuccessMessage("Survey boundary data saved.");
      setActiveStep('generate');
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || "Failed to save survey measurements.");
    } finally {
      setIsSavingSurvey(false);
    }
  };

  const handleGenerate = async () => {
    setErrorMessage(null);
    setSuccessMessage(null);

    // Validation checks before invoking generator
    if (!uploadedFileMeta) {
      setErrorMessage("Uploaded deed / survey plan file is required before blueprint generation.");
      setActiveStep('upload');
      return;
    }
    if (!requirements.declared_land_extent || requirements.declared_land_extent <= 0) {
      setErrorMessage("Please complete client requirements with declared land extent.");
      setActiveStep('requirements');
      return;
    }
    if (surveyData.edges.length < 3) {
      setErrorMessage("At least 3 verified survey boundary edges are required.");
      setActiveStep('survey');
      return;
    }

    setIsGenerating(true);
    try {
      // Save latest state
      await gabGenExtendedApi.saveRequirements(projectId, requirements);
      await gabGenExtendedApi.saveManualSurveyData(projectId, surveyData);

      const result = await gabGenExtendedApi.generate(projectId);
      setOutputData(result.master_json);
      setOutput('gab_gen', result.master_json);

      // Map status safely
      if (result.status === 'completed') {
        setComponentStatus('gab_gen', 'completed');
        setSuccessMessage("GAB-Gen Stage 1 Blueprint generated successfully!");
      } else if (result.status === 'needs_verification') {
        // Needs verification status
        setComponentStatus('gab_gen', 'completed');
        setErrorMessage(`Blueprint generated with warnings: ${result.warnings?.join('; ') || 'Requires surveyor verification.'}`);
      } else if (result.status === 'infeasible') {
        setErrorMessage(`Generation Infeasible: ${result.validation?.violations?.join('; ') || 'Constraints exceeded capacity.'}`);
      } else {
        setErrorMessage(`Generation Status: ${result.status}`);
      }
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || "Blueprint generation failed. Please verify inputs.");
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
        {/* Banner for Error / Success messages (No alert() dialogs) */}
        {errorMessage && (
          <div className="mb-6 p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <button onClick={() => setErrorMessage(null)} className="text-destructive font-bold text-sm">×</button>
          </div>
        )}

        {successMessage && (
          <div className="mb-6 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{successMessage}</span>
            </div>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-400 font-bold text-sm">×</button>
          </div>
        )}

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
                  onRemoveFile={handleRemoveFile}
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
                  projectId={projectId}
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
            <BlueprintViewer
              data={outputData}
              projectName={projectName}
              projectId={projectId}
              onUpdate={(updated) => {
                setOutputData(updated);
                setOutput('gab_gen', updated);
              }}
            />
          </div>

        </div>
      </div>
    </FeatureWorkflowShell>
  );
}
