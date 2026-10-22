import type {
  ExteriorLandscape,
  ELIAValidationResponse,
  ELIAResultResponse,
  EliaCandidateRecord,
  EliaContextFreshness,
  EliaUnresolvedMutation,
  LockedFeatureRequirement,
  ProjectFeasibilityResponse,
  PlantCatalogueEntry,
  PlantAlternativeProposal,
  AcceptedPlantAlternative,
  PlantSuitabilityAssessment,
} from '../types/elia';
import { eliaApi, type SriLankaLocation, type LiveSolarConditions } from './api/elia';
import {
  serializeRequirements,
  deserializeRequirements,
  validateRequirementsForm,
  computeRequirementsFingerprint,
  EliaFormState,
  EliaSelectedLocation,
} from './eliaSerialization';
import { parseEliaError, EliaParsedError } from './eliaError';

function deepcopy<T>(obj: T): T {
  if (obj === undefined || obj === null) return obj;
  return JSON.parse(JSON.stringify(obj));
}

export type EliaReconciledTerminalOutcome = 'completed' | 'infeasible' | 'failed';

export interface EliaRunStatusClassification {
  isProcessing: boolean;
  terminalOutcome: EliaReconciledTerminalOutcome | null;
  isContradictory: boolean;
  contradictionReason?: string;
}

/**
 * Validates that an object conforms to the ELIA ExteriorLandscape contract.
 * Strictly distinguishes valid exterior structures from malformed primitives,
 * arrays, or corrupted nested structures.
 */
/**
 * Validates that an object conforms to the ELIA ExteriorFeature contract.
 * Mirrors backend ExteriorFeatureResponse in schemas.py.
 */
export function validateExteriorFeature(
  feat: unknown,
  path: string
): { valid: true } | { valid: false; error: string } {
  if (feat === null || feat === undefined || typeof feat !== 'object' || Array.isArray(feat)) {
    return { valid: false, error: `${path} must be a feature object.` };
  }
  const f = feat as Record<string, unknown>;

  // json_id: required non-empty string (or id for compatibility)
  const id = f.json_id ?? f.id;
  if (typeof id !== 'string' || id.trim().length === 0) {
    return { valid: false, error: `${path}.json_id must be a non-empty string.` };
  }

  // units: if present, must be 'm'
  if (f.units !== undefined && f.units !== null) {
    if (typeof f.units !== 'string' || f.units !== 'm') {
      return { valid: false, error: `${path}.units must be "m".` };
    }
  }

  // position: optional [number, number] or { x: number, y: number }
  if (f.position !== undefined && f.position !== null) {
    if (Array.isArray(f.position)) {
      if (f.position.length < 2 || !f.position.slice(0, 2).every((p) => typeof p === 'number' && Number.isFinite(p))) {
        return { valid: false, error: `${path}.position array must contain at least 2 finite numbers [x, y].` };
      }
    } else if (typeof f.position === 'object') {
      const pos = f.position as Record<string, unknown>;
      if (typeof pos.x !== 'number' || !Number.isFinite(pos.x) || typeof pos.y !== 'number' || !Number.isFinite(pos.y)) {
        return { valid: false, error: `${path}.position object must contain finite numeric x and y.` };
      }
    } else {
      return { valid: false, error: `${path}.position must be a coordinate array or {x, y} object.` };
    }
  }

  // polygon: optional ring coordinates
  if (f.polygon !== undefined && f.polygon !== null) {
    if (!Array.isArray(f.polygon)) {
      return { valid: false, error: `${path}.polygon must be an array of coordinate pairs.` };
    }
    for (let i = 0; i < f.polygon.length; i++) {
      const pt = f.polygon[i];
      if (!Array.isArray(pt) || pt.length < 2 || typeof pt[0] !== 'number' || !Number.isFinite(pt[0]) || typeof pt[1] !== 'number' || !Number.isFinite(pt[1])) {
        return { valid: false, error: `${path}.polygon[${i}] must be a finite coordinate pair [x, y].` };
      }
    }
  }

  // dimensions: optional Record<string, number>
  if (f.dimensions !== undefined && f.dimensions !== null) {
    if (typeof f.dimensions !== 'object' || Array.isArray(f.dimensions)) {
      return { valid: false, error: `${path}.dimensions must be an object.` };
    }
    for (const [key, val] of Object.entries(f.dimensions)) {
      if (typeof val !== 'number' || !Number.isFinite(val) || val <= 0) {
        return { valid: false, error: `${path}.dimensions.${key} must be a positive finite number.` };
      }
    }
  }

  // rotation_degrees: optional finite number
  if (f.rotation_degrees !== undefined && f.rotation_degrees !== null) {
    if (typeof f.rotation_degrees !== 'number' || !Number.isFinite(f.rotation_degrees)) {
      return { valid: false, error: `${path}.rotation_degrees must be a finite number.` };
    }
  }

  // Specific numeric metric fields read by viewer if present
  for (const numField of ['height_m', 'canopy_radius_m', 'width_m', 'depth_m', 'elevation_m'] as const) {
    if (f[numField] !== undefined && f[numField] !== null) {
      if (typeof f[numField] !== 'number' || !Number.isFinite(f[numField] as number)) {
        return { valid: false, error: `${path}.${numField} must be a finite number.` };
      }
    }
  }

  return { valid: true };
}

/**
 * Safely format validation violations into a readable string without throwing
 * on non-array or malformed values.
 */
export function formatViolations(violations: unknown, fallback: string): string {
  if (Array.isArray(violations) && violations.length > 0) {
    return violations.map((v) => String(v)).join('; ');
  }
  return fallback;
}

/**
 * Validates that an object conforms to the ELIA ExteriorLandscape contract.
 * Strictly distinguishes valid exterior structures from malformed primitives,
 * arrays, or corrupted nested structures.
 */
export function validateExteriorLandscape(
  val: unknown
): { valid: true; value: ExteriorLandscape } | { valid: false; error: string } {
  if (val === null || val === undefined) {
    return { valid: false, error: 'Exterior payload is missing or null.' };
  }
  if (typeof val !== 'object' || Array.isArray(val)) {
    return { valid: false, error: 'Exterior landscape must be a JSON object, not a primitive or array.' };
  }

  const obj = val as Record<string, unknown>;

  // 1. run_id: required non-empty string
  if (typeof obj.run_id !== 'string' || obj.run_id.trim() === '') {
    return { valid: false, error: 'Exterior landscape requires a valid non-empty run_id string.' };
  }

  // 2. access: required object
  if (!obj.access || typeof obj.access !== 'object' || Array.isArray(obj.access)) {
    return { valid: false, error: 'Exterior landscape requires an access object structure.' };
  }

  const access = obj.access as Record<string, unknown>;
  if (access.gate !== undefined && access.gate !== null) {
    const vf = validateExteriorFeature(access.gate, 'access.gate');
    if (!vf.valid) return vf;
  }
  if (access.garage !== undefined && access.garage !== null) {
    const vf = validateExteriorFeature(access.garage, 'access.garage');
    if (!vf.valid) return vf;
  }
  if (access.driveway !== undefined && access.driveway !== null) {
    const vf = validateExteriorFeature(access.driveway, 'access.driveway');
    if (!vf.valid) return vf;
  }
  if (access.gates !== undefined && access.gates !== null) {
    if (!Array.isArray(access.gates)) {
      return { valid: false, error: 'access.gates must be an array when present.' };
    }
    for (let i = 0; i < access.gates.length; i++) {
      const vf = validateExteriorFeature(access.gates[i], `access.gates[${i}]`);
      if (!vf.valid) return vf;
    }
  }

  // 3. Optional collection structures consumed by visualization components
  if (obj.vegetation_nodes !== undefined && obj.vegetation_nodes !== null) {
    if (!Array.isArray(obj.vegetation_nodes)) {
      return { valid: false, error: 'vegetation_nodes must be an array when present.' };
    }
    for (let i = 0; i < obj.vegetation_nodes.length; i++) {
      const vf = validateExteriorFeature(obj.vegetation_nodes[i], `vegetation_nodes[${i}]`);
      if (!vf.valid) return vf;
    }
  }

  if (obj.outdoor_elements !== undefined && obj.outdoor_elements !== null) {
    if (!Array.isArray(obj.outdoor_elements)) {
      return { valid: false, error: 'outdoor_elements must be an array when present.' };
    }
    for (let i = 0; i < obj.outdoor_elements.length; i++) {
      const vf = validateExteriorFeature(obj.outdoor_elements[i], `outdoor_elements[${i}]`);
      if (!vf.valid) return vf;
    }
  }

  if (obj.vertical_greenery !== undefined && obj.vertical_greenery !== null) {
    if (typeof obj.vertical_greenery !== 'object' || Array.isArray(obj.vertical_greenery)) {
      return { valid: false, error: 'vertical_greenery must be an object when present.' };
    }
    const vg = obj.vertical_greenery as Record<string, unknown>;
    if (vg.elements !== undefined && vg.elements !== null) {
      if (!Array.isArray(vg.elements)) {
        return { valid: false, error: 'vertical_greenery.elements must be an array when present.' };
      }
      for (let i = 0; i < vg.elements.length; i++) {
        const vf = validateExteriorFeature(vg.elements[i], `vertical_greenery.elements[${i}]`);
        if (!vf.valid) return vf;
      }
    }
  }

  if (obj.outdoor_lighting !== undefined && obj.outdoor_lighting !== null) {
    if (typeof obj.outdoor_lighting !== 'object' || Array.isArray(obj.outdoor_lighting)) {
      return { valid: false, error: 'outdoor_lighting must be an object when present.' };
    }
    const ol = obj.outdoor_lighting as Record<string, unknown>;
    if (ol.nodes !== undefined && ol.nodes !== null) {
      if (!Array.isArray(ol.nodes)) {
        return { valid: false, error: 'outdoor_lighting.nodes must be an array when present.' };
      }
      for (let i = 0; i < ol.nodes.length; i++) {
        const vf = validateExteriorFeature(ol.nodes[i], `outdoor_lighting.nodes[${i}]`);
        if (!vf.valid) return vf;
      }
    }
  }

  // 4. validation_summary validation (Fix 1)
  if (obj.validation_summary !== undefined && obj.validation_summary !== null) {
    if (typeof obj.validation_summary !== 'object' || Array.isArray(obj.validation_summary)) {
      return { valid: false, error: 'validation_summary must be an object when present.' };
    }
    const vs = obj.validation_summary as Record<string, unknown>;
    if (vs.valid !== undefined && typeof vs.valid !== 'boolean') {
      return { valid: false, error: 'validation_summary.valid must be a boolean.' };
    }
    if (vs.violations !== undefined && vs.violations !== null) {
      if (!Array.isArray(vs.violations)) {
        return { valid: false, error: 'validation_summary.violations must be an array of strings.' };
      }
      for (let i = 0; i < vs.violations.length; i++) {
        if (typeof vs.violations[i] !== 'string') {
          return { valid: false, error: `validation_summary.violations[${i}] must be a string.` };
        }
      }
    }
    if (vs.checks_passed !== undefined && vs.checks_passed !== null) {
      if (typeof vs.checks_passed !== 'number' || !Number.isInteger(vs.checks_passed) || vs.checks_passed < 0) {
        return { valid: false, error: 'validation_summary.checks_passed must be a non-negative integer.' };
      }
    }
    if (vs.checks_total !== undefined && vs.checks_total !== null) {
      if (typeof vs.checks_total !== 'number' || !Number.isInteger(vs.checks_total) || vs.checks_total < 0) {
        return { valid: false, error: 'validation_summary.checks_total must be a non-negative integer.' };
      }
    }
    if (vs.constraint_satisfaction_rate !== undefined && vs.constraint_satisfaction_rate !== null) {
      if (
        typeof vs.constraint_satisfaction_rate !== 'number' ||
        !Number.isFinite(vs.constraint_satisfaction_rate) ||
        vs.constraint_satisfaction_rate < 0 ||
        vs.constraint_satisfaction_rate > 1
      ) {
        return { valid: false, error: 'validation_summary.constraint_satisfaction_rate must be a finite number between 0 and 1.' };
      }
    }
  }

  // 5. environment validation
  if (obj.environment !== undefined && obj.environment !== null) {
    if (typeof obj.environment !== 'object' || Array.isArray(obj.environment)) {
      return { valid: false, error: 'environment must be an object when present.' };
    }
    const env = obj.environment as Record<string, unknown>;
    if (env.north_angle !== undefined && env.north_angle !== null) {
      if (typeof env.north_angle !== 'number' || !Number.isFinite(env.north_angle)) {
        return { valid: false, error: 'environment.north_angle must be a finite number.' };
      }
    }
  }

  return { valid: true, value: obj as unknown as ExteriorLandscape };
}

const KNOWN_STATUSES = new Set(['processing', 'completed', 'infeasible', 'failed']);

/**
 * Classifies execution lifecycle status vs design feasibility outcome across backend channels.
 * Contract:
 *  - ComponentRun.status (latestResult) is 'completed' when generation finishes, even if outcome is 'infeasible'.
 *  - Master JSON processing.elia_engine.status is 'infeasible' for that same run.
 *  - Therefore: procStatus='infeasible' + latestResultStatus='completed' is a valid terminal infeasible outcome.
 */
export function classifyCorrelatedRunStatus(
  procStatus: string | null,
  procOutcome: string | null,
  latestResultStatus: string | null,
  latestResultOutput: any
): EliaRunStatusClassification {
  if (!procStatus && !latestResultStatus) {
    return { isProcessing: false, terminalOutcome: null, isContradictory: false };
  }

  // Check for unknown/unrecognized status strings
  if (procStatus !== null && !KNOWN_STATUSES.has(procStatus)) {
    return {
      isProcessing: false,
      terminalOutcome: null,
      isContradictory: true,
      contradictionReason: `Unrecognized processing status '${procStatus}' encountered during reconciliation.`,
    };
  }
  if (latestResultStatus !== null && !KNOWN_STATUSES.has(latestResultStatus)) {
    return {
      isProcessing: false,
      terminalOutcome: null,
      isContradictory: true,
      contradictionReason: `Unrecognized latest run status '${latestResultStatus}' encountered during reconciliation.`,
    };
  }

  // 1. In-flight processing
  if (procStatus === 'processing' || latestResultStatus === 'processing') {
    if (
      (procStatus === 'processing' && latestResultStatus && latestResultStatus !== 'processing') ||
      (latestResultStatus === 'processing' && procStatus && procStatus !== 'processing')
    ) {
      return {
        isProcessing: false,
        terminalOutcome: null,
        isContradictory: true,
        contradictionReason: `Channel status mismatch: processing channel reported '${procStatus}', but latest run channel reported '${latestResultStatus}'.`,
      };
    }
    return { isProcessing: true, terminalOutcome: null, isContradictory: false };
  }

  // 2. Consistent terminal failures
  if (procStatus === 'failed' && (latestResultStatus === 'failed' || !latestResultStatus)) {
    return { isProcessing: false, terminalOutcome: 'failed', isContradictory: false };
  }
  if (latestResultStatus === 'failed' && (procStatus === 'failed' || !procStatus)) {
    return { isProcessing: false, terminalOutcome: 'failed', isContradictory: false };
  }

  // 3. Genuine contradiction: failed vs completed/infeasible
  if (
    (procStatus === 'failed' && (latestResultStatus === 'completed' || latestResultStatus === 'infeasible')) ||
    (latestResultStatus === 'failed' && (procStatus === 'completed' || procStatus === 'infeasible'))
  ) {
    return {
      isProcessing: false,
      terminalOutcome: null,
      isContradictory: true,
      contradictionReason: `Contradictory terminal status: one channel reported failure while the other reported execution completion ('${procStatus}' vs '${latestResultStatus}').`,
    };
  }

  // 4. Infeasible design outcome recognition:
  // Backend contract: ComponentRun.status is 'completed', while processing.elia_engine.status is 'infeasible'.
  const procIsInfeasible = procStatus === 'infeasible' || procOutcome === 'infeasible';
  const latestResultHasInfeasibleOutput =
    latestResultOutput &&
    typeof latestResultOutput === 'object' &&
    ((latestResultOutput.validation_summary && latestResultOutput.validation_summary.valid === false) ||
      (Array.isArray(latestResultOutput.validation_summary?.violations) &&
        latestResultOutput.validation_summary.violations.length > 0) ||
      latestResultOutput.outcome === 'infeasible');

  if (procIsInfeasible) {
    if (latestResultStatus === 'completed' || latestResultStatus === 'infeasible' || !latestResultStatus) {
      return { isProcessing: false, terminalOutcome: 'infeasible', isContradictory: false };
    }
  }

  if (latestResultStatus === 'infeasible') {
    if (procStatus === 'infeasible' || !procStatus) {
      return { isProcessing: false, terminalOutcome: 'infeasible', isContradictory: false };
    }
    if (procStatus === 'completed') {
      if (procOutcome !== 'infeasible') {
        return {
          isProcessing: false,
          terminalOutcome: null,
          isContradictory: true,
          contradictionReason: `Contradictory status: processing reported completed valid design but latest run reported infeasible outcome.`,
        };
      }
      return { isProcessing: false, terminalOutcome: 'infeasible', isContradictory: false };
    }
  }

  // 5. Successful valid execution
  if (procStatus === 'completed') {
    if (procOutcome === 'infeasible' || latestResultHasInfeasibleOutput) {
      return { isProcessing: false, terminalOutcome: 'infeasible', isContradictory: false };
    }
    if (latestResultStatus === 'completed' || !latestResultStatus) {
      return { isProcessing: false, terminalOutcome: 'completed', isContradictory: false };
    }
  }

  if (latestResultStatus === 'completed' && !procStatus) {
    // Missing processing status evidence in Master JSON
    return {
      isProcessing: false,
      terminalOutcome: null,
      isContradictory: false,
    };
  }

  return {
    isProcessing: false,
    terminalOutcome: null,
    isContradictory: true,
    contradictionReason: `Unsupported status combination: procStatus='${procStatus}', latestResultStatus='${latestResultStatus}'.`,
  };
}

export function getConceptDefaults(concept: string): Partial<EliaFormState> {
  const c = concept.toLowerCase().trim();
  if (c === 'greeny' || c === 'green') {
    return {
      designStyle: 'greeny',
      greeneryDensity: 'high',
      gardenGroundFinish: 'grass',
      lawnRequired: true,
      treesRequired: true,
      shadeTreePreference: true,
      wallClimbingPlants: true,
      verticalGreeneryMode: 'preferred',
      lightingStyle: 'lantern',
      drivewayStyle: 'curved',
    };
  }
  if (c === 'minimalistic' || c === 'minimalist') {
    return {
      designStyle: 'minimalistic',
      greeneryDensity: 'low',
      openSpaceRatio: 0.4,
      boundaryWallType: 'masonry',
      lightingStyle: 'minimal',
      verticalGreeneryMode: 'automatic',
      drivewayStyle: 'straight',
    };
  }
  return {
    designStyle: 'modern',
    greeneryDensity: 'medium',
    gardenGroundFinish: 'interlock',
    boundaryWallType: 'rendered_brick',
    lightingStyle: 'minimal',
    drivewayStyle: 'straight',
  };
}

export function createDefaultFormState(): EliaFormState {
  return {
    generationMode: 'baseline',
    designStyle: 'modern',
    greeneryDensity: 'medium',
    openSpaceRatio: 0.3,
    shadeTreePreference: false,

    // Group B: Parking & Garage
    parkingRequired: true,
    parkingType: 'no_preference',
    garageRequired: false,
    garageCapacity: 1,
    vehicleCount: 1,
    vehicleType: 'car',
    turningSpaceRequired: true,

    // Group C: Driveway, Walkways, Gate
    drivewayRequired: true,
    drivewayStyle: 'auto',
    drivewaySurface: 'interlock',
    pedestrianPathRequired: false,
    gardenPathRequired: false,
    walkingPathSurface: 'paving_stones',
    gateRequired: true,
    gateType: 'unspecified',
    gateWidthM: 3.6,
    gateOpeningMechanism: 'unspecified',
    gateStyle: 'unspecified',

    // Group D: Ground Finishes
    gardenGroundFinish: 'grass',

    // Group E: Garden & Ground Planting
    gardenRequired: true,
    lawnRequired: false,
    treesRequired: true,
    compactTreesPreference: false,
    shrubsRequired: false,
    flowerBedsRequired: false,
    groundPlantersRequired: false,
    gardenSeatingRequired: false,
    gardenTableSetRequired: false,

    // Group F: Walls & Vertical Greenery
    boundaryWallRequired: false,
    boundaryWallType: 'masonry',
    boundaryWallHeightM: 1.8,
    verticalGreeneryMode: 'automatic',
    wallClimbingPlants: false,
    wallMountedGreenery: false,
    hangingTrailingGreenery: false,
    acceptVerticalAlternatives: false,

    // Group G: Balconies
    balconyPlantingRequired: false,
    balconyPottedPlants: false,
    balconyHangingPlants: false,
    balconySeatingRequired: false,
    balconyPlantIds: [],
    targetBalconyIds: [],

    // Group H: Rooftop / Terrace
    rooftopPlantingRequired: false,
    rooftopPlantersRequired: false,
    rooftopSeatingRequired: false,
    rooftopTablesRequired: false,
    targetTerraceIds: [],

    // Group I: Outdoor Lighting
    lightingRequired: false,
    lightingStyle: 'minimal',
    lightingSpacingM: 8.0,
    gardenLighting: false,
    pathwayLighting: false,
    seatingLighting: false,
    wallLighting: false,

    // Group J: Water Features & Utilities
    wellRequired: false,
    gardenTapsRequired: false,
    gardenTapsCount: 1,
    pondRequired: false,
    poolRequired: false,
    septicTankRequired: false,

    // Group K: Solar
    solarRequired: false,
    preferredRoofSurface: 'auto',
    placementPriority: 'balanced',
    includeLiveSolar: false,

    // Environmental & Botanical Preferences
    maintenancePreference: 'no_preference',
    waterAvailability: 'unknown',
    climateZone: 'unknown',
    siteExposure: 'unknown',
    preferredPlantIds: [],
    plantIdsToAvoid: [],
    acceptedPlantAlternatives: [],
    rejectedPlantAlternatives: [],
    lockedFeatures: [],

    selectedLocation: null,
  };
}

export interface EliaWorkflowState {
  projectId: string | null;
  sessionSeq: number;
  isMounted: boolean;
  isActive: boolean;

  // Context channel
  contextFreshness: EliaContextFreshness;
  authoritativeMaster: Record<string, unknown> | null;
  sourceRevision: number | null;
  contextError: string | null;
  conflictError: string | null;
  isLoadingContext: boolean;

  // Requirements & Form
  formState: EliaFormState;
  requirementsDirty: boolean;
  lastSubmittedFingerprint: string | null;

  // Validation & Feasibility channel
  isValidating: boolean;
  validationResult: ELIAValidationResponse | null;
  feasibilityResult: ProjectFeasibilityResponse | null;
  validationError: string | null;

  // Candidate with atomic provenance
  candidate: EliaCandidateRecord | null;
  acceptedLandscape: ExteriorLandscape | null;
  acceptedProvenance: {
    projectId: string;
    sourceRevision: number | null;
    sourceSnapshot?: Record<string, unknown> | null;
    runId?: string;
  } | null;
  activeView: 'candidate' | 'accepted';

  // Mutation states
  isPreviewing: boolean;
  isGenerating: boolean;
  actionError: string | null;
  requiresReconciliation: boolean;
  unresolvedMutation: EliaUnresolvedMutation | null;
  isReconciling: boolean;

  // Latest run channel
  latestRun: ELIAResultResponse | null;
  latestRunError: string | null;
  isCheckingRun: boolean;

  // Location / Solar channel
  locations: SriLankaLocation[];
  isSearchingLocation: boolean;
  locationError: string | null;
  solar: LiveSolarConditions | null;
  isLoadingSolar: boolean;

  // Object Customization channel (Panel Feedback)
  selectedFeatureId: string | null;
  candidateEditHistory: ExteriorLandscape[];
  candidateValidationError: string | null;
  candidateValidationViolations: string[];
  isValidatingCandidate: boolean;
  isSavingCandidate: boolean;
  saveCandidateError: string | null;

  // Botanical Catalogue & Greeny Alternatives channel (Stage 3)
  plantCatalogue: PlantCatalogueEntry[] | null;
  plantCatalogueVersion: string | null;
  isLoadingPlantCatalogue: boolean;
  plantCatalogueError: string | null;
  plantSuitabilityAssessments: Record<string, PlantSuitabilityAssessment>;
  isEvaluatingPlant: boolean;
  plantAlternativeProposals: PlantAlternativeProposal[];
}

export interface EliaApiInterface {
  getContext(projectId: string, options?: { signal?: AbortSignal }): Promise<{ master_json: any; revision?: number | null }>;
  getResult(projectId: string, options?: { signal?: AbortSignal }): Promise<ELIAResultResponse>;
  validateInput(projectId: string, payload: any, options?: { signal?: AbortSignal }): Promise<ELIAValidationResponse>;
  preview(payload: any, options?: { signal?: AbortSignal }): Promise<{ run_id: string; outcome: 'valid' | 'infeasible'; exterior_landscape: ExteriorLandscape }>;
  run(projectId: string, payload: any, options?: { signal?: AbortSignal }): Promise<{ run_id: string; outcome: 'valid' | 'infeasible'; exterior_landscape: ExteriorLandscape; master_json_updated?: boolean }>;
  searchLocations?(query: string, options?: { signal?: AbortSignal }): Promise<{ results: SriLankaLocation[] }>;
  currentSolar?(projectId: string, location: any, options?: { signal?: AbortSignal }): Promise<LiveSolarConditions>;
  validateCandidate?(projectId: string, payload: any, options?: { signal?: AbortSignal }): Promise<any>;
  saveCandidate?(projectId: string, payload: any, options?: { signal?: AbortSignal }): Promise<any>;
  getVegetationCatalog?(options?: { signal?: AbortSignal }): Promise<Record<string, unknown>>;
  getPlantCatalogue?(projectId: string, params?: any, options?: { signal?: AbortSignal }): Promise<{ catalogue_version: string; total_entries: number; entries: PlantCatalogueEntry[]; sources: Record<string, string> }>;
  evaluatePlantSuitability?(projectId: string, payload: any, options?: { signal?: AbortSignal }): Promise<{ assessment: PlantSuitabilityAssessment; alternatives: PlantAlternativeProposal[] }>;
  updatePlantAlternatives?(projectId: string, actions: any[], options?: { signal?: AbortSignal }): Promise<any>;
}

export class EliaWorkflowController {
  private state: EliaWorkflowState;
  private listeners = new Set<(state: EliaWorkflowState) => void>();

  // Channel sequence IDs for same-project request ordering
  private contextReqId = 0;
  private latestRunReqId = 0;
  private validationReqId = 0;
  private mutationReqId = 0;
  private locationSearchReqId = 0;
  private solarReqId = 0;

  // Candidate edit versioning & async request sequencing
  private candidateEditVersion = 0;
  private candidateValidationReqId = 0;
  private candidateSaveReqId = 0;

  // Synchronous guard with token ownership
  private isMutatingSync = false;
  private mutationTokenSeq = 0;
  private activeMutationToken = 0;

  // Mutation epoch tracking to establish request boundaries
  private mutationEpoch = 0;
  private activeMutationEpoch: number | null = null;

  // Reconciliation synchronous guard and request tracking
  private isReconcilingSync = false;
  private reconciliationReqId = 0;
  private activeReconciliationToken = 0;

  // Stable static server snapshot for SSR without hydration mismatch
  private static serverSnapshot: EliaWorkflowState | null = null;

  public static getServerSnapshot(): EliaWorkflowState {
    if (!EliaWorkflowController.serverSnapshot) {
      EliaWorkflowController.serverSnapshot = Object.freeze({
        projectId: null,
        sessionSeq: 0,
        isMounted: false,
        isActive: false,
        contextFreshness: 'unavailable',
        authoritativeMaster: null,
        sourceRevision: null,
        contextError: null,
        conflictError: null,
        isLoadingContext: false,
        formState: createDefaultFormState(),
        requirementsDirty: false,
        lastSubmittedFingerprint: null,
        isValidating: false,
        validationResult: null,
        feasibilityResult: null,
        validationError: null,
        candidate: null,
        acceptedLandscape: null,
        acceptedProvenance: null,
        activeView: 'accepted',
        isPreviewing: false,
        isGenerating: false,
        actionError: null,
        requiresReconciliation: false,
        unresolvedMutation: null,
        isReconciling: false,
        latestRun: null,
        latestRunError: null,
        isCheckingRun: false,
        locations: [],
        isSearchingLocation: false,
        locationError: null,
        solar: null,
        isLoadingSolar: false,
        selectedFeatureId: null,
        candidateEditHistory: [],
        candidateValidationError: null,
        candidateValidationViolations: [],
        isValidatingCandidate: false,
        isSavingCandidate: false,
        saveCandidateError: null,
        plantCatalogue: null,
        plantCatalogueVersion: null,
        isLoadingPlantCatalogue: false,
        plantCatalogueError: null,
        plantSuitabilityAssessments: {},
        isEvaluatingPlant: false,
        plantAlternativeProposals: [],
      }) as EliaWorkflowState;
    }
    return EliaWorkflowController.serverSnapshot;
  }

  public getServerSnapshot(): EliaWorkflowState {
    return EliaWorkflowController.getServerSnapshot();
  }

  constructor(initialProjectId: string | null = null) {
    this.state = {
      projectId: initialProjectId,
      sessionSeq: initialProjectId ? 1 : 0,
      isMounted: Boolean(initialProjectId),
      isActive: Boolean(initialProjectId),

      contextFreshness: initialProjectId ? 'loading' : 'unavailable',
      authoritativeMaster: null,
      sourceRevision: null,
      contextError: null,
      conflictError: null,
      isLoadingContext: false,

      formState: createDefaultFormState(),
      requirementsDirty: false,
      lastSubmittedFingerprint: null,

      isValidating: false,
      validationResult: null,
      feasibilityResult: null,
      validationError: null,

      candidate: null,
      acceptedLandscape: null,
      acceptedProvenance: null,
      activeView: 'accepted',

      isPreviewing: false,
      isGenerating: false,
      actionError: null,
      requiresReconciliation: false,
      unresolvedMutation: null,
      isReconciling: false,

      latestRun: null,
      latestRunError: null,
      isCheckingRun: false,

      locations: [],
      isSearchingLocation: false,
      locationError: null,
      solar: null,
      isLoadingSolar: false,

      selectedFeatureId: null,
      candidateEditHistory: [],
      candidateValidationError: null,
      candidateValidationViolations: [],
      isValidatingCandidate: false,
      isSavingCandidate: false,
      saveCandidateError: null,

      plantCatalogue: null,
      plantCatalogueVersion: null,
      isLoadingPlantCatalogue: false,
      plantCatalogueError: null,
      plantSuitabilityAssessments: {},
      isEvaluatingPlant: false,
      plantAlternativeProposals: [],
    };
  }

  public getState(): EliaWorkflowState {
    return this.state;
  }

  public subscribe(listener: (state: EliaWorkflowState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify() {
    this.listeners.forEach((listener) => {
      listener(this.state);
    });
  }

  private setState(patch: Partial<EliaWorkflowState>) {
    this.state = { ...this.state, ...patch };
    this.notify();
  }

  private acquireMutationGuard(): number | null {
    if (this.isMutatingSync || this.state.isGenerating || this.state.isPreviewing) {
      return null;
    }
    this.isMutatingSync = true;
    this.activeMutationToken = ++this.mutationTokenSeq;
    return this.activeMutationToken;
  }

  private releaseMutationGuard(token: number) {
    if (this.activeMutationToken === token) {
      this.isMutatingSync = false;
      this.activeMutationToken = 0;
    }
  }

  /**
   * Explicit Lifecycle: Activation
   * Establishes fresh lifecycle identity and unblocks request dispatching.
   * Preserves session invalidation for pre-activation requests.
   */
  public activate(projectId: string | null = null): number {
    this.state.isMounted = true;
    this.state.isActive = true;
    const newSession = ++this.state.sessionSeq;

    // Reset sequence counters and advance mutation epoch so pre-activation requests are obsolete
    this.contextReqId += 1;
    this.latestRunReqId += 1;
    this.validationReqId += 1;
    this.mutationReqId += 1;
    this.locationSearchReqId += 1;
    this.solarReqId += 1;
    this.candidateValidationReqId += 1;
    this.candidateSaveReqId += 1;
    this.candidateEditVersion += 1;

    this.mutationEpoch += 1;
    this.activeMutationEpoch = null;

    this.isMutatingSync = false;
    this.activeMutationToken = 0;

    this.isReconcilingSync = false;
    this.activeReconciliationToken = 0;
    this.reconciliationReqId += 1;

    if (this.state.projectId !== projectId) {
      this.setState({
        projectId,
        sessionSeq: newSession,
        isMounted: true,
        isActive: true,
        contextFreshness: projectId ? 'loading' : 'unavailable',
        authoritativeMaster: null,
        sourceRevision: null,
        contextError: null,
        conflictError: null,
        isLoadingContext: false,

        formState: createDefaultFormState(),
        requirementsDirty: false,
        lastSubmittedFingerprint: null,

        isValidating: false,
        validationResult: null,
        feasibilityResult: null,
        validationError: null,

        candidate: null,
        acceptedLandscape: null,
        acceptedProvenance: null,
        activeView: 'accepted',

        isPreviewing: false,
        isGenerating: false,
        actionError: null,
        requiresReconciliation: false,
        unresolvedMutation: null,
        isReconciling: false,

        latestRun: null,
        latestRunError: null,
        isCheckingRun: false,

        locations: [],
        isSearchingLocation: false,
        locationError: null,
        solar: null,
        isLoadingSolar: false,

        selectedFeatureId: null,
        candidateEditHistory: [],
        candidateValidationError: null,
        candidateValidationViolations: [],
        isValidatingCandidate: false,
        isSavingCandidate: false,
        saveCandidateError: null,
      });
    } else {
      this.setState({
        sessionSeq: newSession,
        isMounted: true,
        isActive: true,
        isLoadingContext: false,
        isValidating: false,
        isPreviewing: false,
        isGenerating: false,
        isCheckingRun: false,
        isLoadingSolar: false,
        isSearchingLocation: false,
        isReconciling: false,
      });
    }

    return newSession;
  }

  /**
   * Explicit Lifecycle: Deactivation / Unmount
   * Invalidates in-flight requests and prevents any future store writes.
   */
  public deactivate(): void {
    this.state.isMounted = false;
    this.state.isActive = false;
    this.state.sessionSeq += 1;

    this.contextReqId += 1;
    this.latestRunReqId += 1;
    this.validationReqId += 1;
    this.mutationReqId += 1;
    this.locationSearchReqId += 1;
    this.solarReqId += 1;
    this.candidateValidationReqId += 1;
    this.candidateSaveReqId += 1;

    this.mutationEpoch += 1;
    this.activeMutationEpoch = null;

    this.isMutatingSync = false;
    this.activeMutationToken = 0;

    this.isReconcilingSync = false;
    this.activeReconciliationToken = 0;
    this.reconciliationReqId += 1;

    this.setState({
      isMounted: false,
      isActive: false,
      isLoadingContext: false,
      isValidating: false,
      isPreviewing: false,
      isGenerating: false,
      isCheckingRun: false,
      isLoadingSolar: false,
      isSearchingLocation: false,
      isReconciling: false,
    });
  }

  public changeProject(newProjectId: string | null) {
    this.activate(newProjectId);
  }

  public unmount() {
    this.deactivate();
  }

  public editRequirement(patch: Partial<EliaFormState>) {
    const updatedForm = { ...this.state.formState, ...patch };
    if (this.state.candidate) {
      this.candidateEditVersion += 1;
    }
    this.setState({
      formState: updatedForm,
      requirementsDirty: true,
      validationResult: null, // Invalidate prior validation success immediately!
      validationError: null,
      actionError: null,
      candidateValidationError: null,
      candidateValidationViolations: [],
    });
  }

  public reapplyConceptDefaults(conceptOverride?: string) {
    const concept = conceptOverride || this.state.formState.designStyle || 'modern';
    const defaults = getConceptDefaults(concept);
    this.editRequirement(defaults);
  }

  public selectLocation(loc: SriLankaLocation | EliaSelectedLocation | null) {
    this.solarReqId += 1; // Invalidate any in-flight solar request
    const updatedForm = { ...this.state.formState, selectedLocation: loc };
    this.setState({
      formState: updatedForm,
      solar: null,
      isLoadingSolar: false, // Immediately reset loading flag on location change/clear
      locationError: null,
      requirementsDirty: true,
      validationResult: null,
    });
  }

  public dismissConflict() {
    this.setState({ conflictError: null });
  }

  public dismissActionError() {
    this.setState({ actionError: null, saveCandidateError: null });
  }

  public dismissSaveCandidateError() {
    this.setState({ saveCandidateError: null });
  }

  public toggleActiveView(view: 'candidate' | 'accepted') {
    this.setState({ activeView: view });
  }

  /**
   * Channel: Context Loading
   * Explicit return result: { status: 'success' | 'failed' | 'obsolete' }
   * Preserves conflictError on refresh.
   */
  public async loadAuthoritativeContext(
    api: EliaApiInterface,
    signal?: AbortSignal,
    targetMutationEpoch?: number
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; revision?: number | null; master?: any; error?: string }> {
    const pid = this.state.projectId;
    if (!pid || !this.state.isMounted) return { status: 'obsolete' };

    const session = this.state.sessionSeq;
    const reqId = ++this.contextReqId;
    const reqEpoch = this.mutationEpoch;

    // Transition context to non-current during refresh to block export and mutations
    this.setState({
      isLoadingContext: true,
      contextFreshness: this.state.authoritativeMaster ? 'stale' : 'loading',
      contextError: null,
    });

    try {
      const response = await api.getContext(pid, { signal });
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.contextReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      const isOwnedPostMutation = targetMutationEpoch !== undefined && targetMutationEpoch === this.activeMutationEpoch;

      // An older context read initiated before a newer mutation cannot overwrite post-mutation state
      if (!isOwnedPostMutation && reqEpoch < this.mutationEpoch) {
        this.setState({ isLoadingContext: false });
        return { status: 'obsolete' };
      }

      // Distinguish legitimate absence from malformed or invalid responses
      if (!response || typeof response !== 'object' || !('master_json' in response)) {
        const errorMsg = 'Malformed context response received from server.';
        this.setState({
          contextFreshness: this.state.authoritativeMaster ? 'stale' : 'unavailable',
          contextError: errorMsg,
          isLoadingContext: false,
        });
        return { status: 'failed', error: errorMsg };
      }

      const doc = response.master_json;
      if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
        const errorMsg = 'Malformed Master JSON in context response.';
        this.setState({
          contextFreshness: this.state.authoritativeMaster ? 'stale' : 'unavailable',
          contextError: errorMsg,
          isLoadingContext: false,
        });
        return { status: 'failed', error: errorMsg };
      }

      const rev = response.revision !== undefined && response.revision !== null
        ? response.revision
        : (doc && typeof doc.revision === 'number' ? doc.revision : null);

      const revisionChanged = this.state.sourceRevision !== null && rev !== this.state.sourceRevision;

      // Distinguish:
      // A. Valid accepted exterior
      // B. Legitimate absence of an exterior
      // C. Present but malformed exterior
      let acceptedLandscape: ExteriorLandscape | null = null;
      let acceptedProvenance: {
        projectId: string;
        sourceRevision: number | null;
        sourceSnapshot?: Record<string, unknown> | null;
        runId?: string;
      } | null = null;

      const hasExteriorKey = 'exterior_landscape' in doc;
      const rawExterior = (doc as any).exterior_landscape;

      if (!hasExteriorKey || rawExterior === null || rawExterior === undefined) {
        // Legitimate absence: exterior_landscape is explicitly absent or null
        acceptedLandscape = null;
        acceptedProvenance = null;
      } else {
        // Present: must be validated against the ELIA contract
        const validation = validateExteriorLandscape(rawExterior);
        if (!validation.valid) {
          const errorMsg = `Malformed exterior_landscape in authoritative context: ${validation.error}`;
          this.setState({
            contextFreshness: this.state.authoritativeMaster ? 'stale' : 'unavailable',
            contextError: errorMsg,
            isLoadingContext: false,
          });
          return { status: 'failed', error: errorMsg };
        }
        acceptedLandscape = validation.value;
        acceptedProvenance = {
          projectId: pid,
          sourceRevision: rev,
          sourceSnapshot: doc,
          runId: acceptedLandscape.run_id,
        };
      }

      // Freshness can only be 'current' if no active unowned mutation and no unresolved mutation guard is active
      const canBeCurrent =
        (this.activeMutationEpoch === null || isOwnedPostMutation) &&
        !this.state.requiresReconciliation &&
        this.state.unresolvedMutation === null &&
        (reqEpoch === this.mutationEpoch || isOwnedPostMutation);

      // When the authoritative context legitimately contains no accepted exterior,
      // clear BOTH acceptedLandscape and acceptedProvenance.
      // If activeView was 'accepted' and no accepted design exists, transition to 'candidate' if candidate exists.
      const nextActiveView = acceptedLandscape
        ? this.state.activeView
        : (this.state.candidate ? 'candidate' : 'accepted');

      // Check for saved exterior requirements to restore form state
      const savedReq =
        (response as any)?.saved_requirements ||
        (doc as any)?.exterior_requirements ||
        (doc as any)?.processing?.elia_engine?.requirements;

      let restoredFormState = this.state.formState;
      let restoredDirty = this.state.requirementsDirty;
      if (!this.state.requirementsDirty && savedReq && typeof savedReq === 'object') {
        const deserialized = deserializeRequirements(savedReq);
        restoredFormState = { ...this.state.formState, ...deserialized };
        restoredDirty = false;
      }

      this.setState({
        authoritativeMaster: doc,
        sourceRevision: rev,
        contextFreshness: canBeCurrent ? 'current' : 'stale',
        contextError: null,
        acceptedLandscape, // Legitimately updated or cleared to null
        acceptedProvenance, // Legitimately updated or cleared to null
        activeView: nextActiveView,
        isLoadingContext: false,
        formState: restoredFormState,
        requirementsDirty: restoredDirty,
        ...(revisionChanged ? { validationResult: null, validationError: null } : {}),
      });

      return { status: 'success', revision: rev, master: doc };
    } catch (err: any) {
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.contextReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      if (reqEpoch < this.mutationEpoch && targetMutationEpoch === undefined) {
        this.setState({ isLoadingContext: false });
        return { status: 'obsolete' };
      }

      const parsed = parseEliaError(err, 'Could not load project context.');
      this.setState({
        contextFreshness: this.state.authoritativeMaster ? 'stale' : 'unavailable',
        contextError: parsed.message,
        isLoadingContext: false,
      });

      return { status: 'failed', error: parsed.message };
    }
  }

  /**
   * Channel: Latest Run
   */
  public async loadLatestRun(
    api: EliaApiInterface,
    signal?: AbortSignal
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; error?: string }> {
    const pid = this.state.projectId;
    if (!pid || !this.state.isMounted) return { status: 'obsolete' };

    const session = this.state.sessionSeq;
    const reqId = ++this.latestRunReqId;

    this.setState({ isCheckingRun: true, latestRunError: null });

    try {
      const run = await api.getResult(pid, { signal });
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.latestRunReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      this.setState({ latestRun: run, latestRunError: null, isCheckingRun: false });
      return { status: 'success' };
    } catch (err: any) {
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.latestRunReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      const parsed = parseEliaError(err, 'Could not retrieve latest run.');
      if (parsed.is404) {
        this.setState({ latestRun: null, latestRunError: null, isCheckingRun: false });
        return { status: 'success' };
      } else {
        this.setState({ latestRun: null, latestRunError: parsed.message, isCheckingRun: false });
        return { status: 'failed', error: parsed.message };
      }
    }
  }

  /**
   * Channel: Validation
   * Applies success AND failure ONLY IF session, reqId, submitted fingerprint, and sourceRevision match!
   */
  public async validateRequirements(
    api: EliaApiInterface,
    signal?: AbortSignal
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; result?: ELIAValidationResponse; error?: string }> {
    const pid = this.state.projectId;
    if (!pid || !this.state.authoritativeMaster || !this.state.isMounted) {
      this.setState({ validationError: 'Authoritative project context is required for validation.' });
      return { status: 'failed', error: 'No authoritative context' };
    }

    const validation = validateRequirementsForm(this.state.formState);
    if (!validation.valid) {
      const firstField = Object.keys(validation.errors)[0];
      const errorMsg = `${firstField}: ${validation.errors[firstField]}`;
      this.setState({ validationError: errorMsg });
      return { status: 'failed', error: errorMsg };
    }

    const session = this.state.sessionSeq;
    const reqId = ++this.validationReqId;
    const submittedFingerprint = computeRequirementsFingerprint(this.state.formState);
    const submittedRevision = this.state.sourceRevision;

    this.setState({ isValidating: true, validationResult: null, validationError: null });

    try {
      const requirements = serializeRequirements(this.state.formState);
      const response = await api.validateInput(pid, {
        requirements,
        master_json: this.state.authoritativeMaster,
        source_revision: submittedRevision,
        generation_mode: this.state.formState.generationMode,
      }, { signal });

      // Ownership and freshness check
      if (
        !this.state.isMounted ||
        this.state.sessionSeq !== session ||
        this.validationReqId !== reqId ||
        this.state.projectId !== pid ||
        computeRequirementsFingerprint(this.state.formState) !== submittedFingerprint ||
        this.state.sourceRevision !== submittedRevision
      ) {
        if (this.validationReqId === reqId) this.setState({ isValidating: false });
        return { status: 'obsolete' };
      }

      this.setState({
        validationResult: response,
        feasibilityResult: response.feasibility ?? null,
        isValidating: false,
      });
      return { status: 'success', result: response };
    } catch (err: any) {
      // Discard obsolete validation error if inputs or revision changed
      if (
        !this.state.isMounted ||
        this.state.sessionSeq !== session ||
        this.validationReqId !== reqId ||
        this.state.projectId !== pid ||
        computeRequirementsFingerprint(this.state.formState) !== submittedFingerprint ||
        this.state.sourceRevision !== submittedRevision
      ) {
        if (this.validationReqId === reqId) this.setState({ isValidating: false });
        return { status: 'obsolete' };
      }

      const parsed = parseEliaError(err, 'Validation failed.');
      this.setState({ validationError: parsed.message, isValidating: false });
      return { status: 'failed', error: parsed.message };
    }
  }

  /**
   * Channel: Preview Candidate (Unsaved, Non-Destructive)
   * Captures atomic provenance, matching source snapshot, and submitted generation mode.
   */
  public async previewCandidate(
    api: EliaApiInterface,
    signal?: AbortSignal
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; error?: string }> {
    const token = this.acquireMutationGuard();
    if (token === null) {
      return { status: 'obsolete' };
    }

    const pid = this.state.projectId;
    if (!pid || !this.state.authoritativeMaster || !this.state.isMounted) {
      this.releaseMutationGuard(token);
      this.setState({ actionError: 'Authoritative Master JSON is required for preview.' });
      return { status: 'failed', error: 'No Master JSON' };
    }

    const validation = validateRequirementsForm(this.state.formState);
    if (!validation.valid) {
      this.releaseMutationGuard(token);
      const firstField = Object.keys(validation.errors)[0];
      const errorMsg = `Invalid input in ${firstField}: ${validation.errors[firstField]}`;
      this.setState({ actionError: errorMsg });
      return { status: 'failed', error: errorMsg };
    }

    const session = this.state.sessionSeq;
    const reqId = ++this.mutationReqId;
    const submittedFingerprint = computeRequirementsFingerprint(this.state.formState);
    const snapshotAtSubmit = deepcopy(this.state.authoritativeMaster);
    const submittedRevision = this.state.sourceRevision;
    const submittedGenerationMode = this.state.formState.generationMode;

    this.setState({ isPreviewing: true, actionError: null });

    try {
      const requirements = serializeRequirements(this.state.formState);
      const response = await api.preview({
        master_json: snapshotAtSubmit,
        requirements,
        generation_mode: submittedGenerationMode,
        source_revision: submittedRevision,
      }, { signal });

      if (!this.state.isMounted || this.state.sessionSeq !== session || this.mutationReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      const candValidation = validateExteriorLandscape(response.exterior_landscape);
      if (!candValidation.valid) {
        const errorMsg = `Preview generated malformed exterior output: ${candValidation.error}`;
        this.setState({
          actionError: errorMsg,
          isPreviewing: false,
        });
        return { status: 'failed', error: errorMsg };
      }

      const candidateRecord: EliaCandidateRecord = {
        projectId: pid,
        runId: response.run_id,
        sourceRevision: submittedRevision,
        sourceSnapshot: snapshotAtSubmit,
        submittedFingerprint,
        generationMode: submittedGenerationMode,
        outcome: response.outcome,
        kind: 'preview',
        landscape: candValidation.value,
        timestamp: new Date().toISOString(),
      };

      const currentFingerprint = computeRequirementsFingerprint(this.state.formState);
      const stillClean = currentFingerprint === submittedFingerprint;

      let actionNotice: string | null = null;
      if (response.outcome === 'infeasible') {
        const reason = formatViolations(candValidation.value.validation_summary?.violations, 'Site boundary constraints could not be satisfied.');
        actionNotice = `Infeasible Candidate: ${reason}`;
      }

      this.setState({
        candidate: candidateRecord,
        activeView: 'candidate',
        requirementsDirty: stillClean ? false : this.state.requirementsDirty,
        actionError: actionNotice,
        isPreviewing: false,
      });

      return { status: 'success' };
    } catch (err: any) {
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.mutationReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      const parsed = parseEliaError(err, 'Preview generation failed.');
      this.handleApiError(parsed, api);
      this.setState({ isPreviewing: false });
      return { status: 'failed', error: parsed.message };
    } finally {
      this.releaseMutationGuard(token);
    }
  }

  /**
   * Channel: Generate & Save (Mutating, Persisted)
   * Captures atomic provenance, distinguishes save success from refresh failure,
   * checks ownership across all continuation awaits, and blocks blind resubmission on ambiguous failure.
   */
  public async generateAndSave(
    api: EliaApiInterface,
    sharedStoreCallbacks?: {
      setOutput?: (id: any, out: any) => void;
      setComponentStatus?: (id: any, st: any) => void;
    },
    signal?: AbortSignal
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; refreshStatus?: 'success' | 'failed'; error?: string }> {
    const token = this.acquireMutationGuard();
    if (token === null) {
      return { status: 'obsolete' };
    }

    const pid = this.state.projectId;
    if (!pid || !this.state.isMounted) {
      this.releaseMutationGuard(token);
      return { status: 'failed', error: 'No active project' };
    }

    if (this.state.requiresReconciliation || this.state.unresolvedMutation !== null) {
      this.releaseMutationGuard(token);
      this.setState({
        actionError: 'Project state must be reconciled before submitting another mutation.',
      });
      return { status: 'failed', error: 'Reconciliation required' };
    }

    if (
      this.state.isLoadingContext ||
      this.state.contextFreshness !== 'current' ||
      this.state.sourceRevision === null
    ) {
      this.releaseMutationGuard(token);
      const errorMsg = 'Authoritative project context and revision must be confirmed before saving. Refresh context.';
      this.setState({ actionError: errorMsg });
      return { status: 'failed', error: errorMsg };
    }

    const validation = validateRequirementsForm(this.state.formState);
    if (!validation.valid) {
      this.releaseMutationGuard(token);
      const firstField = Object.keys(validation.errors)[0];
      const errorMsg = `Invalid input in ${firstField}: ${validation.errors[firstField]}`;
      this.setState({ actionError: errorMsg });
      return { status: 'failed', error: errorMsg };
    }

    const session = this.state.sessionSeq;
    const reqId = ++this.mutationReqId;
    const epoch = ++this.mutationEpoch;
    this.activeMutationEpoch = epoch;

    const submittedFingerprint = computeRequirementsFingerprint(this.state.formState);
    const snapshotAtSubmit = deepcopy(this.state.authoritativeMaster);
    const submittedRevision = this.state.sourceRevision;
    const submittedGenerationMode = this.state.formState.generationMode;

    // Transition context to non-current during save
    this.setState({ isGenerating: true, contextFreshness: 'stale', actionError: null });

    try {
      const requirements = serializeRequirements(this.state.formState);
      const response = await api.run(pid, {
        requirements,
        generation_mode: submittedGenerationMode,
        apply_to_project: true,
        source_revision: submittedRevision,
      }, { signal });

      // Step 1: Ownership check after api.run
      if (
        !this.state.isMounted ||
        this.state.sessionSeq !== session ||
        this.mutationReqId !== reqId ||
        this.state.projectId !== pid ||
        this.activeMutationEpoch !== epoch
      ) {
        return { status: 'obsolete' };
      }

      const candValidation = validateExteriorLandscape(response.exterior_landscape);
      if (!candValidation.valid) {
        // A potentially persisted save returned malformed exterior output.
        // Block immediate resubmission by recording an unresolved mutation.
        const unresolvedRecord: EliaUnresolvedMutation = {
          projectId: pid,
          sourceRevision: submittedRevision ?? 0,
          submittedFingerprint,
          submittedGenerationMode,
          snapshotAtSubmit,
          submittedAt: new Date().toISOString(),
          status: 'unresolved',
          correlatedRunId: response.run_id,
          reconciliationError: `Save response contained malformed exterior data: ${candValidation.error}. Reconciliation required before further mutations.`,
        };

        this.setState({
          requiresReconciliation: true,
          unresolvedMutation: unresolvedRecord,
          contextFreshness: 'stale',
          actionError: `Save response contained malformed exterior data: ${candValidation.error}. Reconciliation required before further mutations.`,
          isGenerating: false,
        });
        return { status: 'failed', error: candValidation.error };
      }

      const validLandscape = candValidation.value;
      const candidateRecord: EliaCandidateRecord = {
        projectId: pid,
        runId: response.run_id,
        sourceRevision: submittedRevision,
        sourceSnapshot: snapshotAtSubmit,
        submittedFingerprint,
        generationMode: submittedGenerationMode,
        outcome: response.outcome,
        kind: 'persisted_run',
        landscape: validLandscape,
        timestamp: new Date().toISOString(),
      };

      const currentFingerprint = computeRequirementsFingerprint(this.state.formState);
      const stillClean = currentFingerprint === submittedFingerprint;

      if (response.outcome === 'valid') {
        if (this.state.isMounted && this.state.sessionSeq === session && this.state.projectId === pid) {
          sharedStoreCallbacks?.setOutput?.('elia_engine', validLandscape);
          sharedStoreCallbacks?.setComponentStatus?.('elia_engine', 'completed');
        }

        this.setState({
          candidate: candidateRecord,
          acceptedLandscape: validLandscape,
          acceptedProvenance: {
            projectId: pid,
            sourceRevision: submittedRevision,
            sourceSnapshot: snapshotAtSubmit,
            runId: response.run_id,
          },
          activeView: 'accepted',
          requirementsDirty: stillClean ? false : this.state.requirementsDirty,
          isGenerating: false,
        });

        // Step 2: Await owned loadAuthoritativeContext
        const refreshResult = await this.loadAuthoritativeContext(api, signal, epoch);

        // Recheck ownership after context refresh
        if (
          !this.state.isMounted ||
          this.state.sessionSeq !== session ||
          this.mutationReqId !== reqId ||
          this.state.projectId !== pid ||
          this.activeMutationEpoch !== epoch
        ) {
          return { status: 'obsolete' };
        }
        if (refreshResult.status === 'obsolete') {
          return { status: 'obsolete' };
        }

        // Step 3: Await loadLatestRun ONLY if still owned
        await this.loadLatestRun(api, signal);
        if (
          !this.state.isMounted ||
          this.state.sessionSeq !== session ||
          this.mutationReqId !== reqId ||
          this.state.projectId !== pid
        ) {
          return { status: 'obsolete' };
        }

        if (refreshResult.status === 'failed') {
          this.setState({
            actionError: 'Saved successfully to project database; unable to refresh project state. Click refresh context.',
          });
          return { status: 'success', refreshStatus: 'failed' };
        }

        return { status: 'success', refreshStatus: 'success' };
      } else {
        // Infeasible run: preserves earlier accepted exterior
        const violations = formatViolations(validLandscape.validation_summary?.violations, 'Site boundary constraints could not be satisfied.');
        this.setState({
          candidate: candidateRecord,
          activeView: 'candidate',
          requirementsDirty: stillClean ? false : this.state.requirementsDirty,
          actionError: `Infeasible Run: ${violations} (Previously accepted design preserved).`,
          isGenerating: false,
        });

        // Step 2: Refresh context on infeasible run too because processing incremented revision
        const refreshResult = await this.loadAuthoritativeContext(api, signal, epoch);
        if (
          !this.state.isMounted ||
          this.state.sessionSeq !== session ||
          this.mutationReqId !== reqId ||
          this.state.projectId !== pid ||
          this.activeMutationEpoch !== epoch
        ) {
          return { status: 'obsolete' };
        }
        if (refreshResult.status === 'obsolete') {
          return { status: 'obsolete' };
        }

        await this.loadLatestRun(api, signal);
        if (
          !this.state.isMounted ||
          this.state.sessionSeq !== session ||
          this.mutationReqId !== reqId ||
          this.state.projectId !== pid
        ) {
          return { status: 'obsolete' };
        }

        if (refreshResult.status === 'failed') {
          this.setState({
            actionError: 'Infeasible run recorded; unable to refresh project revision. Click refresh context.',
          });
          return { status: 'success', refreshStatus: 'failed' };
        }

        return { status: 'success', refreshStatus: 'success' };
      }
    } catch (err: any) {
      if (
        !this.state.isMounted ||
        this.state.sessionSeq !== session ||
        this.mutationReqId !== reqId ||
        this.state.projectId !== pid ||
        this.activeMutationEpoch !== epoch
      ) {
        return { status: 'obsolete' };
      }

      const parsed = parseEliaError(err, 'Exterior layout generation failed.');
      this.handleApiError(parsed, api);

      if (!parsed.isStaleRevision && this.state.isMounted && this.state.sessionSeq === session && this.state.projectId === pid) {
        sharedStoreCallbacks?.setComponentStatus?.('elia_engine', 'failed');
      }

      // Distinguish confirmed pre-execution rejection from ambiguous transport failure
      const isConfirmedRejection =
        parsed.isStaleRevision ||
        parsed.type === 'VALIDATION_ERROR' ||
        parsed.type === 'AUTH_REQUIRED' ||
        parsed.type === 'MODEL_UNAVAILABLE';

      if (!isConfirmedRejection) {
        const unresolvedRecord: EliaUnresolvedMutation = {
          projectId: pid,
          sourceRevision: submittedRevision,
          submittedFingerprint,
          submittedGenerationMode,
          snapshotAtSubmit,
          submittedAt: new Date().toISOString(),
          status: 'unresolved',
          reconciliationError: null,
        };

        this.setState({
          requiresReconciliation: true,
          unresolvedMutation: unresolvedRecord,
          contextFreshness: 'stale',
          actionError: `${parsed.message} Network outcome uncertain; reconciliation required before further mutations.`,
        });
      }

      this.setState({ isGenerating: false });
      return { status: 'failed', error: parsed.message };
    } finally {
      if (this.activeMutationEpoch === epoch) {
        this.activeMutationEpoch = null;
      }
      this.releaseMutationGuard(token);
    }
  }

  /**
   * Channel: Mutation Reconciliation
   * Explicitly resolves an uncertain/ambiguous mutation using verifiable correlation evidence:
   *  - doc.processing.elia_engine.source_revision matching unresolved mutation's sourceRevision
   *  - Correlated terminal run status ('completed', 'infeasible', 'failed')
   *  - Followed by an owned authoritative context refresh
   * Unrelated older runs or in-progress runs KEEP the unresolved guard active.
   */
  public async reconcileMutation(
    api: EliaApiInterface,
    signal?: AbortSignal
  ): Promise<{
    status: 'reconciled' | 'processing' | 'unresolved' | 'failed' | 'obsolete';
    message?: string;
  }> {
    const pid = this.state.projectId;
    if (!pid || !this.state.isMounted || !this.state.isActive) return { status: 'obsolete' };

    // Synchronous guard against overlapping reconciliation calls
    if (this.isReconcilingSync || this.state.isReconciling) {
      return { status: 'obsolete' };
    }
    this.isReconcilingSync = true;
    const session = this.state.sessionSeq;
    const reconToken = ++this.reconciliationReqId;
    this.activeReconciliationToken = reconToken;

    const isOwned = () => {
      return (
        this.state.isMounted &&
        this.state.isActive &&
        this.state.sessionSeq === session &&
        this.state.projectId === pid &&
        this.reconciliationReqId === reconToken &&
        this.activeReconciliationToken === reconToken
      );
    };

    const unresolved = this.state.unresolvedMutation;

    if (!this.state.requiresReconciliation && !unresolved) {
      this.isReconcilingSync = false;
      this.activeReconciliationToken = 0;
      return { status: 'reconciled', message: 'No reconciliation required.' };
    }

    const targetSourceRevision = unresolved?.sourceRevision ?? this.state.sourceRevision ?? 0;
    const knownCorrelatedRunId = unresolved?.correlatedRunId ?? null;
    const submittedSnapshot = unresolved?.snapshotAtSubmit ? deepcopy(unresolved.snapshotAtSubmit) : null;
    const submittedRevision = unresolved?.sourceRevision ?? null;
    const submittedFingerprint = unresolved?.submittedFingerprint || '';
    const submittedGenerationMode = unresolved?.submittedGenerationMode || this.state.formState.generationMode;

    this.setState({ isReconciling: true, actionError: null });

    try {
      // 1. Fetch latest run and authoritative context
      const [runResult, contextResult] = await Promise.allSettled([
        api.getResult(pid, { signal }),
        api.getContext(pid, { signal }),
      ]);

      if (!isOwned()) {
        return { status: 'obsolete' };
      }

      // Check for transport failures during reconciliation
      if (contextResult.status === 'rejected') {
        const parsed = parseEliaError(contextResult.reason, 'Reconciliation query failed.');
        this.setState({
          isReconciling: false,
          actionError: `Reconciliation check failed: ${parsed.message} Unresolved mutation remains protected.`,
        });
        return { status: 'unresolved', message: parsed.message };
      }

      const ctxResponse = contextResult.value;
      if (!ctxResponse || typeof ctxResponse !== 'object' || !('master_json' in ctxResponse)) {
        const msg = 'Malformed context response during reconciliation.';
        this.setState({ isReconciling: false, actionError: msg });
        return { status: 'unresolved', message: msg };
      }

      const doc = ctxResponse.master_json;
      if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
        const msg = 'Malformed Master JSON during reconciliation.';
        this.setState({ isReconciling: false, actionError: msg });
        return { status: 'unresolved', message: msg };
      }

      const currentRev = ctxResponse.revision !== undefined && ctxResponse.revision !== null
        ? ctxResponse.revision
        : (typeof doc.revision === 'number' ? doc.revision : null);

      const eliaProc = (doc.processing as any)?.elia_engine;
      const latestRun = runResult.status === 'fulfilled' ? runResult.value : null;

      // Extract backend evidence
      const procSourceRevision = eliaProc && typeof eliaProc.source_revision === 'number' ? eliaProc.source_revision : null;
      const procStatus = eliaProc && typeof eliaProc.status === 'string' ? eliaProc.status : null;
      const procRunId = eliaProc && typeof eliaProc.run_id === 'string' ? eliaProc.run_id : null;

      // --- CORRELATION EVALUATION (Fix 2) ---
      // We must correlate evidence to the unresolved mutation (targetSourceRevision).
      // Problem: Matching procRunId === latestRun.run_id alone does NOT correlate to the unresolved mutation.

      // 1. Check for contradictory revision evidence
      if (procSourceRevision !== null && knownCorrelatedRunId !== null && procRunId === knownCorrelatedRunId && procSourceRevision !== targetSourceRevision) {
        const msg = 'Contradictory evidence: captured run ID matches processing metadata but source revision differs.';
        this.setState({ isReconciling: false, actionError: msg });
        return { status: 'unresolved', message: msg };
      }

      // 2. Unrelated newer request
      // If procSourceRevision > targetSourceRevision, the backend has already processed or is processing a newer request.
      // This newer run cannot be accepted as completion of our uncertain request.
      if (procSourceRevision !== null && procSourceRevision > targetSourceRevision) {
        const msg = `Reconciliation unresolved: Backend metadata (rev ${procSourceRevision}) belongs to a newer request than the uncertain mutation (rev ${targetSourceRevision}). Saving/export remains blocked.`;
        if (unresolved) {
          this.setState({
            unresolvedMutation: { ...unresolved, status: 'unresolved', reconciliationError: msg },
            requiresReconciliation: true,
            isReconciling: false,
            actionError: msg,
          });
        } else {
          this.setState({ requiresReconciliation: true, isReconciling: false, actionError: msg });
        }
        return { status: 'unresolved', message: msg };
      }

      // 3. Unrelated older request
      // If procSourceRevision < targetSourceRevision, or currentRev <= targetSourceRevision with no matching run:
      if (
        (procSourceRevision !== null && procSourceRevision < targetSourceRevision) ||
        (currentRev !== null && currentRev <= targetSourceRevision && procSourceRevision === null && knownCorrelatedRunId === null)
      ) {
        const msg = 'Reconciliation pending: latest backend run belongs to an earlier project revision. The uncertain mutation has not yet registered.';
        if (unresolved) {
          this.setState({
            unresolvedMutation: { ...unresolved, status: 'unresolved', reconciliationError: msg },
            requiresReconciliation: true,
            isReconciling: false,
            actionError: msg,
          });
        } else {
          this.setState({ requiresReconciliation: true, isReconciling: false, actionError: msg });
        }
        return { status: 'unresolved', message: msg };
      }

      // 4. Determine correlation to uncertain mutation
      let correlatedRunId: string | null = null;
      if (procSourceRevision === targetSourceRevision && procRunId) {
        correlatedRunId = procRunId;
      } else if (knownCorrelatedRunId !== null) {
        if (latestRun?.run_id === knownCorrelatedRunId || procRunId === knownCorrelatedRunId) {
          correlatedRunId = knownCorrelatedRunId;
        }
      }

      // If no correlation can be proven (e.g. procSourceRevision is null and knownCorrelatedRunId is null,
      // even if procRunId === latestRun.run_id):
      if (!correlatedRunId) {
        const msg = 'API limitation: Backend did not return verifiable correlation evidence matching the uncertain request revision. Unresolved guard remains active.';
        this.setState({ isReconciling: false, requiresReconciliation: true, actionError: msg });
        return { status: 'unresolved', message: msg };
      }

      // 5. Read terminal status ONLY from evidence belonging to the correlated run
      let statusFromProc: string | null = null;
      let outcomeFromProc: string | null = null;
      let statusFromLatestRun: string | null = null;
      let outputFromLatestRun: any = null;

      if (procRunId === correlatedRunId) {
        statusFromProc = procStatus;
        outcomeFromProc = eliaProc && typeof eliaProc.outcome === 'string' ? eliaProc.outcome : null;
      }
      if (latestRun?.run_id === correlatedRunId) {
        statusFromLatestRun = latestRun.status;
        outputFromLatestRun = latestRun.output;
      }

      const classification = classifyCorrelatedRunStatus(
        statusFromProc,
        outcomeFromProc,
        statusFromLatestRun,
        outputFromLatestRun
      );

      if (classification.isContradictory) {
        const msg = classification.contradictionReason || `Contradictory status evidence for run ${correlatedRunId}. Guard remains active.`;
        this.setState({ isReconciling: false, requiresReconciliation: true, actionError: msg });
        return { status: 'unresolved', message: msg };
      }

      // 6. Handle processing state
      if (classification.isProcessing) {
        const updatedUnresolved: EliaUnresolvedMutation = {
          ...(unresolved || {
            projectId: pid,
            sourceRevision: targetSourceRevision,
            submittedFingerprint: this.state.lastSubmittedFingerprint || '',
            submittedGenerationMode: this.state.formState.generationMode,
            snapshotAtSubmit: null,
            submittedAt: new Date().toISOString(),
          }),
          status: 'processing',
          correlatedRunId,
          reconciliationError: null,
        };
        this.setState({
          unresolvedMutation: updatedUnresolved,
          requiresReconciliation: true,
          isReconciling: false,
          actionError: 'Mutation is currently processing on the backend. Please check status again shortly.',
        });
        return { status: 'processing', message: 'Mutation is currently processing.' };
      }

      const terminalOutcome = classification.terminalOutcome;
      if (!terminalOutcome) {
        const msg = `Unable to determine terminal outcome for correlated run ${correlatedRunId}. Guard remains active.`;
        this.setState({ isReconciling: false, requiresReconciliation: true, actionError: msg });
        return { status: 'unresolved', message: msg };
      }

      // Store latestRun if it belongs to correlated run
      if (latestRun && latestRun.run_id === correlatedRunId) {
        this.setState({ latestRun, latestRunError: null });
      }

      // 8. Owned Authoritative Context Refresh (Fix 3)
      const ownedEpoch = ++this.mutationEpoch;
      this.activeMutationEpoch = ownedEpoch;

      let refreshResult: { status: 'success' | 'failed' | 'obsolete'; revision?: number | null; master?: any; error?: string };
      try {
        refreshResult = await this.loadAuthoritativeContext(api, signal, ownedEpoch);
      } finally {
        if (this.activeMutationEpoch === ownedEpoch && isOwned()) {
          this.activeMutationEpoch = null;
        }
      }

      if (!isOwned()) {
        return { status: 'obsolete' };
      }

      if (refreshResult.status !== 'success') {
        // Authoritative refresh failed (e.g. transport error or malformed exterior in Master JSON):
        // Retain the unresolved guard!
        this.setState({
          isReconciling: false,
          requiresReconciliation: true,
          contextFreshness: 'stale',
          actionError: 'Correlated terminal run verified, but authoritative context refresh failed. Save and export remain blocked until context refresh succeeds.',
        });
        return { status: 'failed', message: 'Context refresh failed after terminal run' };
      }

      // 9. Successfully refreshed authoritative context
      // Handle terminal failure vs infeasible vs completed:
      if (terminalOutcome === 'failed') {
        this.setState({
          unresolvedMutation: null,
          requiresReconciliation: false,
          isReconciling: false,
          contextFreshness: 'current',
          actionError: 'Backend run failed: The uncertain exterior generation failed on the server. Project context refreshed; you may regenerate.',
        });
        return { status: 'reconciled', message: 'Reconciled: backend run failed.' };
      }

      if (terminalOutcome === 'infeasible') {
        // Keep candidate state if output was returned and valid, but DO NOT promote to accepted design!
        // The authoritative refresh above already loaded the still-valid accepted design (or null).
        let candidatePublished = false;
        let candViolations: unknown = null;

        if (outputFromLatestRun && typeof outputFromLatestRun === 'object') {
          const candValidation = validateExteriorLandscape(outputFromLatestRun);
          if (candValidation.valid) {
            candidatePublished = true;
            candViolations = candValidation.value.validation_summary?.violations;
            this.setState({
              candidate: {
                projectId: pid,
                runId: correlatedRunId,
                sourceRevision: submittedRevision,
                sourceSnapshot: submittedSnapshot,
                submittedFingerprint,
                generationMode: submittedGenerationMode,
                outcome: 'infeasible',
                kind: 'persisted_run',
                landscape: candValidation.value,
                timestamp: new Date().toISOString(),
              },
              activeView: this.state.acceptedLandscape ? this.state.activeView : 'candidate',
            });
          }
        }

        let actionNotice: string;
        if (outputFromLatestRun && !candidatePublished) {
          actionNotice =
            'Infeasible Run: Terminal infeasible outcome confirmed; candidate display data was malformed and cannot be displayed (Previously accepted design preserved).';
        } else {
          const violationsText = formatViolations(candViolations, 'Site boundary constraints could not be satisfied.');
          actionNotice = `Infeasible Run: ${violationsText} (Previously accepted design preserved).`;
        }

        this.setState({
          unresolvedMutation: null,
          requiresReconciliation: false,
          isReconciling: false,
          contextFreshness: 'current',
          actionError: actionNotice,
        });
        return { status: 'reconciled', message: 'Reconciled: terminal infeasible run.' };
      }

      // Terminal status is 'completed' (valid)
      if (outputFromLatestRun && typeof outputFromLatestRun === 'object') {
        const candValidation = validateExteriorLandscape(outputFromLatestRun);
        if (candValidation.valid) {
          this.setState({
            candidate: {
              projectId: pid,
              runId: correlatedRunId,
              sourceRevision: submittedRevision,
              sourceSnapshot: submittedSnapshot,
              submittedFingerprint,
              generationMode: submittedGenerationMode,
              outcome: 'valid',
              kind: 'persisted_run',
              landscape: candValidation.value,
              timestamp: new Date().toISOString(),
            },
          });
        }
      }

      this.setState({
        unresolvedMutation: null,
        requiresReconciliation: false,
        isReconciling: false,
        contextFreshness: 'current',
        actionError: null,
      });

      return { status: 'reconciled', message: 'Reconciliation completed successfully.' };
    } catch (err: any) {
      if (!isOwned()) {
        return { status: 'obsolete' };
      }

      const parsed = parseEliaError(err, 'Reconciliation failed.');
      this.setState({
        isReconciling: false,
        requiresReconciliation: true,
        actionError: `Reconciliation error: ${parsed.message}. Guard remains enabled.`,
      });
      return { status: 'unresolved', message: parsed.message };
    } finally {
      if (this.activeReconciliationToken === reconToken) {
        this.isReconcilingSync = false;
        this.activeReconciliationToken = 0;
      }
      if (isOwned()) {
        this.setState({ isReconciling: false });
      }
    }
  }

  public canGenerateAndSave(): boolean {
    return (
      this.state.isMounted &&
      this.state.isActive &&
      !this.state.isGenerating &&
      !this.state.isPreviewing &&
      !this.state.isValidating &&
      !this.state.requiresReconciliation &&
      this.state.unresolvedMutation === null &&
      this.activeMutationEpoch === null &&
      !this.state.isLoadingContext &&
      this.state.sourceRevision !== null &&
      this.state.contextFreshness === 'current'
    );
  }

  public canExportMasterJson(): boolean {
    return (
      this.state.authoritativeMaster !== null &&
      this.state.contextFreshness === 'current' &&
      !this.state.requiresReconciliation &&
      this.state.unresolvedMutation === null &&
      this.activeMutationEpoch === null &&
      !this.state.isGenerating
    );
  }

  public async searchLocations(
    api: EliaApiInterface,
    query: string,
    signal?: AbortSignal
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; results?: SriLankaLocation[] }> {
    if (!query.trim()) {
      this.setState({ locations: [], isSearchingLocation: false, locationError: null });
      return { status: 'success', results: [] };
    }

    const session = this.state.sessionSeq;
    const reqId = ++this.locationSearchReqId;

    this.setState({ isSearchingLocation: true, locationError: null });

    try {
      const res = await (api.searchLocations ? api.searchLocations(query, { signal }) : Promise.resolve({ results: [] }));
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.locationSearchReqId !== reqId) {
        return { status: 'obsolete' };
      }

      this.setState({ locations: res.results || [], isSearchingLocation: false });
      return { status: 'success', results: res.results };
    } catch (err: any) {
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.locationSearchReqId !== reqId) {
        return { status: 'obsolete' };
      }

      this.setState({
        locationError: 'Failed to search locations.',
        isSearchingLocation: false,
      });
      return { status: 'failed' };
    }
  }

  public async loadSolar(
    api: EliaApiInterface,
    location: SriLankaLocation | EliaSelectedLocation,
    signal?: AbortSignal
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; solar?: LiveSolarConditions }> {
    const pid = this.state.projectId;
    if (!pid || !location || !this.state.isMounted) return { status: 'obsolete' };

    const session = this.state.sessionSeq;
    const reqId = ++this.solarReqId;
    const requestedLoc = {
      id: location.id,
      name: location.name,
      latitude: location.latitude,
      longitude: location.longitude,
    };

    this.setState({ isLoadingSolar: true, locationError: null });

    try {
      const data = await (api.currentSolar ? api.currentSolar(pid, location, { signal }) : Promise.reject(new Error('No solar api')));
      
      // Ownership check
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.solarReqId !== reqId || this.state.projectId !== pid) {
        if (this.solarReqId === reqId) this.setState({ isLoadingSolar: false });
        return { status: 'obsolete' };
      }

      // Check location match
      const currentLoc = this.state.formState.selectedLocation;
      if (!currentLoc) {
        if (this.solarReqId === reqId) this.setState({ isLoadingSolar: false });
        return { status: 'obsolete' };
      }

      const idMatches = requestedLoc.id !== undefined && currentLoc.id !== undefined
        ? requestedLoc.id === currentLoc.id
        : true;
      const coordsMatch = Math.abs(requestedLoc.latitude - currentLoc.latitude) < 0.001 &&
                          Math.abs(requestedLoc.longitude - currentLoc.longitude) < 0.001;

      if (!idMatches || !coordsMatch) {
        if (this.solarReqId === reqId) this.setState({ isLoadingSolar: false });
        return { status: 'obsolete' };
      }

      this.setState({ solar: data, isLoadingSolar: false });
      return { status: 'success', solar: data };
    } catch (err: any) {
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.solarReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      this.setState({
        locationError: 'Could not fetch live solar data for selected location.',
        isLoadingSolar: false,
      });
      return { status: 'failed' };
    }
  }

  public setActiveView(view: 'accepted' | 'candidate') {
    this.setState({ activeView: view });
  }

  public selectFeature(featureId: string | null) {
    this.setState({ selectedFeatureId: featureId });
  }

  private syncLockedFeaturesFromLandscape(landscape: ExteriorLandscape): LockedFeatureRequirement[] {
    const locked: LockedFeatureRequirement[] = [];
    for (const node of landscape.vegetation_nodes || []) {
      if (node.locked && node.position) {
        const pos = Array.isArray(node.position) ? node.position : [(node.position as any).x, (node.position as any).y];
        locked.push({
          json_id: node.json_id,
          category: typeof node.category === 'string' ? node.category : undefined,
          plant_id: typeof (node as any).plant_id === 'string' ? (node as any).plant_id : undefined,
          position: [pos[0], pos[1]],
          canopy_radius_m: typeof node.canopy_radius_m === 'number' ? node.canopy_radius_m : undefined,
          height_m: typeof node.height_m === 'number' ? node.height_m : undefined,
          locked: true,
        });
      }
    }
    for (const node of landscape.outdoor_lighting?.nodes || []) {
      if (node.locked && node.position) {
        const pos = Array.isArray(node.position) ? node.position : [(node.position as any).x, (node.position as any).y];
        locked.push({
          json_id: node.json_id,
          category: 'lighting',
          position: [pos[0], pos[1]],
          locked: true,
        });
      }
    }
    for (const elem of landscape.outdoor_elements || []) {
      if (elem.locked && elem.position) {
        const pos = Array.isArray(elem.position) ? elem.position : [(elem.position as any).x, (elem.position as any).y];
        locked.push({
          json_id: elem.json_id,
          category: elem.type || 'outdoor_element',
          position: [pos[0], pos[1]],
          locked: true,
        });
      }
    }
    return locked;
  }

  public editFeaturePosition(featureId: string, position: [number, number]) {
    const candidate = this.state.candidate;
    if (!candidate || !candidate.landscape) return;
    const history = [...(this.state.candidateEditHistory || []), deepcopy(candidate.landscape)];
    const landscape = deepcopy(candidate.landscape);
    let found = false;

    if (landscape.vegetation_nodes) {
      for (const node of landscape.vegetation_nodes) {
        if (node.json_id === featureId) {
          node.position = [position[0], position[1]];
          found = true;
          break;
        }
      }
    }

    if (!found && landscape.outdoor_lighting?.nodes) {
      for (const node of landscape.outdoor_lighting.nodes) {
        if (node.json_id === featureId) {
          node.position = [position[0], position[1]];
          found = true;
          break;
        }
      }
    }

    if (!found && landscape.outdoor_elements) {
      for (const elem of landscape.outdoor_elements) {
        if (elem.json_id === featureId) {
          const oldPos = Array.isArray(elem.position) ? elem.position : [0, 0];
          const dx = position[0] - oldPos[0];
          const dy = position[1] - oldPos[1];
          elem.position = [position[0], position[1]];
          if (elem.polygon && Array.isArray(elem.polygon)) {
            elem.polygon = elem.polygon.map(([px, py]: [number, number]) => [px + dx, py + dy]);
          }
          found = true;
          break;
        }
      }
    }

    if (found) {
      this.candidateEditVersion++;
      const currentLocked = this.syncLockedFeaturesFromLandscape(landscape);
      this.setState({
        candidate: {
          ...candidate,
          landscape,
        },
        candidateEditHistory: history,
        candidateValidationError: null,
        candidateValidationViolations: [],
        formState: {
          ...this.state.formState,
          lockedFeatures: currentLocked,
        },
      });
    }
  }

  public editFeatureRotation(featureId: string, angleDeg: number) {
    const candidate = this.state.candidate;
    if (!candidate || !candidate.landscape) return;
    const history = [...(this.state.candidateEditHistory || []), deepcopy(candidate.landscape)];
    const landscape = deepcopy(candidate.landscape);
    let found = false;

    if (landscape.outdoor_elements) {
      for (const elem of landscape.outdoor_elements) {
        if (elem.json_id === featureId) {
          const oldAngle = Number(elem.orientation_deg ?? elem.rotation_deg ?? elem.azimuth_degrees ?? 0);
          const deltaDeg = angleDeg - oldAngle;
          const rad = (deltaDeg * Math.PI) / 180;
          const cosA = Math.cos(rad);
          const sinA = Math.sin(rad);

          const center = Array.isArray(elem.position) ? elem.position : [0, 0];
          const cx = center[0];
          const cy = center[1];

          if (elem.polygon && Array.isArray(elem.polygon)) {
            elem.polygon = elem.polygon.map(([px, py]: [number, number]) => {
              const dx = px - cx;
              const dy = py - cy;
              return [
                Math.round((cx + dx * cosA - dy * sinA) * 100) / 100,
                Math.round((cy + dx * sinA + dy * cosA) * 100) / 100,
              ];
            });
          }

          elem.orientation_deg = Math.round(angleDeg % 360);
          elem.rotation_deg = Math.round(angleDeg % 360);
          elem.azimuth_degrees = Math.round(angleDeg % 360);
          found = true;
          break;
        }
      }
    }

    if (found) {
      this.candidateEditVersion++;
      const currentLocked = this.syncLockedFeaturesFromLandscape(landscape);
      this.setState({
        candidate: {
          ...candidate,
          landscape,
        },
        candidateEditHistory: history,
        candidateValidationError: null,
        candidateValidationViolations: [],
        formState: {
          ...this.state.formState,
          lockedFeatures: currentLocked,
        },
      });
    }
  }

  public editFeatureDimensions(
    featureId: string,
    dimensions: { width_m?: number; length_m?: number; canopy_radius_m?: number }
  ) {
    const candidate = this.state.candidate;
    if (!candidate || !candidate.landscape) return;
    const history = [...(this.state.candidateEditHistory || []), deepcopy(candidate.landscape)];
    const landscape = deepcopy(candidate.landscape);
    let found = false;

    if (dimensions.canopy_radius_m !== undefined && landscape.vegetation_nodes) {
      for (const node of landscape.vegetation_nodes) {
        if (node.json_id === featureId) {
          const clamped = Math.max(0.5, Math.min(10.0, Number(dimensions.canopy_radius_m)));
          node.canopy_radius_m = Math.round(clamped * 100) / 100;
          found = true;
          break;
        }
      }
    }

    if (!found && landscape.outdoor_elements) {
      for (const elem of landscape.outdoor_elements) {
        if (elem.json_id === featureId) {
          const fixedTypes = ['solar_panel_array', 'water_well', 'septic_tank', 'garden_tap'];
          if (elem.type && fixedTypes.includes(elem.type)) break;

          elem.dimensions = elem.dimensions || {};
          const w = dimensions.width_m !== undefined ? Math.max(0.5, Math.min(15.0, Number(dimensions.width_m))) : Number(elem.dimensions.width_m || 1.5);
          const l = dimensions.length_m !== undefined ? Math.max(0.5, Math.min(15.0, Number(dimensions.length_m))) : Number(elem.dimensions.length_m || elem.dimensions.depth_m || 1.5);

          elem.dimensions.width_m = Math.round(w * 100) / 100;
          elem.dimensions.length_m = Math.round(l * 100) / 100;
          elem.dimensions.depth_m = Math.round(l * 100) / 100;

          const center = Array.isArray(elem.position) ? elem.position : [0, 0];
          const cx = center[0];
          const cy = center[1];
          const halfW = w / 2;
          const halfL = l / 2;

          const angle = Number(elem.orientation_deg ?? elem.rotation_deg ?? elem.azimuth_degrees ?? 0);
          const rad = (angle * Math.PI) / 180;
          const cosA = Math.cos(rad);
          const sinA = Math.sin(rad);

          const localCorners: [number, number][] = [
            [-halfW, -halfL],
            [halfW, -halfL],
            [halfW, halfL],
            [-halfW, halfL],
            [-halfW, -halfL],
          ];

          elem.polygon = localCorners.map(([dx, dy]) => [
            Math.round((cx + dx * cosA - dy * sinA) * 100) / 100,
            Math.round((cy + dx * sinA + dy * cosA) * 100) / 100,
          ]);

          found = true;
          break;
        }
      }
    }

    if (found) {
      this.candidateEditVersion++;
      const currentLocked = this.syncLockedFeaturesFromLandscape(landscape);
      this.setState({
        candidate: {
          ...candidate,
          landscape,
        },
        candidateEditHistory: history,
        candidateValidationError: null,
        candidateValidationViolations: [],
        formState: {
          ...this.state.formState,
          lockedFeatures: currentLocked,
        },
      });
    }
  }

  public replaceVegetationPlant(featureId: string, newPlantEntry: any) {
    const candidate = this.state.candidate;
    if (!candidate || !candidate.landscape?.vegetation_nodes) return;
    const history = [...(this.state.candidateEditHistory || []), deepcopy(candidate.landscape)];
    const landscape = deepcopy(candidate.landscape);

    for (const node of landscape.vegetation_nodes) {
      if (node.json_id === featureId) {
        node.plant_id = newPlantEntry.vegetation_id;
        node.display_name = newPlantEntry.display_name;
        node.scientific_name = newPlantEntry.scientific_name;
        node.category = newPlantEntry.category || node.category;
        if (newPlantEntry.mature_height_m) node.height_m = newPlantEntry.mature_height_m;
        if (newPlantEntry.canopy_radius_m) node.canopy_radius_m = newPlantEntry.canopy_radius_m;
        if (newPlantEntry.water_demand) node.water_demand = newPlantEntry.water_demand;
        if (newPlantEntry.maintenance_level) node.maintenance_level = newPlantEntry.maintenance_level;
        node.verified_species_data = Boolean(newPlantEntry.verified_species_data);
        node.source_reference = newPlantEntry.source_reference;
        node.suitability_explanation = `User substituted with catalogue species '${newPlantEntry.scientific_name || newPlantEntry.display_name}'.`;
        break;
      }
    }

    this.candidateEditVersion++;
    const currentLocked = this.syncLockedFeaturesFromLandscape(landscape);
    this.setState({
      candidate: {
        ...candidate,
        landscape,
      },
      candidateEditHistory: history,
      candidateValidationError: null,
      candidateValidationViolations: [],
      formState: {
        ...this.state.formState,
        lockedFeatures: currentLocked,
      },
    });
  }

  public async loadPlantCatalogue(
    api: EliaApiInterface = eliaApi,
    params?: {
      placement_type?: string;
      category?: string;
      sun_requirement?: string;
      maintenance_level?: string;
      climate_zone?: string;
      query?: string;
      verified_only?: boolean;
    }
  ) {
    if (!this.state.projectId || !api.getPlantCatalogue) return;
    this.setState({ isLoadingPlantCatalogue: true, plantCatalogueError: null });
    try {
      const res = await api.getPlantCatalogue(this.state.projectId, params);
      this.setState({
        plantCatalogue: res.entries,
        plantCatalogueVersion: res.catalogue_version,
        isLoadingPlantCatalogue: false,
      });
    } catch (err: any) {
      this.setState({
        isLoadingPlantCatalogue: false,
        plantCatalogueError: err?.message || 'Failed loading plant catalogue.',
      });
    }
  }

  public async evaluatePlantSuitability(
    api: EliaApiInterface = eliaApi,
    plantId: string,
    placementType = 'ground',
    surfaceId?: string
  ) {
    if (!this.state.projectId || !api.evaluatePlantSuitability) return;
    this.setState({ isEvaluatingPlant: true });
    try {
      const res = await api.evaluatePlantSuitability(this.state.projectId, {
        plant_id: plantId,
        placement_type: placementType,
        surface_id: surfaceId,
        climate_zone: this.state.formState.climateZone !== 'unknown' ? this.state.formState.climateZone : undefined,
      });
      const assessments = { ...this.state.plantSuitabilityAssessments, [plantId]: res.assessment };
      const newProposals = [...this.state.plantAlternativeProposals];
      if (res.alternatives && res.alternatives.length > 0) {
        for (const alt of res.alternatives) {
          if (!newProposals.some(p => p.proposal_id === alt.proposal_id || (p.original_request === alt.original_request && p.alternative_plant_id === alt.alternative_plant_id))) {
            newProposals.push(alt);
          }
        }
      }
      this.setState({
        plantSuitabilityAssessments: assessments,
        plantAlternativeProposals: newProposals,
        isEvaluatingPlant: false,
      });
    } catch {
      this.setState({ isEvaluatingPlant: false });
    }
  }

  public acceptPlantAlternative(proposal: PlantAlternativeProposal) {
    const accepted: AcceptedPlantAlternative = {
      original_request: proposal.original_request,
      alternative_plant_id: proposal.alternative_plant_id,
      alternative_display_name: proposal.alternative_display_name,
      placement_type: proposal.proposed_placement_type,
      surface_id: proposal.proposed_surface_id,
      quantity: proposal.quantity,
      source_revision: this.state.sourceRevision,
      catalogue_version: proposal.catalogue_version || '2.1',
      acceptance_status: 'accepted',
    };
    const currentAccepted = [...(this.state.formState.acceptedPlantAlternatives || [])];
    const filteredAccepted = currentAccepted.filter(
      a => !(a.original_request === proposal.original_request && a.alternative_plant_id === proposal.alternative_plant_id)
    );
    filteredAccepted.push(accepted);

    const preferred = [...(this.state.formState.preferredPlantIds || [])];
    if (!preferred.includes(proposal.alternative_plant_id)) {
      preferred.push(proposal.alternative_plant_id);
    }

    const updatedProposals = this.state.plantAlternativeProposals.map(p =>
      p.proposal_id === proposal.proposal_id ? { ...p, status: 'accepted' as const } : p
    );

    this.editRequirement({
      acceptedPlantAlternatives: filteredAccepted,
      preferredPlantIds: preferred,
    });
    this.setState({ plantAlternativeProposals: updatedProposals });
  }

  public rejectPlantAlternative(proposalId: string, plantId: string) {
    const currentRejected = [...(this.state.formState.rejectedPlantAlternatives || [])];
    if (!currentRejected.includes(plantId)) {
      currentRejected.push(plantId);
    }
    const updatedProposals = this.state.plantAlternativeProposals.map(p =>
      p.proposal_id === proposalId ? { ...p, status: 'rejected' as const } : p
    );
    this.editRequirement({
      rejectedPlantAlternatives: currentRejected,
    });
    this.setState({ plantAlternativeProposals: updatedProposals });
  }

  public revertPlantAlternative(alternativePlantId: string) {
    const currentAccepted = [...(this.state.formState.acceptedPlantAlternatives || [])];
    const filteredAccepted = currentAccepted.filter(a => a.alternative_plant_id !== alternativePlantId);
    const updatedProposals = this.state.plantAlternativeProposals.map(p =>
      p.alternative_plant_id === alternativePlantId ? { ...p, status: 'proposed' as const } : p
    );
    this.editRequirement({
      acceptedPlantAlternatives: filteredAccepted,
    });
    this.setState({ plantAlternativeProposals: updatedProposals });
  }

  public selectPreferredPlant(plantId: string, api: EliaApiInterface = eliaApi) {
    const preferred = [...(this.state.formState.preferredPlantIds || [])];
    if (!preferred.includes(plantId)) {
      preferred.push(plantId);
      this.editRequirement({ preferredPlantIds: preferred });
      this.evaluatePlantSuitability(api, plantId);
    }
  }

  public removePreferredPlant(plantId: string) {
    const preferred = (this.state.formState.preferredPlantIds || []).filter(id => id !== plantId);
    this.editRequirement({ preferredPlantIds: preferred });
  }

  public removeFeature(featureId: string) {
    const candidate = this.state.candidate;
    if (!candidate || !candidate.landscape) return;
    const history = [...(this.state.candidateEditHistory || []), deepcopy(candidate.landscape)];
    const landscape = deepcopy(candidate.landscape);

    landscape.vegetation_nodes = (landscape.vegetation_nodes || []).filter((n) => n.json_id !== featureId);
    if (landscape.outdoor_lighting?.nodes) {
      landscape.outdoor_lighting.nodes = landscape.outdoor_lighting.nodes.filter((n) => n.json_id !== featureId);
    }
    landscape.outdoor_elements = (landscape.outdoor_elements || []).filter((n) => n.json_id !== featureId);

    this.candidateEditVersion++;
    const currentLocked = this.syncLockedFeaturesFromLandscape(landscape);
    this.setState({
      candidate: {
        ...candidate,
        landscape,
      },
      candidateEditHistory: history,
      selectedFeatureId: this.state.selectedFeatureId === featureId ? null : this.state.selectedFeatureId,
      candidateValidationError: null,
      candidateValidationViolations: [],
      formState: {
        ...this.state.formState,
        lockedFeatures: currentLocked,
      },
    });
  }

  public toggleFeatureLock(featureId: string) {
    const candidate = this.state.candidate;
    if (!candidate || !candidate.landscape) return;
    const history = [...(this.state.candidateEditHistory || []), deepcopy(candidate.landscape)];
    const landscape = deepcopy(candidate.landscape);

    for (const node of landscape.vegetation_nodes || []) {
      if (node.json_id === featureId) {
        node.locked = !node.locked;
        break;
      }
    }
    for (const node of landscape.outdoor_lighting?.nodes || []) {
      if (node.json_id === featureId) {
        node.locked = !node.locked;
        break;
      }
    }
    for (const elem of landscape.outdoor_elements || []) {
      if (elem.json_id === featureId) {
        elem.locked = !elem.locked;
        break;
      }
    }

    this.candidateEditVersion++;
    const currentLocked = this.syncLockedFeaturesFromLandscape(landscape);

    this.setState({
      candidate: {
        ...candidate,
        landscape,
      },
      candidateEditHistory: history,
      candidateValidationError: null,
      candidateValidationViolations: [],
      formState: {
        ...this.state.formState,
        lockedFeatures: currentLocked,
      },
    });
  }

  public undoCandidateEdit() {
    const history = [...(this.state.candidateEditHistory || [])];
    if (history.length === 0 || !this.state.candidate) return;
    const previous = history.pop()!;
    this.candidateEditVersion++;
    const currentLocked = this.syncLockedFeaturesFromLandscape(previous);
    this.setState({
      candidate: {
        ...this.state.candidate,
        landscape: previous,
      },
      candidateEditHistory: history,
      candidateValidationError: null,
      candidateValidationViolations: [],
      formState: {
        ...this.state.formState,
        lockedFeatures: currentLocked,
      },
    });
  }

  public resetCandidateEdits() {
    const history = this.state.candidateEditHistory;
    if (!history || history.length === 0 || !this.state.candidate) return;
    const initial = history[0];
    this.candidateEditVersion++;
    const currentLocked = this.syncLockedFeaturesFromLandscape(initial);
    this.setState({
      candidate: {
        ...this.state.candidate,
        landscape: initial,
      },
      candidateEditHistory: [],
      candidateValidationError: null,
      candidateValidationViolations: [],
      formState: {
        ...this.state.formState,
        lockedFeatures: currentLocked,
      },
    });
  }

  public async validateEditedCandidate(api: EliaApiInterface): Promise<boolean> {
    const { projectId, candidate, formState, isMounted, isActive } = this.state;
    if (!isMounted || !isActive || !projectId || !candidate?.landscape) return false;
    if (this.isMutatingSync || this.isReconcilingSync) return false;

    const reqId = ++this.candidateValidationReqId;
    const capturedVersion = this.candidateEditVersion;
    const capturedLandscape = deepcopy(candidate.landscape);
    const capturedRequirements = serializeRequirements(formState);

    this.setState({ isValidatingCandidate: true, candidateValidationError: null, candidateValidationViolations: [] });

    try {
      const res = await (api as any).validateCandidate(projectId, {
        exterior_landscape: capturedLandscape,
        requirements: capturedRequirements,
      });

      // Ignore stale response if lifecycle changed or candidate was further modified
      if (
        !this.state.isMounted ||
        !this.state.isActive ||
        this.state.projectId !== projectId ||
        this.candidateValidationReqId !== reqId ||
        this.candidateEditVersion !== capturedVersion ||
        !this.state.candidate
      ) {
        return false;
      }

      if (res.valid) {
        const canonical = res.canonical_candidate || capturedLandscape;
        const updatedLandscape: ExteriorLandscape = {
          ...canonical,
          factors_assessment: res.factors_assessment || canonical.factors_assessment,
          validation_summary: {
            ...canonical.validation_summary,
            valid: true,
            violations: [],
            checks_passed: res.checks_passed ?? canonical.validation_summary?.checks_passed,
            checks_total: res.checks_total ?? canonical.validation_summary?.checks_total,
          },
        };
        // Explicitly strip any obsolete financial fields
        delete (updatedLandscape as any).budget_estimate;
        delete (updatedLandscape as any).budget_assessment;

        this.setState({
          isValidatingCandidate: false,
          candidate: {
            ...this.state.candidate,
            landscape: updatedLandscape,
          },
          candidateValidationError: null,
          candidateValidationViolations: [],
        });
        return true;
      } else {
        this.setState({
          isValidatingCandidate: false,
          candidateValidationError: 'Customized candidate violates geometric or safety constraints.',
          candidateValidationViolations: res.violations || [],
        });
        return false;
      }
    } catch (err: any) {
      if (
        !this.state.isMounted ||
        !this.state.isActive ||
        this.state.projectId !== projectId ||
        this.candidateValidationReqId !== reqId
      ) {
        return false;
      }
      const parsed = parseEliaError(err);
      this.setState({
        isValidatingCandidate: false,
        candidateValidationError: parsed.message,
        candidateValidationViolations: err.response?.data?.detail?.violations || [],
      });
      return false;
    }
  }

  public async saveEditedCandidate(
    api: EliaApiInterface,
    callbacks?: { setOutput?: (comp: string, data: any) => void; setComponentStatus?: (comp: string, status: any) => void }
  ): Promise<boolean> {
    const { projectId, candidate, sourceRevision, formState, isMounted, isActive, isSavingCandidate } = this.state;
    if (!isMounted || !isActive || !projectId || !candidate?.landscape || sourceRevision === null) return false;
    if (isSavingCandidate || this.isMutatingSync || this.isReconcilingSync) return false;

    // Prevent duplicate mutations with synchronous guard
    this.isMutatingSync = true;
    const reqId = ++this.candidateSaveReqId;
    const capturedVersion = this.candidateEditVersion;
    const capturedLandscape = deepcopy(candidate.landscape);
    const capturedRevision = sourceRevision;
    const capturedRequirements = serializeRequirements(formState);

    this.setState({ isSavingCandidate: true, saveCandidateError: null });

    try {
      // 1. Validate the candidate before saving
      const validateRes = await (api as any).validateCandidate(projectId, {
        exterior_landscape: capturedLandscape,
        requirements: capturedRequirements,
      });

      // Check if project or candidate version changed during validation
      if (
        !this.state.isMounted ||
        !this.state.isActive ||
        this.state.projectId !== projectId ||
        this.candidateEditVersion !== capturedVersion ||
        this.candidateSaveReqId !== reqId
      ) {
        this.isMutatingSync = false;
        this.setState({ isSavingCandidate: false });
        return false;
      }

      if (!validateRes.valid) {
        // Validation failed: preserve unsaved edits in candidate
        this.isMutatingSync = false;
        this.setState({
          isSavingCandidate: false,
          candidateValidationError: 'Customized candidate violates geometric or safety constraints.',
          candidateValidationViolations: validateRes.violations || [],
        });
        return false;
      }

      // Use canonical candidate returned from validation if available
      const canonicalLandscape = validateRes.canonical_candidate || capturedLandscape;

      // 2. Save the validated canonical candidate
      const res = await (api as any).saveCandidate(projectId, {
        exterior_landscape: canonicalLandscape,
        source_revision: capturedRevision,
        requirements: capturedRequirements,
      });

      if (
        !this.state.isMounted ||
        !this.state.isActive ||
        this.state.projectId !== projectId ||
        this.candidateSaveReqId !== reqId
      ) {
        this.isMutatingSync = false;
        return false;
      }

      if (callbacks?.setOutput) {
        callbacks.setOutput('elia_engine', res.exterior_landscape);
      }
      if (callbacks?.setComponentStatus) {
        callbacks.setComponentStatus('elia_engine', 'completed');
      }

      this.setState({
        isSavingCandidate: false,
        sourceRevision: res.revision,
        acceptedLandscape: res.exterior_landscape,
        acceptedProvenance: {
          projectId,
          sourceRevision: res.revision,
          runId: res.run_id,
        },
        candidate: null,
        candidateEditHistory: [],
        activeView: 'accepted',
        selectedFeatureId: null,
        saveCandidateError: null,
      });

      this.isMutatingSync = false;

      // Refresh authoritative context after successful save to ensure master JSON is up to date
      await this.loadAuthoritativeContext(api);

      return true;
    } catch (err: any) {
      this.isMutatingSync = false;
      if (
        !this.state.isMounted ||
        !this.state.isActive ||
        this.state.projectId !== projectId ||
        this.candidateSaveReqId !== reqId
      ) {
        this.setState({ isSavingCandidate: false });
        return false;
      }

      const parsed = parseEliaError(err);
      if (parsed.isStaleRevision) {
        // 409 Revision conflict: preserve unsaved edits in candidate, report conflict
        this.setState({
          isSavingCandidate: false,
          saveCandidateError: `Revision Conflict (409): The project was modified concurrently (current revision is ${parsed.currentRevision ?? 'newer'}). Your custom edits have been preserved.`,
        });
        return false;
      }

      // If uncertain network outcome (timeout / 5xx / offline), reconcile state
      if (err.code === 'ECONNABORTED' || !err.response || err.response?.status >= 500) {
        this.setState({
          isSavingCandidate: false,
          saveCandidateError: 'Network or timeout occurred during save. Reconciling project state...',
        });
        await this.reconcileMutation(api);
        return false;
      }

      this.setState({
        isSavingCandidate: false,
        saveCandidateError: parsed.message,
      });
      return false;
    }
  }

  private handleApiError(parsed: EliaParsedError, api: EliaApiInterface) {
    if (parsed.isStaleRevision) {
      this.setState({
        conflictError: `Revision Conflict (409): The project was modified concurrently (current revision is ${parsed.currentRevision ?? 'newer'}). Your requirements form has been preserved. Please refresh context and regenerate.`,
      });
      this.loadAuthoritativeContext(api);
      return;
    }

    if (parsed.type === 'MODEL_UNAVAILABLE') {
      this.setState({ actionError: `${parsed.code}: ${parsed.message}` });
      return;
    }

    this.setState({ actionError: parsed.message });
  }
}
