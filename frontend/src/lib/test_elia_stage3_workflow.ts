/**
 * ELIA Stage 3 Production Workflow & Behavior Verification Tests
 *
 * Directly tests the production controller, serializer, and error utilities:
 *  - EliaWorkflowController
 *  - validateRequirementsForm, serializeRequirements, computeRequirementsFingerprint
 *  - parseStrictInteger, parseStrictFloat
 *  - parseEliaError
 *
 * Covers required Stage 3 regression tests A through H:
 *  - Case A: Accepted exterior removal (authoritative absence clears acceptedLandscape & acceptedProvenance)
 *  - Case B: Failed refresh preservation (keeps known design, marks stale, blocks export/save; rejects malformed)
 *  - Case C: Unrelated newer run (newer source revision does not unlock reconciliation)
 *  - Case D: Missing or contradictory evidence (missing link, contradictory run/rev, contradictory status, processing)
 *  - Case E: Valid terminal reconciliation (completed + success refresh, refresh failure, failed outcome handling)
 *  - Case F: Project-switch race during reconciliation (old refresh cannot clear new project's mutation epoch/guard)
 *  - Case G: Overlapping reconciliation & lifecycle behavior (synchronous guard, deactivation/reactivation)
 *  - Case H: Existing workflow regressions (lifecycle, preview, CAS, serialization, export, mode-capture, solar-invalidation)
 *
 * Uses actual controller/public workflow methods and controlled deferred API responses.
 * Dynamically counts and reports exact executed test count.
 */
import assert from 'assert'
import {
  EliaWorkflowController,
  createDefaultFormState,
  type EliaApiInterface,
} from './eliaWorkflowController'
import {
  parseStrictInteger,
  parseStrictFloat,
  validateRequirementsForm,
  serializeRequirements,
  computeRequirementsFingerprint,
} from './eliaSerialization'
import { parseEliaError } from './eliaError'
import type { ExteriorLandscape } from '../types/elia'

function createDeferredPromise<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: any) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  promise.catch(() => {})
  return { promise, resolve, reject }
}

const noopApi: EliaApiInterface = {
  getContext: async () => ({ master_json: { id: 'test' }, revision: 1 }),
  getResult: async () => ({ run_id: 'test_run', status: 'completed' } as any),
  validateInput: async () => ({ valid: true } as any),
  preview: async () => ({ run_id: 'prev_1', outcome: 'valid', exterior_landscape: { run_id: 'prev_1', access: {} } as any }),
  run: async () => ({ run_id: 'run_1', outcome: 'valid', exterior_landscape: { run_id: 'run_1', access: {} } as any }),
}

let testCount = 0
function passTest(title: string) {
  testCount++
  console.log(`✓ ${testCount}. ${title}`)
}

console.log('Running ELIA Stage 3 Production Behavior Tests...\n')

async function runAllTests() {
  // ===========================================================================
  // GROUP 1: LIFECYCLE & STRICT MODE (Case H)
  // ===========================================================================

  // 1. Deactivate → reactivate → load context succeeds with fresh session
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.deactivate()
    assert.strictEqual(controller.getState().isMounted, false)
    assert.strictEqual(controller.getState().isActive, false)

    const freshSession = controller.activate('proj_1')
    assert.strictEqual(controller.getState().isMounted, true)
    assert.strictEqual(controller.getState().isActive, true)
    assert.strictEqual(controller.getState().sessionSeq, freshSession)

    const res = await controller.loadAuthoritativeContext(noopApi)
    assert.strictEqual(res.status, 'success')
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    passTest('Deactivate → reactivate → load context succeeds with fresh session')
  }

  // 2. Old-session responses remain invalid after reactivation
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')

    const defOld = createDeferredPromise<any>()
    const apiOld: EliaApiInterface = {
      ...noopApi,
      getContext: () => defOld.promise,
    }

    const pOld = controller.loadAuthoritativeContext(apiOld)

    controller.deactivate()
    controller.activate('proj_1')

    defOld.resolve({ master_json: { id: 'old_data' }, revision: 99 })
    const resOld = await pOld

    assert.strictEqual(resOld.status, 'obsolete')
    assert.strictEqual(controller.getState().sourceRevision, null)
    assert.strictEqual(controller.getState().authoritativeMaster, null)
    passTest('Old-session responses remain strictly invalid after reactivation')
  }

  // 3. React Strict Mode setup/cleanup/setup sequence leaves controller operational
  {
    const controller = new EliaWorkflowController('proj_strict')

    controller.activate('proj_strict')
    const defCtx1 = createDeferredPromise<any>()
    controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defCtx1.promise })

    controller.deactivate()

    controller.activate('proj_strict')
    assert.strictEqual(controller.getState().isMounted, true)
    assert.strictEqual(controller.getState().isActive, true)

    const defCtx2 = createDeferredPromise<any>()
    const p2 = controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defCtx2.promise })

    defCtx1.resolve({ master_json: { id: 'run1' }, revision: 1 })
    defCtx2.resolve({ master_json: { id: 'run2' }, revision: 2 })

    const res2 = await p2
    assert.strictEqual(res2.status, 'success')
    assert.strictEqual(controller.getState().sourceRevision, 2)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    passTest('React Strict Mode setup/cleanup/setup sequence leaves controller operational')
  }

  // 4. Server rendering / hydration snapshot is stable, frozen, and matches SSR
  {
    const serverSnapshot = EliaWorkflowController.getServerSnapshot()
    assert.strictEqual(serverSnapshot.projectId, null)
    assert.strictEqual(serverSnapshot.isMounted, false)
    assert.strictEqual(serverSnapshot.contextFreshness, 'unavailable')
    assert.strictEqual(Object.isFrozen(serverSnapshot), true)

    const controller = new EliaWorkflowController(null)
    const instanceServerSnapshot = controller.getServerSnapshot()
    assert.strictEqual(instanceServerSnapshot, serverSnapshot)
    passTest('Server rendering / hydration snapshot is stable, frozen, and matches SSR')
  }

  // ===========================================================================
  // GROUP 2: SOLAR, LOCATION, & FORM VALIDATION (Case H)
  // ===========================================================================

  // 5. Location change during solar lookup immediately resets isLoadingSolar
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    const loc1 = { id: 1, name: 'Colombo', latitude: 6.9271, longitude: 79.8612, attribution: '' }
    const loc2 = { id: 2, name: 'Kandy', latitude: 7.2906, longitude: 80.6337, attribution: '' }

    controller.selectLocation(loc1)
    const defSolar = createDeferredPromise<any>()
    const pSolar = controller.loadSolar({ ...noopApi, currentSolar: () => defSolar.promise }, loc1)
    assert.strictEqual(controller.getState().isLoadingSolar, true)

    controller.selectLocation(loc2)
    assert.strictEqual(controller.getState().isLoadingSolar, false)
    assert.strictEqual(controller.getState().solar, null)

    defSolar.resolve({ status: 'available', irradiance_w_m2: { ghi: 500 } } as any)
    const resSolar = await pSolar
    assert.strictEqual(resSolar.status, 'obsolete')
    assert.strictEqual(controller.getState().solar, null)
    passTest('Location change during solar lookup immediately resets isLoadingSolar')
  }

  // 6. Old solar completion cannot stop a newer solar loading state
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    const loc1 = { id: 1, name: 'Colombo', latitude: 6.9271, longitude: 79.8612, attribution: '' }
    const loc2 = { id: 2, name: 'Galle', latitude: 6.0535, longitude: 80.221, attribution: '' }

    controller.selectLocation(loc1)
    const defSolar1 = createDeferredPromise<any>()
    const pSolar1 = controller.loadSolar({ ...noopApi, currentSolar: () => defSolar1.promise }, loc1)

    controller.selectLocation(loc2)
    const defSolar2 = createDeferredPromise<any>()
    const pSolar2 = controller.loadSolar({ ...noopApi, currentSolar: () => defSolar2.promise }, loc2)
    assert.strictEqual(controller.getState().isLoadingSolar, true)

    defSolar1.resolve({ status: 'available', irradiance_w_m2: { ghi: 300 } } as any)
    await pSolar1
    assert.strictEqual(controller.getState().isLoadingSolar, true)

    defSolar2.resolve({ status: 'available', irradiance_w_m2: { ghi: 600 } } as any)
    const resSolar2 = await pSolar2
    assert.strictEqual(resSolar2.status, 'success')
    assert.strictEqual(controller.getState().isLoadingSolar, false)
    assert.strictEqual((controller.getState().solar as any)?.irradiance_w_m2?.ghi, 600)
    passTest('Old solar completion cannot stop a newer solar loading state')
  }

  // 7. Clearing location handles pending solar success and failure cleanly
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    const loc = { id: 1, name: 'Jaffna', latitude: 9.6615, longitude: 80.0255, attribution: '' }

    controller.selectLocation(loc)
    const defSolar = createDeferredPromise<any>()
    const pSolar = controller.loadSolar({ ...noopApi, currentSolar: () => defSolar.promise }, loc)

    controller.selectLocation(null)
    assert.strictEqual(controller.getState().isLoadingSolar, false)
    assert.strictEqual(controller.getState().solar, null)

    defSolar.reject(new Error('Solar API error'))
    const resSolar = await pSolar
    assert.strictEqual(resSolar.status, 'obsolete')
    assert.strictEqual(controller.getState().locationError, null)
    passTest('Clearing location handles pending solar success and failure cleanly')
  }

  // 8. Project switch during post-save refresh causes no cross-project follow-up or error notice
  {
    const controller = new EliaWorkflowController('proj_A')
    controller.activate('proj_A')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_A', revision: 1 }, revision: 1 }),
    })

    const defSaveCtx = createDeferredPromise<any>()
    let latestRunCallCount = 0

    const apiPostSave: EliaApiInterface = {
      ...noopApi,
      run: async () => ({
        run_id: 'run_A',
        outcome: 'valid',
        exterior_landscape: { run_id: 'run_A', access: {} } as any,
      }),
      getContext: () => defSaveCtx.promise,
      getResult: async () => {
        latestRunCallCount++
        return { run_id: 'run_A', status: 'completed' } as any
      },
    }

    const pSave = controller.generateAndSave(apiPostSave)
    await new Promise((r) => setTimeout(r, 10))

    controller.changeProject('proj_B')
    assert.strictEqual(controller.getState().projectId, 'proj_B')

    defSaveCtx.reject(new Error('Network error on old project A'))
    const resSave = await pSave

    assert.strictEqual(resSave.status, 'obsolete')
    assert.strictEqual(latestRunCallCount, 0)
    assert.strictEqual(controller.getState().actionError, null)
    assert.strictEqual(controller.getState().projectId, 'proj_B')
    passTest('Project switch during post-save refresh causes no cross-project follow-up or error notice')
  }

  // 9. Project switch during latest-run refresh causes no cross-project state write
  {
    const controller = new EliaWorkflowController('proj_A')
    controller.activate('proj_A')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_A', revision: 1 }, revision: 1 }),
    })

    const defRunRefresh = createDeferredPromise<any>()
    const apiLatestRunRace: EliaApiInterface = {
      ...noopApi,
      run: async () => ({
        run_id: 'run_A',
        outcome: 'valid',
        exterior_landscape: { run_id: 'run_A', access: {} } as any,
      }),
      getContext: async () => ({ master_json: { id: 'proj_A', revision: 2 }, revision: 2 }),
      getResult: () => defRunRefresh.promise,
    }

    const pSave = controller.generateAndSave(apiLatestRunRace)
    await new Promise((r) => setTimeout(r, 10))

    controller.changeProject('proj_B')

    defRunRefresh.resolve({ run_id: 'run_A_result', status: 'completed' })
    const resSave = await pSave

    assert.strictEqual(resSave.status, 'obsolete')
    assert.strictEqual(controller.getState().latestRun, null)
    assert.strictEqual(controller.getState().projectId, 'proj_B')
    passTest('Project switch during latest-run refresh causes no cross-project state write')
  }

  // 10. Unmount during post-save refresh cleanly prevents later state writes
  {
    const controller = new EliaWorkflowController('proj_A')
    controller.activate('proj_A')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_A', revision: 1 }, revision: 1 }),
    })

    const defSaveCtx = createDeferredPromise<any>()
    const apiUnmount: EliaApiInterface = {
      ...noopApi,
      run: async () => ({
        run_id: 'run_A',
        outcome: 'valid',
        exterior_landscape: { run_id: 'run_A', access: {} } as any,
      }),
      getContext: () => defSaveCtx.promise,
    }

    const pSave = controller.generateAndSave(apiUnmount)
    await new Promise((r) => setTimeout(r, 10))

    controller.unmount()
    assert.strictEqual(controller.getState().isMounted, false)
    assert.strictEqual(controller.getState().isActive, false)

    defSaveCtx.resolve({ master_json: { id: 'proj_A', revision: 2 }, revision: 2 })
    const resSave = await pSave

    assert.strictEqual(resSave.status, 'obsolete')
    assert.strictEqual(controller.getState().isMounted, false)
    assert.strictEqual(controller.getState().isGenerating, false)
    passTest('Unmount during post-save refresh cleanly prevents later state writes')
  }

  // 11. Validation error after a form edit is discarded as obsolete
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_1', revision: 1 }, revision: 1 }),
    })

    const defVal = createDeferredPromise<any>()
    const pVal = controller.validateRequirements({
      ...noopApi,
      validateInput: () => defVal.promise,
    })

    controller.editRequirement({ designStyle: 'traditional' })
    defVal.reject(new Error('Validation rule failed on old form input'))
    const resVal = await pVal

    assert.strictEqual(resVal.status, 'obsolete')
    assert.strictEqual(controller.getState().validationError, null)
    passTest('Validation error after a form edit is discarded as obsolete')
  }

  // 12. Validation result after source revision change is discarded
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_1', revision: 1 }, revision: 1 }),
    })

    const defVal = createDeferredPromise<any>()
    const pVal = controller.validateRequirements({
      ...noopApi,
      validateInput: () => defVal.promise,
    })

    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_1', revision: 2 }, revision: 2 }),
    })

    defVal.resolve({ valid: true, project_id: 'proj_1' } as any)
    const resVal = await pVal

    assert.strictEqual(resVal.status, 'obsolete')
    assert.strictEqual(controller.getState().validationResult, null)
    passTest('Validation result after source revision change is discarded')
  }

  // 13. Generation-mode edit during request does not corrupt candidate submitted mode
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_1', revision: 1 }, revision: 1 }),
    })
    controller.editRequirement({ generationMode: 'baseline' })

    const defPrev = createDeferredPromise<any>()
    const prevPromise = controller.previewCandidate({
      ...noopApi,
      preview: () => defPrev.promise,
    })

    controller.editRequirement({ generationMode: 'trained_model' })

    defPrev.resolve({ run_id: 'prev_base', outcome: 'valid', exterior_landscape: { run_id: 'prev_base', access: {} } as any })
    await prevPromise

    assert.strictEqual(controller.getState().candidate?.generationMode, 'baseline')
    passTest('Generation-mode edit during request does not corrupt candidate submitted mode')
  }

  // 14. Authoritative export is disabled during refresh and after refresh failure
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_1', revision: 1 }, revision: 1 }),
    })
    assert.strictEqual(controller.canExportMasterJson(), true)

    const defCtx = createDeferredPromise<any>()
    const pCtx = controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defCtx.promise })

    assert.notStrictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.canExportMasterJson(), false)

    defCtx.reject(new Error('Network error'))
    await pCtx

    assert.strictEqual(controller.getState().contextFreshness, 'stale')
    assert.strictEqual(controller.canExportMasterJson(), false)
    passTest('Authoritative export is disabled during refresh and after refresh failure')
  }

  // 15. Save success plus refresh failure retains correctly paired accepted source snapshot
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    const originalSnapshot = { id: 'proj_1', revision: 1, boundary: 'v1_polygon' }
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: originalSnapshot, revision: 1 }),
    })

    const api: EliaApiInterface = {
      ...noopApi,
      run: async () => ({
        run_id: 'run_saved_99',
        outcome: 'valid',
        exterior_landscape: { run_id: 'run_saved_99', access: {} } as any,
      }),
      getContext: async () => {
        throw new Error('500 Internal Server Error during refresh')
      },
    }

    const res = await controller.generateAndSave(api)
    assert.strictEqual(res.status, 'success')
    assert.strictEqual(res.refreshStatus, 'failed')
    assert.strictEqual((controller.getState().acceptedProvenance?.sourceSnapshot as any).boundary, 'v1_polygon')
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_saved_99')
    passTest('Save success plus refresh failure retains correctly paired accepted source snapshot')
  }

  // ===========================================================================
  // GROUP 3: CORE STAGE 3 DEFECT REGRESSIONS (Cases A - G)
  // ===========================================================================

  // ---------------------------------------------------------------------------
  // Case A: Accepted exterior removal (FIX 1)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseA')
    controller.activate('proj_caseA')

    const initialExterior = { run_id: 'run_prev_saved', access: { existing: true } } as any
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_caseA', revision: 1, exterior_landscape: initialExterior },
        revision: 1,
      }),
    })

    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_prev_saved')
    assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_prev_saved')
    assert.strictEqual(controller.getState().activeView, 'accepted')

    // Create a candidate so we can verify activeView transitions
    await controller.previewCandidate({
      ...noopApi,
      preview: async () => ({
        run_id: 'cand_preview_1',
        outcome: 'valid',
        exterior_landscape: { run_id: 'cand_preview_1', access: {} } as any,
      }),
    })
    assert.strictEqual(controller.getState().candidate?.runId, 'cand_preview_1')

    // Set view to accepted
    controller.toggleActiveView('accepted')
    assert.strictEqual(controller.getState().activeView, 'accepted')

    // Subsequent valid authoritative response legitimately contains NO exterior_landscape
    const resAbsence = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_caseA', revision: 2 }, // exterior_landscape explicitly absent!
        revision: 2,
      }),
    })

    assert.strictEqual(resAbsence.status, 'success')
    // BOTH acceptedLandscape and acceptedProvenance MUST be cleared to null
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.getState().acceptedProvenance, null)
    // View transitions to candidate because candidate exists
    assert.strictEqual(controller.getState().activeView, 'candidate')
    assert.strictEqual(controller.getState().sourceRevision, 2)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    passTest('Case A: Authoritative absence clears both acceptedLandscape and acceptedProvenance together')
  }

  // ---------------------------------------------------------------------------
  // Case B: Failed refresh preservation & malformed payload rejection (FIX 1)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseB')
    controller.activate('proj_caseB')

    const initialExterior = { run_id: 'run_init_b', access: { existing: true } } as any
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_caseB', revision: 1, exterior_landscape: initialExterior },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_init_b')

    // Refresh fails with network error
    const resFail = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => {
        throw new Error('503 Service Unavailable')
      },
    })
    assert.strictEqual(resFail.status, 'failed')
    // Previously known design remains intact!
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_init_b')
    assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_init_b')
    assert.strictEqual(controller.getState().contextFreshness, 'stale')
    assert.strictEqual(controller.canExportMasterJson(), false)
    assert.strictEqual(controller.canGenerateAndSave(), false)

    // Now test malformed payloads: null, string, non-object master_json must be rejected as failed, NOT deletion
    const resMalformed = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: null, revision: 2 } as any),
    })
    assert.strictEqual(resMalformed.status, 'failed')
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_init_b')
    assert.strictEqual(controller.getState().contextFreshness, 'stale')
    passTest('Case B: Failed refresh preserves known design with truthful stale status and export/save restrictions')
  }

  // ---------------------------------------------------------------------------
  // Case C: Unrelated newer run does not clear reconciliation guard (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseC')
    controller.activate('proj_caseC')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseC', revision: 2 }, revision: 2 }),
    })

    // Cause ambiguous save failure at revision 2
    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Gateway Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().unresolvedMutation?.sourceRevision, 2)

    // Backend returns latestRun and processing metadata that match each other (run_id: 'run_newer'),
    // BUT their source_revision is 3 (a newer request than our unresolved revision 2)!
    const apiNewerRun: EliaApiInterface = {
      ...noopApi,
      getResult: async () => ({ run_id: 'run_newer', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseC',
          revision: 4,
          processing: {
            elia_engine: {
              status: 'completed',
              run_id: 'run_newer',
              source_revision: 3, // newer source revision!
            },
          },
        },
        revision: 4,
      }),
    }

    const resRecon = await controller.reconcileMutation(apiNewerRun)
    assert.strictEqual(resRecon.status, 'unresolved')
    // Reconciliation must NOT unlock saving or export
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.strictEqual(controller.canExportMasterJson(), false)
    passTest('Case C: Unrelated newer run matching IDs does not unlock reconciliation guard')
  }

  // ---------------------------------------------------------------------------
  // Case D1: Matching run IDs without proven link to uncertain request (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseD1')
    controller.activate('proj_caseD1')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseD1', revision: 2 }, revision: 2 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Connection reset')
        err.code = 'ECONNRESET'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    // procRunId matches latestRun.run_id, but proc has NO source_revision and no known link
    const apiNoSourceRev: EliaApiInterface = {
      ...noopApi,
      getResult: async () => ({ run_id: 'run_unknown_link', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseD1',
          revision: 3,
          processing: {
            elia_engine: {
              status: 'completed',
              run_id: 'run_unknown_link',
              // source_revision is missing!
            },
          },
        },
        revision: 3,
      }),
    }

    const res = await controller.reconcileMutation(apiNoSourceRev)
    assert.strictEqual(res.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    passTest('Case D1: Matching run IDs without proven link to uncertain request remain unresolved')
  }

  // ---------------------------------------------------------------------------
  // Case D2: Contradictory run / revision evidence remains unresolved (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseD2')
    controller.activate('proj_caseD2')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseD2', revision: 2 }, revision: 2 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })

    // Correlate to run_captured in processing cycle first
    await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_captured', status: 'processing' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseD2',
          revision: 2,
          processing: { elia_engine: { status: 'processing', run_id: 'run_captured', source_revision: 2 } },
        },
        revision: 2,
      }),
    })
    assert.strictEqual(controller.getState().unresolvedMutation?.correlatedRunId, 'run_captured')

    // Now backend presents contradictory metadata: run_captured associated with source_revision 5
    const resContradictory = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_captured', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseD2',
          revision: 6,
          processing: { elia_engine: { status: 'completed', run_id: 'run_captured', source_revision: 5 } },
        },
        revision: 6,
      }),
    })

    assert.strictEqual(resContradictory.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    passTest('Case D2: Contradictory run and revision evidence remains unresolved')
  }

  // ---------------------------------------------------------------------------
  // Case D3: Contradictory status evidence remains unresolved (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseD3')
    controller.activate('proj_caseD3')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseD3', revision: 2 }, revision: 2 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })

    // processing channel says 'completed', latestRun channel says 'failed'
    const resStatusConflict = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_conflict', status: 'failed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseD3',
          revision: 3,
          processing: { elia_engine: { status: 'completed', run_id: 'run_conflict', source_revision: 2 } },
        },
        revision: 3,
      }),
    })

    assert.strictEqual(resStatusConflict.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    passTest('Case D3: Contradictory status evidence between channels remains unresolved')
  }

  // ---------------------------------------------------------------------------
  // Case D4: A correlated processing run keeps unresolved guard active (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseD4')
    controller.activate('proj_caseD4')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseD4', revision: 2 }, revision: 2 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    const res = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_proc_d4', status: 'processing' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseD4',
          revision: 2,
          processing: { elia_engine: { status: 'processing', run_id: 'run_proc_d4', source_revision: 2 } },
        },
        revision: 2,
      }),
    })

    assert.strictEqual(res.status, 'processing')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().unresolvedMutation?.status, 'processing')
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.strictEqual(controller.canExportMasterJson(), false)
    passTest('Case D4: A correlated processing run keeps unresolved guard active and mutations blocked')
  }

  // ---------------------------------------------------------------------------
  // Case E1: Valid terminal completed outcome clears guard appropriately (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseE1')
    controller.activate('proj_caseE1')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseE1', revision: 2 }, revision: 2 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    const res = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_e1', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseE1',
          revision: 3,
          processing: { elia_engine: { status: 'completed', run_id: 'run_e1', source_revision: 2 } },
          exterior_landscape: { run_id: 'run_e1', access: { gate: { json_id: 'gate_e1' } } },
        },
        revision: 3,
      }),
    })

    assert.strictEqual(res.status, 'reconciled')
    assert.strictEqual(controller.getState().requiresReconciliation, false)
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_e1')
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.canGenerateAndSave(), true)
    passTest('Case E1: Valid terminal completed outcome plus successful authoritative refresh clears guard')
  }

  // ---------------------------------------------------------------------------
  // Case E2: Terminal failure outcome is not displayed as successful accepted design (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseE2')
    controller.activate('proj_caseE2')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseE2', revision: 2 }, revision: 2 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    // Backend reports run failed
    const res = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_fail', status: 'failed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseE2',
          revision: 3,
          processing: { elia_engine: { status: 'failed', run_id: 'run_fail', source_revision: 2 } },
          // No exterior_landscape saved!
        },
        revision: 3,
      }),
    })

    assert.strictEqual(res.status, 'reconciled')
    assert.strictEqual(controller.getState().requiresReconciliation, false)
    // Crucial: terminal failure outcome MUST NOT be displayed as successful accepted design
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.getState().acceptedProvenance, null)
    assert.ok(controller.getState().actionError?.includes('Backend run failed'))
    assert.strictEqual(controller.canGenerateAndSave(), true)
    passTest('Case E2: Terminal failure outcome is not displayed as successful accepted design')
  }

  // ---------------------------------------------------------------------------
  // Case E3: Terminal run verified but authoritative refresh fails retains guard (FIX 2)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseE3')
    controller.activate('proj_caseE3')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseE3', revision: 2 }, revision: 2 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    let getCtxCall = 0
    const res = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_e3', status: 'completed' } as any),
      getContext: async () => {
        getCtxCall++
        if (getCtxCall === 1) {
          return {
            master_json: {
              id: 'proj_caseE3',
              revision: 3,
              processing: { elia_engine: { status: 'completed', run_id: 'run_e3', source_revision: 2 } },
            },
            revision: 3,
          }
        }
        // Owned context refresh fails!
        throw new Error('500 Server Error during refresh')
      },
    })

    assert.strictEqual(res.status, 'failed')
    // Guard MUST remain active!
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().contextFreshness, 'stale')
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.strictEqual(controller.canExportMasterJson(), false)
    passTest('Case E3: Terminal run verified but authoritative refresh fails retains unresolved guard')
  }

  // ---------------------------------------------------------------------------
  // Case F: Project-switch race during reconciliation (FIX 3)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_race_A')
    controller.activate('proj_race_A')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_race_A', revision: 1 }, revision: 1 }),
    })

    // Ambiguous failure on proj_race_A
    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    // Start reconciliation on proj_race_A with a deferred context refresh
    let contextCallCount = 0
    const defRefreshCtxA = createDeferredPromise<any>()
    const pReconA = controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_A', status: 'completed' } as any),
      getContext: async () => {
        contextCallCount++
        if (contextCallCount === 1) {
          return {
            master_json: {
              id: 'proj_race_A',
              revision: 2,
              processing: { elia_engine: { status: 'completed', run_id: 'run_A', source_revision: 1 } },
            },
            revision: 2,
          }
        }
        return defRefreshCtxA.promise
      },
    })

    // Wait until reconciliation is awaiting its owned context refresh
    await new Promise((r) => setTimeout(r, 10))

    // User switches to proj_race_B and starts a new operation
    controller.changeProject('proj_race_B')
    assert.strictEqual(controller.getState().projectId, 'proj_race_B')

    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_race_B', revision: 10 }, revision: 10 }),
    })

    // Start a mutation on proj_race_B with deferred run
    const defRunB = createDeferredPromise<any>()
    const pSaveB = controller.generateAndSave({
      ...noopApi,
      run: () => defRunB.promise,
    })

    // proj_race_B is now actively mutating
    assert.strictEqual(controller.getState().isGenerating, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)

    // Now resolve proj_race_A's paused context refresh
    defRefreshCtxA.resolve({
      master_json: { id: 'proj_race_A', revision: 3 },
      revision: 3,
    })

    const reconResA = await pReconA
    assert.strictEqual(reconResA.status, 'obsolete')

    // Confirm proj_race_A DID NOT clear proj_race_B's active mutation guard or busy state!
    assert.strictEqual(controller.getState().projectId, 'proj_race_B')
    assert.strictEqual(controller.getState().isGenerating, true)
    assert.strictEqual(controller.getState().requiresReconciliation, false)

    // Clean up proj_race_B's mutation
    defRunB.resolve({
      run_id: 'run_B',
      outcome: 'valid',
      exterior_landscape: { run_id: 'run_B', access: {} } as any,
    })
    await pSaveB
    assert.strictEqual(controller.getState().isGenerating, false)
    passTest('Case F: Project-switch race during reconciliation preserves new project mutation epoch and guards')
  }

  // ---------------------------------------------------------------------------
  // Case G1: Synchronous guard against overlapping reconciliation calls (FIX 3)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseG1')
    controller.activate('proj_caseG1')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseG1', revision: 1 }, revision: 1 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    // Start reconciliation 1 with deferred promise
    const defRecon1 = createDeferredPromise<any>()
    const pRecon1 = controller.reconcileMutation({
      ...noopApi,
      getResult: () => defRecon1.promise,
      getContext: () => defRecon1.promise,
    })

    // Attempt overlapping reconciliation 2 while reconciliation 1 is synchronous in flight
    const pRecon2 = controller.reconcileMutation(noopApi)
    const res2 = await pRecon2

    // Second overlapping attempt is immediately rejected as obsolete
    assert.strictEqual(res2.status, 'obsolete')

    // Resolve reconciliation 1
    defRecon1.reject(new Error('Network error'))
    const res1 = await pRecon1
    assert.strictEqual(res1.status, 'unresolved')
    assert.strictEqual(controller.getState().isReconciling, false)
    passTest('Case G1: Overlapping reconciliation attempts are rejected synchronously by guard')
  }

  // ---------------------------------------------------------------------------
  // Case G2: Deactivation during reconciliation stops continuation cleanly (FIX 3)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseG2')
    controller.activate('proj_caseG2')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseG2', revision: 1 }, revision: 1 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })

    const defRecon = createDeferredPromise<any>()
    const pRecon = controller.reconcileMutation({
      ...noopApi,
      getResult: () => defRecon.promise,
      getContext: () => defRecon.promise,
    })

    controller.deactivate()
    assert.strictEqual(controller.getState().isActive, false)

    defRecon.resolve({ run_id: 'late_run', status: 'completed' })
    const res = await pRecon
    assert.strictEqual(res.status, 'obsolete')
    assert.strictEqual(controller.getState().isReconciling, false)
    assert.strictEqual(controller.getState().isActive, false)
    passTest('Case G2: Late results after deactivation are ignored without lingering locks')
  }

  // ---------------------------------------------------------------------------
  // Case H1: Pending context refresh correctly prevents mutation; resolving context restores eligibility
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseH1')
    controller.activate('proj_caseH1')
    const defCtx = createDeferredPromise<any>()
    const pCtx = controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defCtx.promise })

    const resSave = await controller.generateAndSave(noopApi)
    assert.strictEqual(resSave.status, 'failed')
    assert.strictEqual(controller.canGenerateAndSave(), false)

    defCtx.resolve({ master_json: { id: 'proj_caseH1', revision: 1 }, revision: 1 })
    const resCtx = await pCtx
    assert.strictEqual(resCtx.status, 'success')
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.canGenerateAndSave(), true)
    passTest('Case H1: Pending context refresh correctly prevents mutation; resolving context restores eligibility')
  }

  // ---------------------------------------------------------------------------
  // Case H2: While Generate & Save is pending, authoritative export and another mutation remain blocked
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseH2')
    controller.activate('proj_caseH2')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseH2', revision: 1 }, revision: 1 }),
    })
    assert.strictEqual(controller.canGenerateAndSave(), true)

    const defRun = createDeferredPromise<any>()
    const pSave = controller.generateAndSave({ ...noopApi, run: () => defRun.promise })

    assert.strictEqual(controller.getState().isGenerating, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.strictEqual(controller.canExportMasterJson(), false)

    const resSecondSave = await controller.generateAndSave(noopApi)
    assert.strictEqual(resSecondSave.status, 'obsolete')

    defRun.resolve({
      run_id: 'run_caseH2',
      outcome: 'valid',
      exterior_landscape: { run_id: 'run_caseH2', access: {} } as any,
    })
    await pSave
    passTest('Case H2: While Generate & Save is pending, authoritative export and another mutation remain blocked')
  }

  // ---------------------------------------------------------------------------
  // Case H3: Resolving context before pending save completes does not unlock mutation or expose pre-save JSON
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseH3')
    controller.activate('proj_caseH3')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseH3', revision: 1 }, revision: 1 }),
    })

    const defRun = createDeferredPromise<any>()
    const pSave = controller.generateAndSave({ ...noopApi, run: () => defRun.promise })

    const defConcurrentCtx = createDeferredPromise<any>()
    const pCtx = controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defConcurrentCtx.promise })

    defConcurrentCtx.resolve({ master_json: { id: 'proj_caseH3', revision: 1 }, revision: 1 })
    const resCtx = await pCtx
    assert.strictEqual(resCtx.status, 'success')

    assert.strictEqual(controller.getState().contextFreshness, 'stale')
    assert.strictEqual(controller.getState().isGenerating, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.strictEqual(controller.canExportMasterJson(), false)

    defRun.resolve({
      run_id: 'run_caseH3',
      outcome: 'valid',
      exterior_landscape: { run_id: 'run_caseH3', access: {} } as any,
    })
    await pSave
    passTest('Case H3: Resolving context before pending save completes does not unlock mutation or expose pre-save JSON')
  }

  // ---------------------------------------------------------------------------
  // Case H4: Ambiguous network failure blocks immediate resubmission without issuing another API run call
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseH4')
    controller.activate('proj_caseH4')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseH4', revision: 1 }, revision: 1 }),
    })

    let runCallCount = 0
    const apiNetworkFail: EliaApiInterface = {
      ...noopApi,
      run: async () => {
        runCallCount++
        const err: any = new Error('Network timeout (ECONNABORTED)')
        err.code = 'ECONNABORTED'
        throw err
      },
    }

    const resFail = await controller.generateAndSave(apiNetworkFail)
    assert.strictEqual(resFail.status, 'failed')
    assert.strictEqual(runCallCount, 1)
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.strictEqual(controller.canExportMasterJson(), false)

    const resResubmit = await controller.generateAndSave(apiNetworkFail)
    assert.strictEqual(resResubmit.status, 'failed')
    assert.strictEqual(resResubmit.error, 'Reconciliation required')
    assert.strictEqual(runCallCount, 1) // NO second run call
    passTest('Case H4: Ambiguous network failure blocks immediate resubmission without issuing another API run call')
  }

  // ---------------------------------------------------------------------------
  // Case H5: Infeasible run preserves accepted design while updating revision and freshness
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseH5')
    controller.activate('proj_caseH5')

    const initialAccepted = { run_id: 'run_prev_h5', access: { existing: true } } as any
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_caseH5', revision: 1, exterior_landscape: initialAccepted },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_prev_h5')

    const apiInfeasible: EliaApiInterface = {
      ...noopApi,
      run: async () => ({
        run_id: 'run_inf_h5',
        outcome: 'infeasible',
        exterior_landscape: { run_id: 'run_inf_h5', access: {}, validation_summary: { violations: ['Overlap'] } } as any,
      }),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseH5',
          revision: 3,
          exterior_landscape: initialAccepted,
          processing: { elia_engine: { status: 'infeasible', run_id: 'run_inf_h5', source_revision: 1 } },
        },
        revision: 3,
      }),
      getResult: async () => ({ run_id: 'run_inf_h5', status: 'infeasible' } as any),
    }

    const resInf = await controller.generateAndSave(apiInfeasible)
    assert.strictEqual(resInf.status, 'success')
    assert.strictEqual(resInf.refreshStatus, 'success')
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_prev_h5')
    assert.strictEqual(controller.getState().candidate?.outcome, 'infeasible')
    assert.strictEqual(controller.getState().sourceRevision, 3)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    passTest('Case H5: Infeasible run preserves accepted design while updating revision and freshness')
  }

  // ---------------------------------------------------------------------------
  // Case H6: Obsolete context request finishing after reconciliation cannot replace newer authoritative state
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseH6')
    controller.activate('proj_caseH6')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseH6', revision: 1 }, revision: 1 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    const defStaleCtx = createDeferredPromise<any>()
    const pStaleCtx = controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: () => defStaleCtx.promise,
    })

    await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_h6', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_caseH6',
          revision: 5,
          processing: { elia_engine: { status: 'completed', run_id: 'run_h6', source_revision: 1 } },
        },
        revision: 5,
      }),
    })

    assert.strictEqual(controller.getState().sourceRevision, 5)
    assert.strictEqual(controller.getState().contextFreshness, 'current')

    defStaleCtx.resolve({
      master_json: { id: 'proj_caseH6', revision: 1 },
      revision: 1,
    })

    const staleRes = await pStaleCtx
    assert.strictEqual(staleRes.status, 'obsolete')
    assert.strictEqual(controller.getState().sourceRevision, 5)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    passTest('Case H6: Obsolete context request finishing after reconciliation cannot replace newer authoritative state')
  }

  // ---------------------------------------------------------------------------
  // Case H7: HTTP 409 conflict preserves requirements form while reporting conflict
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_caseH7')
    controller.activate('proj_caseH7')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_caseH7', revision: 1 }, revision: 1 }),
    })

    controller.editRequirement({ garageRequired: true, garageCapacity: 2 })

    let contextRefreshed = false
    const api409: EliaApiInterface = {
      ...noopApi,
      run: async () => {
        const err: any = new Error('Stale revision conflict')
        err.response = {
          status: 409,
          data: { code: 'ELIA_STALE_REVISION', current_revision: 3, detail: { code: 'ELIA_STALE_REVISION' } },
        }
        throw err
      },
      getContext: async () => {
        contextRefreshed = true
        return { master_json: { id: 'proj_caseH7', revision: 3 }, revision: 3 }
      },
    }

    const res = await controller.generateAndSave(api409)
    assert.strictEqual(res.status, 'failed')
    // Requirements form was PRESERVED!
    assert.strictEqual(controller.getState().formState.garageRequired, true)
    assert.strictEqual(controller.getState().formState.garageCapacity, 2)
    assert.ok(controller.getState().conflictError?.includes('Revision Conflict (409)'))
    passTest('Case H7: HTTP 409 conflict preserves requirements form and notifies conflict')
  }

  // ===========================================================================
  // GROUP 4: STRICT NUMBER & FORM VALIDATION CHECKS (Case H)
  // ===========================================================================
  {
    assert.strictEqual(parseStrictInteger(2).valid, true)
    assert.strictEqual(parseStrictInteger(2).value, 2)
    assert.strictEqual(parseStrictInteger('2').valid, true)
    assert.strictEqual(parseStrictInteger('2').value, 2)
    assert.strictEqual(parseStrictInteger(0).valid, true)
    assert.strictEqual(parseStrictInteger(0).value, 0)
    assert.strictEqual(parseStrictInteger('0').valid, true)
    assert.strictEqual(parseStrictInteger('0').value, 0)
    assert.strictEqual(parseStrictInteger('2.5').valid, false)
    assert.strictEqual(parseStrictInteger(2.5).valid, false)
    assert.strictEqual(parseStrictInteger('2abc').valid, false)
    assert.strictEqual(parseStrictInteger('Infinity').valid, false)
    assert.strictEqual(parseStrictInteger(Infinity).valid, false)
    assert.strictEqual(parseStrictInteger(NaN).valid, false)

    assert.strictEqual(parseStrictFloat('3.6').valid, true)
    assert.strictEqual(parseStrictFloat('3.6').value, 3.6)
    assert.strictEqual(parseStrictFloat(3.6).valid, true)
    assert.strictEqual(parseStrictFloat(3.6).value, 3.6)
    assert.strictEqual(parseStrictFloat('0').valid, true)
    assert.strictEqual(parseStrictFloat('0').value, 0)
    assert.strictEqual(parseStrictFloat('3.6xyz').valid, false)
    assert.strictEqual(parseStrictFloat('Infinity').valid, false)
    assert.strictEqual(parseStrictFloat(Infinity).valid, false)

    const defaultForm = createDefaultFormState()
    assert.strictEqual(validateRequirementsForm(defaultForm).valid, true)

    const invalidFractional = validateRequirementsForm({ ...defaultForm, garageRequired: true, vehicleCount: 1.5 })
    assert.strictEqual(invalidFractional.valid, false)
    assert.ok(invalidFractional.errors.vehicleCount?.includes('integer'))

    const invalidGate = validateRequirementsForm({ ...defaultForm, gateWidthM: 'Infinity' })
    assert.strictEqual(invalidGate.valid, false)
    assert.ok(invalidGate.errors.gateWidthM?.includes('valid number'))

    const invalidRatio = validateRequirementsForm({ ...defaultForm, openSpaceRatio: 1.5 })
    assert.strictEqual(invalidRatio.valid, false)
    assert.ok(invalidRatio.errors.openSpaceRatio?.includes('at most 1'))

    passTest('Fractional counts, non-finite values, and malformed numeric strings are strictly rejected')
  }

  // ===========================================================================
  // GROUP 5: STAGE 3 CONFIRMED DEFECTS REGRESSION COVERAGE (Cases A - J)
  // ===========================================================================

  // ---------------------------------------------------------------------------
  // Case A: Correctly correlated infeasible outcome with successful refresh
  // processing.status = "infeasible" + latestResult.status = "completed"
  // Clears reconciliation and preserves prior accepted exterior
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_A')
    controller.activate('proj_reg_A')

    const priorAccepted = {
      run_id: 'run_prior_accepted_a',
      access: { gate: null, garage: null, driveway: null },
    }

    // Load initial valid accepted context
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_A',
          revision: 1,
          exterior_landscape: priorAccepted,
        },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_prior_accepted_a')
    assert.strictEqual(controller.getState().sourceRevision, 1)

    // Trigger ambiguous mutation failure at source revision 1
    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Gateway Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().unresolvedMutation?.sourceRevision, 1)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.strictEqual(controller.canExportMasterJson(), false)

    // Reconcile: backend ComponentRun has status "completed", while processing in Master JSON has status "infeasible"
    const apiInfeasibleCorrelated: EliaApiInterface = {
      ...noopApi,
      getResult: async () => ({
        run_id: 'run_infeasible_a',
        status: 'completed', // ComponentRun is "completed"
        output: {
          run_id: 'run_infeasible_a',
          access: { gate: null },
          validation_summary: { valid: false, violations: ['Boundary setback violation'] },
          outcome: 'infeasible',
        },
      } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_A',
          revision: 2,
          // Master JSON preserves prior accepted exterior when outcome is infeasible!
          exterior_landscape: priorAccepted,
          processing: {
            elia_engine: {
              status: 'infeasible', // Master JSON processing status is "infeasible"
              outcome: 'infeasible',
              run_id: 'run_infeasible_a',
              source_revision: 1, // Correlates to unresolved mutation revision 1!
            },
          },
        },
        revision: 2,
      }),
    }

    const reconRes = await controller.reconcileMutation(apiInfeasibleCorrelated)
    assert.strictEqual(reconRes.status, 'reconciled')
    // Reconciliation guard must be cleared!
    assert.strictEqual(controller.getState().requiresReconciliation, false)
    assert.strictEqual(controller.getState().unresolvedMutation, null)
    // Prior accepted design must be preserved!
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_prior_accepted_a')
    assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_prior_accepted_a')
    // Candidate contains the infeasible candidate run and was NOT promoted to acceptedLandscape
    assert.strictEqual(controller.getState().candidate?.outcome, 'infeasible')
    assert.strictEqual(controller.getState().candidate?.runId, 'run_infeasible_a')
    // UI is truthful and operational
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.canGenerateAndSave(), true)
    assert.strictEqual(controller.canExportMasterJson(), true)
    assert.ok(controller.getState().actionError?.includes('Infeasible Run'))
    assert.ok(controller.getState().actionError?.includes('Previously accepted design preserved'))
    passTest('Regression A: Correlated processing=infeasible + latestResult=completed with successful refresh clears guard and preserves prior accepted exterior')
  }

  // ---------------------------------------------------------------------------
  // Case B: Same infeasible outcome with failed or malformed authoritative refresh
  // Reconciliation, Save, and Export remain blocked
  // ---------------------------------------------------------------------------
  {
    // B1: Transport failure during authoritative refresh
    const controllerB1 = new EliaWorkflowController('proj_reg_B1')
    controllerB1.activate('proj_reg_B1')
    const priorAccepted = { run_id: 'run_prior_b1', access: { gate: null } }

    await controllerB1.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_B1', revision: 1, exterior_landscape: priorAccepted },
        revision: 1,
      }),
    })

    await controllerB1.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })
    assert.strictEqual(controllerB1.getState().requiresReconciliation, true)

    let getCtxCallsB1 = 0
    const resB1 = await controllerB1.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_inf_b1', status: 'completed' } as any),
      getContext: async () => {
        getCtxCallsB1++
        if (getCtxCallsB1 === 1) {
          // Reconciliation query returns valid doc showing correlated infeasible run
          return {
            master_json: {
              id: 'proj_reg_B1',
              revision: 2,
              exterior_landscape: priorAccepted,
              processing: { elia_engine: { status: 'infeasible', run_id: 'run_inf_b1', source_revision: 1 } },
            },
            revision: 2,
          }
        }
        // Owned authoritative context refresh fails!
        throw new Error('503 Service Unavailable')
      },
    })

    assert.strictEqual(resB1.status, 'failed')
    assert.strictEqual(controllerB1.getState().requiresReconciliation, true)
    assert.strictEqual(controllerB1.getState().contextFreshness, 'stale')
    assert.strictEqual(controllerB1.canGenerateAndSave(), false)
    assert.strictEqual(controllerB1.canExportMasterJson(), false)

    // B2: Malformed exterior in authoritative refresh response
    const controllerB2 = new EliaWorkflowController('proj_reg_B2')
    controllerB2.activate('proj_reg_B2')

    await controllerB2.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_B2', revision: 1, exterior_landscape: priorAccepted },
        revision: 1,
      }),
    })

    await controllerB2.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })

    let getCtxCallsB2 = 0
    const resB2 = await controllerB2.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_inf_b2', status: 'completed' } as any),
      getContext: async () => {
        getCtxCallsB2++
        if (getCtxCallsB2 === 1) {
          return {
            master_json: {
              id: 'proj_reg_B2',
              revision: 2,
              exterior_landscape: priorAccepted,
              processing: { elia_engine: { status: 'infeasible', run_id: 'run_inf_b2', source_revision: 1 } },
            },
            revision: 2,
          }
        }
        // Authoritative context returns malformed exterior
        return {
          master_json: {
            id: 'proj_reg_B2',
            revision: 2,
            exterior_landscape: 'corrupted_string_value', // Malformed!
          },
          revision: 2,
        }
      },
    })

    assert.strictEqual(resB2.status, 'failed')
    assert.strictEqual(controllerB2.getState().requiresReconciliation, true)
    assert.strictEqual(controllerB2.getState().contextFreshness, 'stale')
    // Prior accepted design must still be preserved!
    assert.strictEqual(controllerB2.getState().acceptedLandscape?.run_id, 'run_prior_b1')
    assert.strictEqual(controllerB2.canGenerateAndSave(), false)
    assert.strictEqual(controllerB2.canExportMasterJson(), false)
    passTest('Regression B: Infeasible outcome with failed or malformed refresh leaves reconciliation, Save, and Export blocked')
  }

  // ---------------------------------------------------------------------------
  // Case C: Genuinely incompatible statuses remain unresolved
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_C')
    controller.activate('proj_reg_C')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_reg_C', revision: 1 }, revision: 1 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })

    // Incompatible 1: processing=failed vs latestRun=completed
    const res1 = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_incompat_1', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_C',
          revision: 2,
          processing: { elia_engine: { status: 'failed', run_id: 'run_incompat_1', source_revision: 1 } },
        },
        revision: 2,
      }),
    })
    assert.strictEqual(res1.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.ok(controller.getState().actionError?.includes('Contradictory'))

    // Incompatible 2: processing=completed vs latestRun=failed
    const res2 = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_incompat_2', status: 'failed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_C',
          revision: 2,
          processing: { elia_engine: { status: 'completed', run_id: 'run_incompat_2', source_revision: 1 } },
        },
        revision: 2,
      }),
    })
    assert.strictEqual(res2.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    // Incompatible 3: processing=completed (valid) vs latestRun=infeasible
    const res3 = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_incompat_3', status: 'infeasible' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_C',
          revision: 2,
          processing: { elia_engine: { status: 'completed', outcome: 'valid', run_id: 'run_incompat_3', source_revision: 1 } },
        },
        revision: 2,
      }),
    })
    assert.strictEqual(res3.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    passTest('Regression C: Genuinely incompatible statuses remain unresolved and guarded')
  }

  // ---------------------------------------------------------------------------
  // Case D: Same status pair belonging to an unrelated newer or older run
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_D')
    controller.activate('proj_reg_D')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_reg_D', revision: 2 }, revision: 2 }),
    })

    // Unresolved mutation at source revision 2
    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })

    // Subcase D1: Backend returns status pair (processing=infeasible, latestResult=completed),
    // but source_revision is 4 (newer than target revision 2)!
    const resNewer = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_inf_newer', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_D',
          revision: 5,
          processing: { elia_engine: { status: 'infeasible', run_id: 'run_inf_newer', source_revision: 4 } },
        },
        revision: 5,
      }),
    })
    assert.strictEqual(resNewer.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)

    // Subcase D2: Backend returns status pair for an older run (source_revision: 1 < 2)
    const resOlder = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_inf_older', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_D',
          revision: 2,
          processing: { elia_engine: { status: 'infeasible', run_id: 'run_inf_older', source_revision: 1 } },
        },
        revision: 2,
      }),
    })
    assert.strictEqual(resOlder.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    passTest('Regression D: Status pair from unrelated newer or older run does not unlock uncertain mutation')
  }

  // ---------------------------------------------------------------------------
  // Case E: Missing, unknown, or nonterminal status evidence
  // Must not falsely become a completed accepted design
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_E')
    controller.activate('proj_reg_E')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_reg_E', revision: 1 }, revision: 1 }),
    })

    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        const err: any = new Error('Timeout')
        err.code = 'ETIMEDOUT'
        throw err
      },
    })

    // Subcase E1: Unknown status string
    const resUnknown = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_unk_status', status: 'unrecognized_status' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_E',
          revision: 2,
          processing: { elia_engine: { status: 'completed', run_id: 'run_unk_status', source_revision: 1 } },
        },
        revision: 2,
      }),
    })
    assert.strictEqual(resUnknown.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().acceptedLandscape, null)

    // Subcase E2: Missing processing status in Master JSON (status is null)
    const resMissingProc = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_missing_proc', status: 'completed' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_E',
          revision: 2,
          processing: { elia_engine: { run_id: 'run_missing_proc', source_revision: 1 } }, // status omitted!
        },
        revision: 2,
      }),
    })
    assert.strictEqual(resMissingProc.status, 'unresolved')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().acceptedLandscape, null)

    // Subcase E3: Nonterminal status ('processing')
    const resProcessing = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({ run_id: 'run_nonterm', status: 'processing' } as any),
      getContext: async () => ({
        master_json: {
          id: 'proj_reg_E',
          revision: 1,
          processing: { elia_engine: { status: 'processing', run_id: 'run_nonterm', source_revision: 1 } },
        },
        revision: 1,
      }),
    })
    assert.strictEqual(resProcessing.status, 'processing')
    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    passTest('Regression E: Missing, unknown, or nonterminal status evidence does not falsely become accepted design')
  }

  // ---------------------------------------------------------------------------
  // Case F: Valid authoritative absence clears accepted exterior and provenance together
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_F')
    controller.activate('proj_reg_F')

    // 1. Initial context has valid accepted exterior
    const initialExt = { run_id: 'run_f_init', access: { gate: null } }
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_F', revision: 1, exterior_landscape: initialExt },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_f_init')
    assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_f_init')

    // 2. Authoritative context response has explicit null exterior_landscape
    const resNull = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_F', revision: 2, exterior_landscape: null },
        revision: 2,
      }),
    })
    assert.strictEqual(resNull.status, 'success')
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.getState().acceptedProvenance, null)
    assert.strictEqual(controller.getState().contextFreshness, 'current')

    // 3. Re-set valid exterior, then test key omitted entirely
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_F', revision: 3, exterior_landscape: initialExt },
        revision: 3,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_f_init')

    const resOmitted = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_F', revision: 4 }, // exterior_landscape property omitted!
        revision: 4,
      }),
    })
    assert.strictEqual(resOmitted.status, 'success')
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.getState().acceptedProvenance, null)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    passTest('Regression F: Valid authoritative absence (null or omitted) clears accepted exterior and provenance together')
  }

  // ---------------------------------------------------------------------------
  // Case G: Malformed exterior values: representative primitives, arrays, bad structures
  // Preserves prior valid snapshot/design/provenance, returns failure, stale state, blocked save/export
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_G')
    controller.activate('proj_reg_G')

    const validKnownExterior = { run_id: 'run_valid_g', access: { gate: null } }
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_G', revision: 1, exterior_landscape: validKnownExterior },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_valid_g')
    assert.strictEqual(controller.getState().sourceRevision, 1)
    assert.strictEqual(controller.getState().contextFreshness, 'current')

    const malformedSamples: Array<{ label: string; payload: any }> = [
      { label: 'primitive string', payload: 'corrupted_string' },
      { label: 'primitive number', payload: 12345 },
      { label: 'primitive boolean', payload: true },
      { label: 'array', payload: [{ run_id: 'run_arr' }] },
      { label: 'empty object', payload: {} },
      { label: 'empty run_id string', payload: { run_id: '  ', access: {} } },
      { label: 'missing access object', payload: { run_id: 'run_no_acc' } },
      { label: 'primitive access property', payload: { run_id: 'run_bad_acc', access: 'main_gate' } },
      { label: 'malformed access.gate (primitive)', payload: { run_id: 'run_bad_gate', access: { gate: 999 } } },
      { label: 'malformed access.garage (primitive)', payload: { run_id: 'run_bad_garage', access: { garage: 'standard' } } },
      { label: 'malformed vegetation_nodes (not array)', payload: { run_id: 'run_bad_veg', access: {}, vegetation_nodes: 'dense' } },
      { label: 'malformed outdoor_elements (not array)', payload: { run_id: 'run_bad_elem', access: {}, outdoor_elements: 42 } },
      { label: 'malformed vertical_greenery (primitive)', payload: { run_id: 'run_bad_vg', access: {}, vertical_greenery: 'none' } },
      { label: 'malformed outdoor_lighting (primitive)', payload: { run_id: 'run_bad_ol', access: {}, outdoor_lighting: 10 } },
      { label: 'malformed validation_summary (primitive)', payload: { run_id: 'run_bad_val', access: {}, validation_summary: 'passed' } },
    ]

    for (const sample of malformedSamples) {
      const res = await controller.loadAuthoritativeContext({
        ...noopApi,
        getContext: async () => ({
          master_json: { id: 'proj_reg_G', revision: 2, exterior_landscape: sample.payload },
          revision: 2,
        }),
      })

      assert.strictEqual(res.status, 'failed', `Sample '${sample.label}' should return failed context refresh`)
      // Prior known good snapshot, revision, accepted exterior, and provenance MUST be preserved!
      assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_valid_g')
      assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_valid_g')
      assert.strictEqual(controller.getState().sourceRevision, 1)
      assert.strictEqual(controller.getState().contextFreshness, 'stale')
      assert.ok(controller.getState().contextError !== null, `Sample '${sample.label}' must have actionable contextError`)
      assert.strictEqual(controller.canExportMasterJson(), false)
      assert.strictEqual(controller.canGenerateAndSave(), false)
    }
    passTest('Regression G: Representative malformed exterior values fail cleanly and preserve prior valid state')
  }

  // ---------------------------------------------------------------------------
  // Case H: Malformed exterior when no valid context has ever loaded
  // Context remains unavailable and actions remain blocked
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_H')
    controller.activate('proj_reg_H')
    assert.strictEqual(controller.getState().contextFreshness, 'loading')

    const res = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_H', revision: 1, exterior_landscape: 'corrupted_first_load' },
        revision: 1,
      }),
    })

    assert.strictEqual(res.status, 'failed')
    assert.strictEqual(controller.getState().contextFreshness, 'unavailable')
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.getState().acceptedProvenance, null)
    assert.strictEqual(controller.getState().authoritativeMaster, null)
    assert.strictEqual(controller.canExportMasterJson(), false)
    assert.strictEqual(controller.canGenerateAndSave(), false)
    assert.ok(controller.getState().contextError?.includes('Malformed exterior_landscape'))
    passTest('Regression H: Malformed exterior when no valid context has ever loaded leaves context unavailable and actions blocked')
  }

  // ---------------------------------------------------------------------------
  // Case I: Recovery: Subsequent valid refresh restores appropriate state and eligibility
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_reg_I')
    controller.activate('proj_reg_I')

    // 1. First attempt fails due to malformed exterior
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_I', revision: 1, exterior_landscape: { invalid: true } },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().contextFreshness, 'unavailable')
    assert.strictEqual(controller.canGenerateAndSave(), false)

    // 2. Subsequent valid refresh
    const validExterior = { run_id: 'run_recovered_i', access: { gate: null } }
    const resRecover = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_reg_I', revision: 2, exterior_landscape: validExterior },
        revision: 2,
      }),
    })

    assert.strictEqual(resRecover.status, 'success')
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.getState().contextError, null)
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_recovered_i')
    assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_recovered_i')
    assert.strictEqual(controller.getState().sourceRevision, 2)
    assert.strictEqual(controller.canGenerateAndSave(), true)
    assert.strictEqual(controller.canExportMasterJson(), true)
    passTest('Regression I: Subsequent valid refresh completely restores state and eligibility without obsolete errors')
  }

  // ---------------------------------------------------------------------------
  // Case J: Lifecycle races: Late failed/malformed response from old project/session
  // Must not affect current project mutation guard or accepted state
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_old_race')
    controller.activate('proj_old_race')

    // Start a pending context load on proj_old_race
    const defOld = createDeferredPromise<any>()
    const pOld = controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: () => defOld.promise,
    })

    // Switch project to proj_new_race
    controller.activate('proj_new_race')
    const newValidExterior = { run_id: 'run_new_j', access: { gate: null } }
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_new_race', revision: 1, exterior_landscape: newValidExterior },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().projectId, 'proj_new_race')
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_new_j')
    assert.strictEqual(controller.getState().contextFreshness, 'current')

    // Late old response resolves with malformed exterior!
    defOld.resolve({
      master_json: { id: 'proj_old_race', revision: 1, exterior_landscape: 'malformed_old' },
      revision: 1,
    })
    const resOld = await pOld
    assert.strictEqual(resOld.status, 'obsolete')

    // New project must be completely unaffected!
    assert.strictEqual(controller.getState().projectId, 'proj_new_race')
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_new_j')
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.getState().contextError, null)
    assert.strictEqual(controller.canGenerateAndSave(), true)
    assert.strictEqual(controller.canExportMasterJson(), true)
    passTest('Regression J: Late malformed response from old project does not affect current project state or eligibility')
  }

  // ===========================================================================
  // GROUP 5: CONFIRMED DEFECT FIXES & DIRECT REGRESSIONS
  // ===========================================================================

  // ---------------------------------------------------------------------------
  // 47. Defect 1.1: violations as a string rejected without join/map exceptions
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_viol_str')
    controller.activate('proj_viol_str')

    // Context refresh with string violations is rejected
    const badExterior = {
      run_id: 'run_bad_str',
      access: {},
      validation_summary: {
        valid: false,
        violations: 'broken',
      },
    }

    const resCtx = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_viol_str', revision: 1, exterior_landscape: badExterior },
        revision: 1,
      }),
    })
    assert.strictEqual(resCtx.status, 'failed')
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.getState().contextFreshness, 'unavailable')
    assert.ok(controller.getState().contextError?.includes('validation_summary.violations'))

    // Initial valid context
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_viol_str', revision: 1 },
        revision: 1,
      }),
    })

    // Preview returning string violations is rejected without throwing join/map exceptions
    const resPrev = await controller.previewCandidate({
      ...noopApi,
      preview: async () => ({
        run_id: 'prev_str_viol',
        outcome: 'infeasible',
        exterior_landscape: badExterior as any,
      }),
    })
    assert.strictEqual(resPrev.status, 'failed')
    assert.strictEqual(controller.getState().candidate, null)
    assert.ok(controller.getState().actionError?.includes('validation_summary.violations'))

    passTest('Defect 1.1: violations as a string rejected without join/map exceptions')
  }

  // ---------------------------------------------------------------------------
  // 48. Defect 1.2: violations containing non-string entries rejected according to contract
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_viol_arr')
    controller.activate('proj_viol_arr')

    const exteriorNonStringEntries = {
      run_id: 'run_non_str',
      access: {},
      validation_summary: {
        valid: false,
        violations: ['Valid setback violation', 404, { detail: 'nested object' }],
      },
    }

    const resCtx = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_viol_arr', revision: 1, exterior_landscape: exteriorNonStringEntries },
        revision: 1,
      }),
    })
    assert.strictEqual(resCtx.status, 'failed')
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.ok(controller.getState().contextError?.includes('validation_summary.violations'))

    // Initial valid context
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_viol_arr', revision: 1 },
        revision: 1,
      }),
    })

    const resPrev = await controller.previewCandidate({
      ...noopApi,
      preview: async () => ({
        run_id: 'prev_non_str',
        outcome: 'infeasible',
        exterior_landscape: exteriorNonStringEntries as any,
      }),
    })
    assert.strictEqual(resPrev.status, 'failed')
    assert.strictEqual(controller.getState().candidate, null)
    assert.ok(controller.getState().actionError?.includes('validation_summary.violations'))

    passTest('Defect 1.2: violations containing non-string entries rejected according to contract')
  }

  // ---------------------------------------------------------------------------
  // 49. Defect 1.3: Malformed nested feature collections/entries rejected before accepted or candidate state update
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_nested_feat')
    controller.activate('proj_nested_feat')

    const malformedFeatureSamples = [
      {
        name: 'non-object entry in vegetation_nodes',
        ext: { run_id: 'f1', access: {}, vegetation_nodes: ['tree_primitive'] },
      },
      {
        name: 'vegetation_node with empty json_id',
        ext: { run_id: 'f2', access: {}, vegetation_nodes: [{ json_id: '   ' }] },
      },
      {
        name: 'vegetation_node with non-finite position coordinates',
        ext: { run_id: 'f3', access: {}, vegetation_nodes: [{ json_id: 'tree_1', position: [NaN, 10] }] },
      },
      {
        name: 'gate with non-positive dimensions',
        ext: { run_id: 'f4', access: { gate: { json_id: 'gate_1', dimensions: { width_m: -1 } } } },
      },
      {
        name: 'gate in gates array with invalid units',
        ext: { run_id: 'f5', access: { gates: [{ json_id: 'gate_2', units: 'feet' }] } },
      },
      {
        name: 'vertical_greenery element with non-finite height_m',
        ext: { run_id: 'f6', access: {}, vertical_greenery: { elements: [{ json_id: 'vg_1', height_m: Infinity }] } },
      },
      {
        name: 'outdoor_lighting node missing json_id',
        ext: { run_id: 'f7', access: {}, outdoor_lighting: { nodes: [{ type: 'lamp' }] } },
      },
    ]

    for (const sample of malformedFeatureSamples) {
      const resCtx = await controller.loadAuthoritativeContext({
        ...noopApi,
        getContext: async () => ({
          master_json: { id: 'proj_nested_feat', revision: 1, exterior_landscape: sample.ext },
          revision: 1,
        }),
      })
      assert.strictEqual(resCtx.status, 'failed', `Sample '${sample.name}' must fail authoritative context load`)
      assert.strictEqual(controller.getState().acceptedLandscape, null)
      assert.strictEqual(controller.getState().candidate, null)
    }

    passTest('Defect 1.3: Malformed nested feature collections/entries rejected before accepted or candidate state update')
  }

  // ---------------------------------------------------------------------------
  // 50. Defect 1.4: Malformed authoritative refresh after valid accepted design preserves previous snapshot, revision, and provenance
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_refresh_preserve')
    controller.activate('proj_refresh_preserve')

    const snapshotA = { id: 'proj_refresh_preserve', revision: 1, site: 'survey_A' }
    const validExteriorA = { run_id: 'run_init_valid', access: { gate: { json_id: 'g_init' } } }

    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { ...snapshotA, exterior_landscape: validExteriorA },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_init_valid')
    assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_init_valid')
    assert.strictEqual(controller.getState().acceptedProvenance?.sourceRevision, 1)
    assert.strictEqual((controller.getState().acceptedProvenance?.sourceSnapshot as any)?.site, 'survey_A')
    assert.strictEqual(controller.getState().sourceRevision, 1)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.canExportMasterJson(), true)
    assert.strictEqual(controller.canGenerateAndSave(), true)

    // Second context refresh contains a malformed exterior payload
    const malformedExterior = {
      run_id: 'run_corrupted',
      access: {},
      validation_summary: { valid: false, violations: 'corrupted_string' },
    }

    const resMalformed = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_refresh_preserve', revision: 2, exterior_landscape: malformedExterior },
        revision: 2,
      }),
    })

    assert.strictEqual(resMalformed.status, 'failed')
    // Prior valid snapshot, revision, accepted exterior, and provenance MUST be preserved!
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_init_valid')
    assert.strictEqual(controller.getState().acceptedProvenance?.runId, 'run_init_valid')
    assert.strictEqual(controller.getState().acceptedProvenance?.sourceRevision, 1)
    assert.strictEqual((controller.getState().acceptedProvenance?.sourceSnapshot as any)?.site, 'survey_A')
    assert.strictEqual(controller.getState().sourceRevision, 1)
    assert.strictEqual((controller.getState().authoritativeMaster as any)?.site, 'survey_A')

    // Marked stale and appropriate actions strictly blocked
    assert.strictEqual(controller.getState().contextFreshness, 'stale')
    assert.ok(controller.getState().contextError !== null)
    assert.strictEqual(controller.canExportMasterJson(), false)
    assert.strictEqual(controller.canGenerateAndSave(), false)

    passTest('Defect 1.4: Malformed authoritative refresh after valid accepted design preserves previous snapshot, revision, and provenance')
  }

  // ---------------------------------------------------------------------------
  // 51. Defect 1.5: Malformed initial context remains unavailable and keeps actions blocked
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_init_bad')
    controller.activate('proj_init_bad')
    assert.strictEqual(controller.getState().contextFreshness, 'loading')

    const resInit = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: {
          id: 'proj_init_bad',
          revision: 1,
          exterior_landscape: {
            run_id: 'run_bad_first',
            access: { gate: { json_id: 'g1', units: 'ft' } },
          },
        },
        revision: 1,
      }),
    })

    assert.strictEqual(resInit.status, 'failed')
    assert.strictEqual(controller.getState().contextFreshness, 'unavailable')
    assert.strictEqual(controller.getState().acceptedLandscape, null)
    assert.strictEqual(controller.getState().acceptedProvenance, null)
    assert.strictEqual(controller.getState().authoritativeMaster, null)
    assert.strictEqual(controller.getState().sourceRevision, null)
    assert.strictEqual(controller.canExportMasterJson(), false)
    assert.strictEqual(controller.canGenerateAndSave(), false)

    passTest('Defect 1.5: Malformed initial context remains unavailable and keeps actions blocked')
  }

  // ---------------------------------------------------------------------------
  // 52. Defect 1.6 & 2: Malformed reconciliation candidate output avoids exceptions and prevents invalid publication without blocking mutation resolution
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_recon_cand_malformed')
    controller.activate('proj_recon_cand_malformed')

    // Initial valid context at revision 1
    const snapshotA = { id: 'proj_recon_cand_malformed', revision: 1, site: 'v1_site' }
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: snapshotA,
        revision: 1,
      }),
    })

    // Simulate an ambiguous network save failure that creates an unresolved mutation
    const runCall = controller.generateAndSave({
      ...noopApi,
      run: async () => {
        throw new Error('Ambiguous 500 Network Timeout')
      },
    })
    await runCall

    assert.strictEqual(controller.getState().requiresReconciliation, true)
    assert.strictEqual(controller.getState().unresolvedMutation?.sourceRevision, 1)

    // Reconcile:
    // backend finished the terminal infeasible run 'run_corr',
    // but candidate output in run history has corrupted string violations
    const malformedOutput = {
      run_id: 'run_corr',
      access: {},
      validation_summary: {
        valid: false,
        violations: 'corrupted_string_violations',
      },
    }

    const resRecon = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({
        run_id: 'run_corr',
        status: 'completed',
        output: malformedOutput as any,
      }),
      getContext: async () => ({
        master_json: {
          id: 'proj_recon_cand_malformed',
          revision: 2,
          processing: {
            elia_engine: {
              status: 'infeasible',
              run_id: 'run_corr',
              source_revision: 1,
            },
          },
        },
        revision: 2,
      }),
    })

    // Must resolve cleanly without exceptions!
    assert.strictEqual(resRecon.status, 'reconciled')
    // Malformed candidate output must NOT be published
    assert.strictEqual(controller.getState().candidate, null)
    // Mutation is proven terminal; guard is unlocked and context is current!
    assert.strictEqual(controller.getState().requiresReconciliation, false)
    assert.strictEqual(controller.getState().unresolvedMutation, null)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.getState().sourceRevision, 2)
    assert.strictEqual(controller.canGenerateAndSave(), true)

    passTest('Defect 1.6 & 2: Malformed reconciliation candidate output avoids exceptions and prevents invalid publication without blocking mutation resolution')
  }

  // ---------------------------------------------------------------------------
  // 53. Defect 2.7: Valid correlated infeasible reconciliation preserves accepted design and sets candidate
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_recon_inf')
    controller.activate('proj_recon_inf')

    const priorAccepted = { run_id: 'prior_acc_design', access: { gate: { json_id: 'gate_acc' } } }
    const snapshotA = { id: 'proj_recon_inf', revision: 1, site: 'context_snap_A' }

    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { ...snapshotA, exterior_landscape: priorAccepted },
        revision: 1,
      }),
    })
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'prior_acc_design')

    // Ambiguous save failure
    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        throw new Error('ETIMEDOUT')
      },
    })
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    // Reconcile with valid correlated infeasible run
    const candidateOutput = {
      run_id: 'run_corr_inf',
      access: {},
      validation_summary: {
        valid: false,
        violations: ['Boundary setback violation'],
      },
    }

    const resRecon = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({
        run_id: 'run_corr_inf',
        status: 'completed',
        output: candidateOutput as any,
      }),
      getContext: async () => ({
        master_json: {
          id: 'proj_recon_inf',
          revision: 2,
          site: 'context_snap_B',
          exterior_landscape: priorAccepted,
          processing: {
            elia_engine: {
              status: 'infeasible',
              run_id: 'run_corr_inf',
              source_revision: 1,
            },
          },
        },
        revision: 2,
      }),
    })

    assert.strictEqual(resRecon.status, 'reconciled')
    // Accepted design preserved
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'prior_acc_design')
    // Candidate set and correctly marked infeasible
    assert.strictEqual(controller.getState().candidate?.outcome, 'infeasible')
    assert.strictEqual(controller.getState().candidate?.runId, 'run_corr_inf')
    // Candidate retains submitted snapshot A and submitted revision 1!
    assert.strictEqual(controller.getState().candidate?.sourceRevision, 1)
    assert.strictEqual((controller.getState().candidate?.sourceSnapshot as any)?.site, 'context_snap_A')
    // Authoritative context reflects B
    assert.strictEqual((controller.getState().authoritativeMaster as any)?.site, 'context_snap_B')
    assert.strictEqual(controller.getState().sourceRevision, 2)
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.canGenerateAndSave(), true)

    passTest('Defect 2.7: Valid correlated infeasible reconciliation preserves accepted design and sets candidate')
  }

  // ---------------------------------------------------------------------------
  // 54. Defect 2.8: Snapshot provenance retains submitted snapshot A and revision N while authoritative state reflects B
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_prov_separation')
    controller.activate('proj_prov_separation')

    const snapshotA = { id: 'proj_prov_separation', revision: 5, land_geometry: 'v5_geometry' }
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: snapshotA,
        revision: 5,
      }),
    })

    // Submit mutation at revision 5
    await controller.generateAndSave({
      ...noopApi,
      run: async () => {
        throw new Error('Connection reset')
      },
    })
    assert.strictEqual(controller.getState().unresolvedMutation?.sourceRevision, 5)

    // Later authoritative context B has advanced to revision 8
    const snapshotB = {
      id: 'proj_prov_separation',
      revision: 8,
      land_geometry: 'v8_geometry_modified',
      processing: {
        elia_engine: {
          status: 'infeasible',
          run_id: 'run_rev5_correlated',
          source_revision: 5,
        },
      },
    }

    const resRecon = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({
        run_id: 'run_rev5_correlated',
        status: 'completed',
        output: {
          run_id: 'run_rev5_correlated',
          access: {},
          validation_summary: { valid: false, violations: ['Garage exceeds setback'] },
        } as any,
      }),
      getContext: async () => ({
        master_json: snapshotB,
        revision: 8,
      }),
    })

    assert.strictEqual(resRecon.status, 'reconciled')
    // Candidate strictly pairs with submitted snapshot A and revision 5!
    const cand = controller.getState().candidate
    assert.ok(cand !== null)
    assert.strictEqual(cand.sourceRevision, 5)
    assert.strictEqual((cand.sourceSnapshot as any)?.land_geometry, 'v5_geometry')
    assert.notStrictEqual((cand.sourceSnapshot as any)?.land_geometry, 'v8_geometry_modified')

    // Authoritative state strictly reflects B and revision 8!
    assert.strictEqual(controller.getState().sourceRevision, 8)
    assert.strictEqual((controller.getState().authoritativeMaster as any)?.land_geometry, 'v8_geometry_modified')

    passTest('Defect 2.8: Snapshot provenance retains submitted snapshot A and revision N while authoritative state reflects B')
  }

  // ---------------------------------------------------------------------------
  // 55. Defect 2.9: Missing submitted snapshot is not silently paired with current context while accepted view remains usable
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_missing_snapshot')
    controller.activate('proj_missing_snapshot')

    // Initial valid context with accepted design
    const acceptedExterior = { run_id: 'acc_usable', access: {} }
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_missing_snapshot', revision: 2, exterior_landscape: acceptedExterior },
        revision: 2,
      }),
    })

    // Directly simulate an unresolved mutation where snapshotAtSubmit is unavailable (null)
    (controller as any).setState({
      requiresReconciliation: true,
      unresolvedMutation: {
        projectId: 'proj_missing_snapshot',
        sourceRevision: 2,
        submittedFingerprint: 'fp_missing',
        submittedGenerationMode: 'baseline',
        snapshotAtSubmit: null, // UNAVAILABLE!
        submittedAt: new Date().toISOString(),
        status: 'unresolved',
      },
    })

    const laterDoc = {
      id: 'proj_missing_snapshot',
      revision: 3,
      site_name: 'Later Current Context C',
      exterior_landscape: acceptedExterior,
      processing: {
        elia_engine: {
          status: 'infeasible',
          run_id: 'run_nosnap',
          source_revision: 2,
        },
      },
    }

    const resRecon = await controller.reconcileMutation({
      ...noopApi,
      getResult: async () => ({
        run_id: 'run_nosnap',
        status: 'completed',
        output: {
          run_id: 'run_nosnap',
          access: {},
          validation_summary: { valid: false, violations: ['Driveway slope excessive'] },
        } as any,
      }),
      getContext: async () => ({
        master_json: laterDoc,
        revision: 3,
      }),
    })

    assert.strictEqual(resRecon.status, 'reconciled')
    // Candidate sourceSnapshot MUST be null (explicitly unavailable) — never substituted with laterDoc!
    const cand = controller.getState().candidate
    assert.ok(cand !== null)
    assert.strictEqual(cand.sourceSnapshot, null)
    assert.strictEqual(cand.sourceRevision, 2)

    // Accepted view remains usable and truthful
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'acc_usable')
    assert.strictEqual(controller.getState().sourceRevision, 3)
    assert.strictEqual((controller.getState().authoritativeMaster as any)?.site_name, 'Later Current Context C')
    assert.strictEqual(controller.canExportMasterJson(), true)

    passTest('Defect 2.9: Missing submitted snapshot is not silently paired with current context while accepted view remains usable')
  }

  // ---------------------------------------------------------------------------
  // 56. Defect 2.10: Project switch during reconciliation prevents old response from overwriting new project candidate or guard
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_switch_recon_A')
    controller.activate('proj_switch_recon_A')

    // Establish unresolved state on proj_switch_recon_A
    controller.setState({
      requiresReconciliation: true,
      unresolvedMutation: {
        projectId: 'proj_switch_recon_A',
        sourceRevision: 1,
        submittedFingerprint: 'fp_a',
        submittedGenerationMode: 'baseline',
        snapshotAtSubmit: { id: 'snap_A' },
        submittedAt: new Date().toISOString(),
        status: 'unresolved',
      },
    })

    // Start reconciliation on Project A with deferred promises
    const defGetResA = createDeferredPromise<any>()
    const defGetCtxA = createDeferredPromise<any>()

    const pReconA = controller.reconcileMutation({
      ...noopApi,
      getResult: () => defGetResA.promise,
      getContext: () => defGetCtxA.promise,
    })

    // User switches project to Project B!
    controller.activate('proj_switch_recon_B')
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: { id: 'proj_switch_recon_B', revision: 10, site: 'project_B_clean' },
        revision: 10,
      }),
    })

    assert.strictEqual(controller.getState().projectId, 'proj_switch_recon_B')
    assert.strictEqual(controller.getState().requiresReconciliation, false)
    assert.strictEqual(controller.getState().candidate, null)

    // Old Project A reconciliation finishes late with an infeasible candidate
    defGetResA.resolve({
      run_id: 'run_old_a',
      status: 'completed',
      output: { run_id: 'run_old_a', access: {}, validation_summary: { valid: false, violations: ['old A error'] } },
    })
    defGetCtxA.resolve({
      master_json: {
        id: 'proj_switch_recon_A',
        revision: 2,
        processing: { elia_engine: { status: 'infeasible', run_id: 'run_old_a', source_revision: 1 } },
      },
      revision: 2,
    })

    const resA = await pReconA
    assert.strictEqual(resA.status, 'obsolete')

    // Current Project B must be completely untainted!
    assert.strictEqual(controller.getState().projectId, 'proj_switch_recon_B')
    assert.strictEqual(controller.getState().candidate, null)
    assert.strictEqual(controller.getState().requiresReconciliation, false)
    assert.strictEqual(controller.getState().unresolvedMutation, null)
    assert.strictEqual(controller.getState().sourceRevision, 10)
    assert.strictEqual((controller.getState().authoritativeMaster as any)?.site, 'project_B_clean')

    passTest('Defect 2.10: Project switch during reconciliation prevents old response from overwriting new project candidate or guard')
  }

  // ---------------------------------------------------------------------------
  // 57. Defect 1.11: Subsequent valid response restores correct state without obsolete errors
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_recovery')
    controller.activate('proj_recovery')

    // 1. Initial attempt fails with malformed exterior
    const resBad = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: {
          id: 'proj_recovery',
          revision: 1,
          exterior_landscape: {
            run_id: 'run_bad_recov',
            access: {},
            validation_summary: { valid: false, violations: 'malformed_string' },
          },
        },
        revision: 1,
      }),
    })
    assert.strictEqual(resBad.status, 'failed')
    assert.strictEqual(controller.getState().contextFreshness, 'unavailable')
    assert.ok(controller.getState().contextError?.includes('validation_summary.violations'))

    // 2. Subsequent valid refresh recovers state completely
    const validExterior = {
      run_id: 'run_recovered_ok',
      access: { gate: { json_id: 'gate_recov' } },
      validation_summary: { valid: true, violations: [] },
    }
    const resGood = await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({
        master_json: {
          id: 'proj_recovery',
          revision: 2,
          exterior_landscape: validExterior,
        },
        revision: 2,
      }),
    })

    assert.strictEqual(resGood.status, 'success')
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    assert.strictEqual(controller.getState().contextError, null)
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_recovered_ok')
    assert.strictEqual(controller.getState().sourceRevision, 2)
    assert.strictEqual(controller.canExportMasterJson(), true)
    assert.strictEqual(controller.canGenerateAndSave(), true)

    passTest('Defect 1.11: Subsequent valid response restores correct state without obsolete errors')
  }

  console.log(`\nAll ${testCount} ELIA Stage 3 Production Behavior Tests Passed Successfully!`)
}

runAllTests().catch((err) => {
  console.error('\nTest Failure:', err)
  process.exit(1)
})
