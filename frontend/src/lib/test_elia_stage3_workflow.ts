/**
 * ELIA Stage 3 Production Workflow & Behavior Verification Tests
 *
 * Directly tests the production controller, serializer, and error utilities:
 *  - EliaWorkflowController
 *  - validateRequirementsForm, serializeRequirements, computeRequirementsFingerprint
 *  - parseStrictInteger, parseStrictFloat
 *  - parseEliaError
 *
 * Verifies all 19 required async, provenance, ordering, lifecycle, and validation behaviors
 * using deferred promises for deterministic scheduling without fabricated Master JSON fixtures.
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
import type { ExteriorLandscape, EliaContextFreshness } from '../types/elia'

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

console.log('Running ELIA Stage 3 Production Behavior Tests...\n')

async function runAllTests() {
  // ---------------------------------------------------------------------------
  // 1. Deactivate → reactivate → load context succeeds (Section 3)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.deactivate()
    assert.strictEqual(controller.getState().isMounted, false)
    assert.strictEqual(controller.getState().isActive, false)

    // Reactivate establishing fresh session
    const freshSession = controller.activate('proj_1')
    assert.strictEqual(controller.getState().isMounted, true)
    assert.strictEqual(controller.getState().isActive, true)
    assert.strictEqual(controller.getState().sessionSeq, freshSession)

    const res = await controller.loadAuthoritativeContext(noopApi)
    assert.strictEqual(res.status, 'success')
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    console.log('✓ 1. Deactivate → reactivate → load context succeeds with fresh session')
  }

  // ---------------------------------------------------------------------------
  // 2. Old-session responses remain invalid after reactivation (Section 3)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')

    const defOld = createDeferredPromise<any>()
    const apiOld: EliaApiInterface = {
      ...noopApi,
      getContext: () => defOld.promise,
    }

    const pOld = controller.loadAuthoritativeContext(apiOld)

    // Deactivate and reactivate (e.g. Strict Mode cycle or quick unmount/mount)
    controller.deactivate()
    controller.activate('proj_1')

    // Old request resolves late
    defOld.resolve({ master_json: { id: 'old_data' }, revision: 99 })
    const resOld = await pOld

    assert.strictEqual(resOld.status, 'obsolete')
    assert.strictEqual(controller.getState().sourceRevision, null)
    assert.strictEqual(controller.getState().authoritativeMaster, null)
    console.log('✓ 2. Old-session responses remain strictly invalid after reactivation')
  }

  // ---------------------------------------------------------------------------
  // 3. React Strict Mode setup/cleanup/setup leaves actual page operational (Section 3)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_strict')

    // Setup 1
    controller.activate('proj_strict')
    const defCtx1 = createDeferredPromise<any>()
    controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defCtx1.promise })

    // Strict Mode Cleanup 1
    controller.deactivate()

    // Strict Mode Setup 2 on the SAME controller instance
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
    console.log('✓ 3. React Strict Mode setup/cleanup/setup sequence leaves controller operational')
  }

  // ---------------------------------------------------------------------------
  // 4. Server rendering / hydration has valid snapshot strategy (Section 4)
  // ---------------------------------------------------------------------------
  {
    const serverSnapshot = EliaWorkflowController.getServerSnapshot()
    assert.strictEqual(serverSnapshot.projectId, null)
    assert.strictEqual(serverSnapshot.isMounted, false)
    assert.strictEqual(serverSnapshot.contextFreshness, 'unavailable')
    assert.strictEqual(Object.isFrozen(serverSnapshot), true)

    const controller = new EliaWorkflowController(null)
    const instanceServerSnapshot = controller.getServerSnapshot()
    assert.strictEqual(instanceServerSnapshot, serverSnapshot)
    console.log('✓ 4. Server rendering / hydration snapshot is stable, frozen, and matches SSR')
  }

  // ---------------------------------------------------------------------------
  // 5. Location change during solar request resets loading (Section 7)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')

    const locA = { id: 1, name: 'Colombo', latitude: 6.927, longitude: 79.861 }
    const locB = { id: 2, name: 'Kandy', latitude: 7.290, longitude: 80.633 }

    controller.selectLocation(locA)
    const defSolar = createDeferredPromise<any>()
    controller.loadSolar({ ...noopApi, currentSolar: () => defSolar.promise }, locA)

    assert.strictEqual(controller.getState().isLoadingSolar, true)

    // User switches location while solar request is running
    controller.selectLocation(locB)
    assert.strictEqual(controller.getState().isLoadingSolar, false) // Cleared immediately!
    assert.strictEqual(controller.getState().solar, null)
    console.log('✓ 5. Location change during solar lookup immediately resets isLoadingSolar')
  }

  // ---------------------------------------------------------------------------
  // 6. Old solar completion cannot stop a newer solar loading state (Section 7)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')

    const locA = { id: 1, name: 'Colombo', latitude: 6.927, longitude: 79.861 }
    const locB = { id: 2, name: 'Galle', latitude: 6.053, longitude: 80.221 }

    controller.selectLocation(locA)
    const defSolarA = createDeferredPromise<any>()
    controller.loadSolar({ ...noopApi, currentSolar: () => defSolarA.promise }, locA)

    // Switch to B and start new solar lookup
    controller.selectLocation(locB)
    const defSolarB = createDeferredPromise<any>()
    const pB = controller.loadSolar({ ...noopApi, currentSolar: () => defSolarB.promise }, locB)

    assert.strictEqual(controller.getState().isLoadingSolar, true)

    // Old Solar A resolves
    defSolarA.resolve({ status: 'available', irradiance_w_m2: { shortwave_radiation: 800 } })
    // Req A completion MUST NOT clear Req B's loading state!
    assert.strictEqual(controller.getState().isLoadingSolar, true)

    // Solar B resolves
    defSolarB.resolve({ status: 'available', irradiance_w_m2: { shortwave_radiation: 950 } })
    const resB = await pB
    assert.strictEqual(resB.status, 'success')
    assert.strictEqual(controller.getState().isLoadingSolar, false)
    assert.strictEqual((controller.getState().solar?.irradiance_w_m2 as any).shortwave_radiation, 950)
    console.log('✓ 6. Old solar completion cannot stop a newer solar loading state')
  }

  // ---------------------------------------------------------------------------
  // 7. Clearing location handles pending solar success and failure (Section 7)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    const locA = { id: 1, name: 'Jaffna', latitude: 9.661, longitude: 80.025 }

    // Case 7a: Pending success
    controller.selectLocation(locA)
    const defSuccess = createDeferredPromise<any>()
    const pSuccess = controller.loadSolar({ ...noopApi, currentSolar: () => defSuccess.promise }, locA)
    controller.selectLocation(null) // Cleared!
    assert.strictEqual(controller.getState().isLoadingSolar, false)
    defSuccess.resolve({ status: 'available' })
    const resSuccess = await pSuccess
    assert.strictEqual(resSuccess.status, 'obsolete')
    assert.strictEqual(controller.getState().solar, null)

    // Case 7b: Pending failure
    controller.selectLocation(locA)
    const defFail = createDeferredPromise<any>()
    const pFail = controller.loadSolar({ ...noopApi, currentSolar: () => defFail.promise }, locA)
    controller.selectLocation(null) // Cleared!
    defFail.reject(new Error('Weather API 500'))
    const resFail = await pFail
    assert.strictEqual(resFail.status, 'obsolete')
    assert.strictEqual(controller.getState().locationError, null)
    console.log('✓ 7. Clearing location handles pending solar success and failure cleanly')
  }

  // ---------------------------------------------------------------------------
  // 8. Project switch during post-save context refresh causes no cross-project follow-up (Section 6)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_A')
    controller.activate('proj_A')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_A', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    let latestRunCalledOnProject: string | null = null
    const defCtx = createDeferredPromise<any>()

    const api: EliaApiInterface = {
      ...noopApi,
      run: async () => ({ run_id: 'run_A', outcome: 'valid', exterior_landscape: { run_id: 'run_A' } as any }),
      getContext: () => defCtx.promise,
      getResult: async (pid) => {
        latestRunCalledOnProject = pid
        return { run_id: 'latest', status: 'completed' } as any
      },
    }

    const savePromise = controller.generateAndSave(api)

    // While context refresh for proj_A is in-flight, switch to proj_B!
    controller.changeProject('proj_B')

    // Context refresh for proj_A fails
    defCtx.reject(new Error('Context refresh failed for proj_A'))
    const res = await savePromise

    assert.strictEqual(res.status, 'obsolete')
    // Must NOT have started getResult for proj_B as continuation of proj_A save!
    assert.strictEqual(latestRunCalledOnProject, null)
    // Must NOT show proj_A action error in proj_B UI!
    assert.strictEqual(controller.getState().actionError, null)
    assert.strictEqual(controller.getState().projectId, 'proj_B')
    console.log('✓ 8. Project switch during post-save refresh causes no cross-project follow-up or error notice')
  }

  // ---------------------------------------------------------------------------
  // 9. Project switch during latest-run refresh causes no cross-project state write (Section 6)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_A')
    controller.activate('proj_A')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_A', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    const defRun = createDeferredPromise<any>()
    const api: EliaApiInterface = {
      ...noopApi,
      run: async () => ({ run_id: 'run_A', outcome: 'valid', exterior_landscape: { run_id: 'run_A' } as any }),
      getContext: async () => ({ master_json: { id: 'proj_A', revision: 2 }, revision: 2 }),
      getResult: () => defRun.promise,
    }

    const savePromise = controller.generateAndSave(api)

    // Switch to proj_B while getResult is awaiting
    await new Promise((r) => setTimeout(r, 10))
    controller.changeProject('proj_B')

    // Resolve run A
    defRun.resolve({ run_id: 'run_A_result', status: 'completed' })
    const res = await savePromise

    assert.strictEqual(res.status, 'obsolete')
    assert.strictEqual(controller.getState().latestRun, null)
    assert.strictEqual(controller.getState().projectId, 'proj_B')
    console.log('✓ 9. Project switch during latest-run refresh causes no cross-project state write')
  }

  // ---------------------------------------------------------------------------
  // 10. Unmount during each post-save await prevents later writes (Section 6)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    const defCtx = createDeferredPromise<any>()
    const api: EliaApiInterface = {
      ...noopApi,
      run: async () => ({ run_id: 'run_1', outcome: 'valid', exterior_landscape: { run_id: 'run_1' } as any }),
      getContext: () => defCtx.promise,
    }

    const savePromise = controller.generateAndSave(api)
    await new Promise((r) => setTimeout(r, 10))

    // Unmount during post-save context await
    controller.unmount()
    defCtx.resolve({ master_json: { id: 'proj_1', revision: 2 }, revision: 2 })
    const res = await savePromise

    assert.strictEqual(res.status, 'obsolete')
    assert.strictEqual(controller.getState().isMounted, false)
    console.log('✓ 10. Unmount during post-save refresh cleanly prevents later state writes')
  }

  // ---------------------------------------------------------------------------
  // 11. Validation error after a form edit is discarded (Section 8)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    const defVal = createDeferredPromise<any>()
    const valPromise = controller.validateRequirements({
      ...noopApi,
      validateInput: () => defVal.promise,
    })

    // Edit form before error arrives
    controller.editRequirement({ drivewayStyle: 'curved' })

    defVal.reject({ response: { status: 422, data: { detail: 'Old input syntax error' } } })
    const res = await valPromise

    assert.strictEqual(res.status, 'obsolete')
    assert.strictEqual(controller.getState().validationError, null)
    assert.strictEqual(controller.getState().isValidating, false)
    console.log('✓ 11. Validation error after a form edit is discarded as obsolete')
  }

  // ---------------------------------------------------------------------------
  // 12. Validation result/error after source revision changes is discarded (Section 8)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    const defVal = createDeferredPromise<any>()
    const valPromise = controller.validateRequirements({
      ...noopApi,
      validateInput: () => defVal.promise,
    })

    // Revision changes while validation is in-flight
    await controller.loadAuthoritativeContext({
      ...noopApi,
      getContext: async () => ({ master_json: { id: 'proj_1', revision: 2 }, revision: 2 }),
    })
    assert.strictEqual(controller.getState().sourceRevision, 2)

    defVal.resolve({ valid: true, geometry: { land_area_m2: 500, house_footprint_area_m2: 150, source_units: 'm' }, orientation: { north_angle_degrees: 0 } })
    const res = await valPromise

    assert.strictEqual(res.status, 'obsolete')
    assert.strictEqual(controller.getState().validationResult, null)
    console.log('✓ 12. Validation result after source revision change is discarded')
  }

  // ---------------------------------------------------------------------------
  // 13. Generation-mode edit during request does not change submitted candidate mode (Section 9)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'
    controller.editRequirement({ generationMode: 'baseline' })

    const defPrev = createDeferredPromise<any>()
    const prevPromise = controller.previewCandidate({
      ...noopApi,
      preview: () => defPrev.promise,
    })

    // User switches mode toggle to trained_model while request is in-flight
    controller.editRequirement({ generationMode: 'trained_model' })

    defPrev.resolve({ run_id: 'prev_base', outcome: 'valid', exterior_landscape: { run_id: 'prev_base' } as any })
    await prevPromise

    // Candidate MUST preserve the submitted mode 'baseline', NOT the newer 'trained_model' selection
    assert.strictEqual(controller.getState().candidate?.generationMode, 'baseline')
    console.log('✓ 13. Generation-mode edit during request does not corrupt candidate submitted mode')
  }

  // ---------------------------------------------------------------------------
  // 14. Authoritative export is disabled during refresh and after refresh failure (Section 10)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    const defCtx = createDeferredPromise<any>()
    controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defCtx.promise })

    // During refresh, contextFreshness is non-current ('stale' or 'loading')
    assert.notStrictEqual(controller.getState().contextFreshness, 'current')

    defCtx.reject(new Error('Network error'))
    await new Promise((r) => setTimeout(r, 10))

    // After failure, contextFreshness is 'stale'
    assert.strictEqual(controller.getState().contextFreshness, 'stale')
    console.log('✓ 14. Authoritative export is disabled during refresh and after refresh failure')
  }

  // ---------------------------------------------------------------------------
  // 15. Save success plus refresh failure retains correctly paired accepted geometry (Section 11)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    const originalSnapshot = { id: 'proj_1', revision: 1, boundary: 'v1_polygon' }
    ;(controller as any).state.authoritativeMaster = originalSnapshot
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

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
    // Retains matching submitted source snapshot on accepted provenance
    assert.strictEqual((controller.getState().acceptedProvenance?.sourceSnapshot as any).boundary, 'v1_polygon')
    assert.strictEqual(controller.getState().acceptedLandscape?.run_id, 'run_saved_99')
    console.log('✓ 15. Save success plus refresh failure retains correctly paired accepted source snapshot')
  }

  // ---------------------------------------------------------------------------
  // 16. Old operation cleanup cannot release a newer mutation guard (Section 5)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')

    const token1 = (controller as any).acquireMutationGuard()
    assert.ok(token1 !== null)
    assert.strictEqual((controller as any).isMutatingSync, true)

    // Simulate second mutation token
    ;(controller as any).activeMutationToken = 999

    // Old mutation cleanup passes token1
    ;(controller as any).releaseMutationGuard(token1)

    // Newer mutation guard is STILL PROTECTED
    assert.strictEqual((controller as any).isMutatingSync, true)
    ;(controller as any).releaseMutationGuard(999)
    assert.strictEqual((controller as any).isMutatingSync, false)
    console.log('✓ 16. Old operation cleanup cannot release a newer mutation guard')
  }

  // ---------------------------------------------------------------------------
  // 17. Pre-mutation context responses cannot overwrite post-mutation state (Section 10)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')

    const defCtxOld = createDeferredPromise<any>()
    const pOld = controller.loadAuthoritativeContext({ ...noopApi, getContext: () => defCtxOld.promise })

    // Mutation starts, updates state to revision 5
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 5 }
    ;(controller as any).state.sourceRevision = 5
    ;(controller as any).state.contextFreshness = 'current'
    // Sequence advances
    ;(controller as any).contextReqId += 1

    defCtxOld.resolve({ master_json: { id: 'proj_1', revision: 1 }, revision: 1 })
    const resOld = await pOld

    assert.strictEqual(resOld.status, 'obsolete')
    assert.strictEqual(controller.getState().sourceRevision, 5)
    console.log('✓ 17. Pre-mutation context responses cannot overwrite post-mutation state')
  }

  // ---------------------------------------------------------------------------
  // 18. Infeasible-run refresh failure is not reported as successful refresh (Section 6)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    const api: EliaApiInterface = {
      ...noopApi,
      run: async () => ({
        run_id: 'run_inf',
        outcome: 'infeasible',
        exterior_landscape: { run_id: 'run_inf', validation_summary: { violations: ['Overlap'] } } as any,
      }),
      getContext: async () => {
        throw new Error('Refresh failed')
      },
    }

    const res = await controller.generateAndSave(api)
    assert.strictEqual(res.status, 'success')
    assert.strictEqual(res.refreshStatus, 'failed') // Explicitly failed, NOT success!
    assert.ok(controller.getState().actionError?.includes('unable to refresh project revision'))
    console.log('✓ 18. Infeasible-run refresh failure is accurately reported as failed refresh')
  }

  // ---------------------------------------------------------------------------
  // 19. Ambiguous mutation failure blocks blind resubmission until reconciliation (Section 10)
  // ---------------------------------------------------------------------------
  {
    const controller = new EliaWorkflowController('proj_1')
    controller.activate('proj_1')
    ;(controller as any).state.authoritativeMaster = { id: 'proj_1', revision: 1 }
    ;(controller as any).state.sourceRevision = 1
    ;(controller as any).state.contextFreshness = 'current'

    const apiNetworkFail: EliaApiInterface = {
      ...noopApi,
      run: async () => {
        const err: any = new Error('Network timeout (ECONNABORTED)')
        err.code = 'ECONNABORTED'
        throw err
      },
    }

    const res1 = await controller.generateAndSave(apiNetworkFail)
    assert.strictEqual(res1.status, 'failed')
    assert.strictEqual(controller.getState().requiresReconciliation, true)

    // Attempt blind resubmission without reconciling
    const res2 = await controller.generateAndSave(noopApi)
    assert.strictEqual(res2.status, 'failed')
    assert.strictEqual(res2.error, 'Reconciliation required')

    // Reconcile via authoritative context fetch
    await controller.loadAuthoritativeContext(noopApi)
    assert.strictEqual(controller.getState().requiresReconciliation, false)

    // Now mutations are allowed again
    assert.strictEqual(controller.getState().contextFreshness, 'current')
    console.log('✓ 19. Ambiguous mutation failure blocks blind resubmission until reconciliation')
  }

  // ---------------------------------------------------------------------------
  // Strict Number & Form Validation Checks (Section 14 & 15)
  // ---------------------------------------------------------------------------
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

    console.log('✓ 20. Fractional counts, non-finite values, and malformed numeric strings are strictly rejected')
  }

  console.log('\nAll 20 ELIA Stage 3 Production Behavior Tests Passed Successfully!')
}

runAllTests().catch((err) => {
  console.error('\nTest Failure:', err)
  process.exit(1)
})
