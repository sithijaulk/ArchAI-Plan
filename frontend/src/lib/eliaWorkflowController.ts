import type {
  ExteriorLandscape,
  ELIAValidationResponse,
  ELIAResultResponse,
  EliaCandidateRecord,
  EliaContextFreshness,
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

    // Reset sequence counters so pre-activation requests are obsolete
    this.contextReqId += 1;
    this.latestRunReqId += 1;
    this.validationReqId += 1;
    this.mutationReqId += 1;
    this.locationSearchReqId += 1;
    this.solarReqId += 1;

    this.isMutatingSync = false;
    this.activeMutationToken = 0;

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

    this.isMutatingSync = false;
    this.activeMutationToken = 0;

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
    signal?: AbortSignal
  ): Promise<{ status: 'success' | 'failed' | 'obsolete'; revision?: number | null; master?: any; error?: string }> {
    const pid = this.state.projectId;
    if (!pid || !this.state.isMounted) return { status: 'obsolete' };

    const session = this.state.sessionSeq;
    const reqId = ++this.contextReqId;

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

      const doc = response.master_json;
      const rev = response.revision !== undefined && response.revision !== null
        ? response.revision
        : (doc && typeof doc.revision === 'number' ? doc.revision : null);

      const revisionChanged = this.state.sourceRevision !== null && rev !== this.state.sourceRevision;

      // Check for accepted exterior in Master JSON (strictly authoritative)
      const existingExterior = (doc?.exterior_landscape as ExteriorLandscape | null) ?? null;
      const acceptedLandscape = existingExterior && existingExterior.access ? existingExterior : null;
      const acceptedProvenance = acceptedLandscape ? {
        projectId: pid,
        sourceRevision: rev,
        sourceSnapshot: doc,
        runId: acceptedLandscape.run_id,
      } : null;

      this.setState({
        authoritativeMaster: doc,
        sourceRevision: rev,
        contextFreshness: 'current',
        requiresReconciliation: false,
        contextError: null,
        acceptedLandscape,
        acceptedProvenance,
        isLoadingContext: false,
        ...(revisionChanged ? { validationResult: null, validationError: null } : {}),
      });

      return { status: 'success', revision: rev, master: doc };
    } catch (err: any) {
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.contextReqId !== reqId || this.state.projectId !== pid) {
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

      this.setState({ latestRun: run, latestRunError: null, isCheckingRun: false, requiresReconciliation: false });
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

    if (this.state.requiresReconciliation) {
      this.releaseMutationGuard(token);
      this.setState({
        actionError: 'Project state must be reconciled by refreshing context before submitting another mutation.',
      });
      return { status: 'failed', error: 'Reconciliation required' };
    }

    if (this.state.contextFreshness !== 'current' || this.state.sourceRevision === null) {
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

        // Step 2: Await loadAuthoritativeContext
        const refreshResult = await this.loadAuthoritativeContext(api);

        // Recheck ownership after context refresh
        if (!this.state.isMounted || this.state.sessionSeq !== session || this.mutationReqId !== reqId || this.state.projectId !== pid) {
          return { status: 'obsolete' };
        }
        if (refreshResult.status === 'obsolete') {
          return { status: 'obsolete' };
        }

        // Step 3: Await loadLatestRun ONLY if still owned
        await this.loadLatestRun(api);
        if (!this.state.isMounted || this.state.sessionSeq !== session || this.mutationReqId !== reqId || this.state.projectId !== pid) {
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
        const refreshResult = await this.loadAuthoritativeContext(api);
        if (!this.state.isMounted || this.state.sessionSeq !== session || this.mutationReqId !== reqId || this.state.projectId !== pid) {
          return { status: 'obsolete' };
        }
        if (refreshResult.status === 'obsolete') {
          return { status: 'obsolete' };
        }

        await this.loadLatestRun(api);
        if (!this.state.isMounted || this.state.sessionSeq !== session || this.mutationReqId !== reqId || this.state.projectId !== pid) {
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
      if (!this.state.isMounted || this.state.sessionSeq !== session || this.mutationReqId !== reqId || this.state.projectId !== pid) {
        return { status: 'obsolete' };
      }

      const parsed = parseEliaError(err, 'Exterior layout generation failed.');
      this.handleApiError(parsed, api);

      if (!parsed.isStaleRevision && this.state.isMounted && this.state.sessionSeq === session && this.state.projectId === pid) {
        sharedStoreCallbacks?.setComponentStatus?.('elia_engine', 'failed');
      }

      // Ambiguous failure blocks blind resubmission until reconciliation
      if (!parsed.isStaleRevision && parsed.type !== 'MODEL_UNAVAILABLE') {
        this.setState({
          requiresReconciliation: true,
          contextFreshness: 'stale',
          actionError: `${parsed.message} Network outcome uncertain; please refresh context or inspect run history before retrying.`,
        });
      }

      this.setState({ isGenerating: false });
      return { status: 'failed', error: parsed.message };
    } finally {
      this.releaseMutationGuard(token);
    }
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
