import type {
  ExteriorLandscape,
  ELIAValidationResponse,
  ELIAResultResponse,
  EliaCandidateRecord,
  EliaContextFreshness,
  EliaUnresolvedMutation,
} from '../types/elia';
import type { SriLankaLocation, LiveSolarConditions } from './api/elia';
import {
  serializeRequirements,
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
  if (access.gates !== undefined && access.gates !== null && !Array.isArray(access.gates)) {
    return { valid: false, error: 'access.gates must be an array when present.' };
  }
  if (access.gate !== undefined && access.gate !== null && (typeof access.gate !== 'object' || Array.isArray(access.gate))) {
    return { valid: false, error: 'access.gate must be an object or null when present.' };
  }
  if (access.garage !== undefined && access.garage !== null && (typeof access.garage !== 'object' || Array.isArray(access.garage))) {
    return { valid: false, error: 'access.garage must be an object or null when present.' };
  }
  if (access.driveway !== undefined && access.driveway !== null && (typeof access.driveway !== 'object' || Array.isArray(access.driveway))) {
    return { valid: false, error: 'access.driveway must be an object or null when present.' };
  }

  // 3. Optional collection structures consumed by visualization components
  if (obj.vegetation_nodes !== undefined && obj.vegetation_nodes !== null && !Array.isArray(obj.vegetation_nodes)) {
    return { valid: false, error: 'vegetation_nodes must be an array when present.' };
  }
  if (obj.outdoor_elements !== undefined && obj.outdoor_elements !== null && !Array.isArray(obj.outdoor_elements)) {
    return { valid: false, error: 'outdoor_elements must be an array when present.' };
  }
  if (obj.vertical_greenery !== undefined && obj.vertical_greenery !== null) {
    if (typeof obj.vertical_greenery !== 'object' || Array.isArray(obj.vertical_greenery)) {
      return { valid: false, error: 'vertical_greenery must be an object when present.' };
    }
    const vg = obj.vertical_greenery as Record<string, unknown>;
    if (vg.elements !== undefined && vg.elements !== null && !Array.isArray(vg.elements)) {
      return { valid: false, error: 'vertical_greenery.elements must be an array when present.' };
    }
  }
  if (obj.outdoor_lighting !== undefined && obj.outdoor_lighting !== null) {
    if (typeof obj.outdoor_lighting !== 'object' || Array.isArray(obj.outdoor_lighting)) {
      return { valid: false, error: 'outdoor_lighting must be an object when present.' };
    }
    const ol = obj.outdoor_lighting as Record<string, unknown>;
    if (ol.nodes !== undefined && ol.nodes !== null && !Array.isArray(ol.nodes)) {
      return { valid: false, error: 'outdoor_lighting.nodes must be an array when present.' };
    }
  }
  if (obj.validation_summary !== undefined && obj.validation_summary !== null) {
    if (typeof obj.validation_summary !== 'object' || Array.isArray(obj.validation_summary)) {
      return { valid: false, error: 'validation_summary must be an object when present.' };
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

export function createDefaultFormState(): EliaFormState {
  return {
    generationMode: 'baseline',
    designStyle: 'contemporary',
    greeneryDensity: 'medium',
    openSpaceRatio: 0.3,
    shadeTreePreference: false,

    garageRequired: false,
    garageCapacity: 1,
    vehicleCount: 1,
    drivewayRequired: true,
    drivewayStyle: 'auto',
    turningSpaceRequired: true,
    gateType: 'unspecified',
    gateWidthM: 3.6,

    gardenRequired: true,
    lawnRequired: false,
    gardenSeatingRequired: false,
    gardenTableSetRequired: false,
    pedestrianPathRequired: false,
    gardenPathRequired: false,
    boundaryWallRequired: false,
    boundaryWallType: 'masonry',
    boundaryWallHeightM: 1.8,

    lightingRequired: false,
    lightingStyle: 'minimal',
    verticalGreeneryMode: 'automatic',

    selectedLocation: null,
    includeLiveSolar: false,
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

  // Validation channel
  isValidating: boolean;
  validationResult: ELIAValidationResponse | null;
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
}

export interface EliaApiInterface {
  getContext(projectId: string, options?: { signal?: AbortSignal }): Promise<{ master_json: any; revision?: number | null }>;
  getResult(projectId: string, options?: { signal?: AbortSignal }): Promise<ELIAResultResponse>;
  validateInput(projectId: string, payload: any, options?: { signal?: AbortSignal }): Promise<ELIAValidationResponse>;
  preview(payload: any, options?: { signal?: AbortSignal }): Promise<{ run_id: string; outcome: 'valid' | 'infeasible'; exterior_landscape: ExteriorLandscape }>;
  run(projectId: string, payload: any, options?: { signal?: AbortSignal }): Promise<{ run_id: string; outcome: 'valid' | 'infeasible'; exterior_landscape: ExteriorLandscape; master_json_updated?: boolean }>;
  searchLocations?(query: string, options?: { signal?: AbortSignal }): Promise<{ results: SriLankaLocation[] }>;
  currentSolar?(projectId: string, location: any, options?: { signal?: AbortSignal }): Promise<LiveSolarConditions>;
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
    this.setState({
      formState: updatedForm,
      requirementsDirty: true,
      validationResult: null, // Invalidate prior validation success immediately!
      validationError: null,
      actionError: null,
    });
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
    this.setState({ actionError: null });
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

      this.setState({
        authoritativeMaster: doc,
        sourceRevision: rev,
        contextFreshness: canBeCurrent ? 'current' : 'stale',
        contextError: null,
        acceptedLandscape, // Legitimately updated or cleared to null
        acceptedProvenance, // Legitimately updated or cleared to null
        activeView: nextActiveView,
        isLoadingContext: false,
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

      this.setState({ validationResult: response, isValidating: false });
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

      const candidateRecord: EliaCandidateRecord = {
        projectId: pid,
        runId: response.run_id,
        sourceRevision: submittedRevision,
        sourceSnapshot: snapshotAtSubmit,
        submittedFingerprint,
        generationMode: submittedGenerationMode,
        outcome: response.outcome,
        kind: 'preview',
        landscape: response.exterior_landscape,
        timestamp: new Date().toISOString(),
      };

      const currentFingerprint = computeRequirementsFingerprint(this.state.formState);
      const stillClean = currentFingerprint === submittedFingerprint;

      let actionNotice: string | null = null;
      if (response.outcome === 'infeasible') {
        const reason = response.exterior_landscape?.validation_summary?.violations?.join('; ') || 'Site boundary constraints could not be satisfied.';
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

      const candidateRecord: EliaCandidateRecord = {
        projectId: pid,
        runId: response.run_id,
        sourceRevision: submittedRevision,
        sourceSnapshot: snapshotAtSubmit,
        submittedFingerprint,
        generationMode: submittedGenerationMode,
        outcome: response.outcome,
        kind: 'persisted_run',
        landscape: response.exterior_landscape,
        timestamp: new Date().toISOString(),
      };

      const currentFingerprint = computeRequirementsFingerprint(this.state.formState);
      const stillClean = currentFingerprint === submittedFingerprint;

      if (response.outcome === 'valid') {
        if (this.state.isMounted && this.state.sessionSeq === session && this.state.projectId === pid) {
          sharedStoreCallbacks?.setOutput?.('elia_engine', response.exterior_landscape);
          sharedStoreCallbacks?.setComponentStatus?.('elia_engine', 'completed');
        }

        this.setState({
          candidate: candidateRecord,
          acceptedLandscape: response.exterior_landscape,
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
        const violations = response.exterior_landscape?.validation_summary?.violations?.join('; ') || 'Site boundary constraints could not be satisfied.';
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
        // Keep candidate state if output was returned, but DO NOT promote to accepted design!
        // The authoritative refresh above already loaded the still-valid accepted design (or null).
        if (outputFromLatestRun && typeof outputFromLatestRun === 'object') {
          const candValidation = validateExteriorLandscape(outputFromLatestRun);
          if (candValidation.valid) {
            this.setState({
              candidate: {
                projectId: pid,
                runId: correlatedRunId,
                sourceRevision: targetSourceRevision,
                sourceSnapshot: doc,
                submittedFingerprint: unresolved?.submittedFingerprint || '',
                generationMode: unresolved?.submittedGenerationMode || this.state.formState.generationMode,
                outcome: 'infeasible',
                kind: 'persisted_run',
                landscape: candValidation.value,
                timestamp: new Date().toISOString(),
              },
              activeView: this.state.acceptedLandscape ? this.state.activeView : 'candidate',
            });
          }
        }

        const violations = outputFromLatestRun?.validation_summary?.violations?.join('; ') || 'Site boundary constraints could not be satisfied.';
        this.setState({
          unresolvedMutation: null,
          requiresReconciliation: false,
          isReconciling: false,
          contextFreshness: 'current',
          actionError: `Infeasible Run: ${violations} (Previously accepted design preserved).`,
        });
        return { status: 'reconciled', message: 'Reconciled: terminal infeasible run.' };
      }

      // Terminal status is 'completed' (valid)
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
