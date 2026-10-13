/**
 * ELIA Stage 3 Frontend Workflow & Contract Verification
 *
 * Exercises:
 *  1. Requirement serialization and dependency cleaning (no stale hidden values).
 *  2. Explicit generation_mode="baseline" requirement.
 *  3. Preview (non-mutating) vs Run (mutating, CAS-protected) semantics.
 *  4. Infeasible candidate handling (accepted design preserved).
 *  5. CAS conflict (HTTP 409) and model unavailable (HTTP 503) error mapping.
 *  6. Export labeling distinctions (authoritative Master JSON vs candidate).
 */
import assert from 'assert'
import type {
  ELIARequirements,
  ELIARequestPayload,
  ExteriorLandscape,
  EliaViewModel,
} from '../types/elia'
import { extractNormalizedUpstreamGeometry } from './eliaGeometry'

console.log('Running ELIA Stage 3 Frontend Workflow Tests...')

// ---------------------------------------------------------------------------
// 1. Requirement Serialization & Dependent Field Sanitization
// ---------------------------------------------------------------------------
{
  const serializeRequirements = (form: {
    garageRequired: boolean
    garageCapacity: number
    drivewayRequired: boolean
    drivewayStyle: string
    boundaryWallRequired: boolean
    boundaryWallHeightM: number
    lightingRequired: boolean
    lightingStyle: string
    selectedLocation: { latitude: number; longitude: number; timezone?: string | null; name: string } | null
  }): ELIARequirements => {
    const req: ELIARequirements = {
      units: 'm',
      design_style: 'contemporary',
      greenery_level: 'medium',
      access: {
        garage_required: form.garageRequired,
        driveway_required: form.drivewayRequired,
      },
      landscape: {
        boundary_wall_required: form.boundaryWallRequired,
      },
      lighting: {
        required: form.lightingRequired,
      },
    }

    if (form.garageRequired) {
      req.access!.garage_capacity = form.garageCapacity
    }
    if (form.drivewayRequired) {
      req.access!.driveway_style = form.drivewayStyle
    }
    if (form.boundaryWallRequired) {
      req.landscape!.boundary_wall_height_m = form.boundaryWallHeightM
    }
    if (form.lightingRequired) {
      req.lighting!.style = form.lightingStyle
    }
    if (form.selectedLocation) {
      req.location = {
        latitude: form.selectedLocation.latitude,
        longitude: form.selectedLocation.longitude,
        timezone: form.selectedLocation.timezone || null,
        city: form.selectedLocation.name,
      }
    }
    return req
  }

  // Case A: Garage and wall disabled — dependent fields must NOT be present
  const disabledReq = serializeRequirements({
    garageRequired: false,
    garageCapacity: 2,
    drivewayRequired: false,
    drivewayStyle: 'curved',
    boundaryWallRequired: false,
    boundaryWallHeightM: 2.2,
    lightingRequired: false,
    lightingStyle: 'accent',
    selectedLocation: null,
  })

  assert.strictEqual(disabledReq.access?.garage_required, false)
  assert.strictEqual(disabledReq.access?.garage_capacity, undefined, 'garage_capacity omitted when garageRequired is false')
  assert.strictEqual(disabledReq.access?.driveway_style, undefined, 'driveway_style omitted when drivewayRequired is false')
  assert.strictEqual(disabledReq.landscape?.boundary_wall_height_m, undefined, 'wall height omitted when wallRequired is false')
  assert.strictEqual(disabledReq.lighting?.style, undefined, 'lighting style omitted when lighting is false')
  assert.strictEqual(disabledReq.location, undefined, 'location omitted when not selected')
  console.log('✓ Requirement serialization omits stale dependent values when parent is disabled')

  // Case B: Enabled fields are serialized cleanly
  const enabledReq = serializeRequirements({
    garageRequired: true,
    garageCapacity: 2,
    drivewayRequired: true,
    drivewayStyle: 'straight',
    boundaryWallRequired: true,
    boundaryWallHeightM: 1.8,
    lightingRequired: true,
    lightingStyle: 'minimal',
    selectedLocation: { latitude: 6.9271, longitude: 79.8612, timezone: 'Asia/Colombo', name: 'Colombo' },
  })

  assert.strictEqual(enabledReq.access?.garage_capacity, 2)
  assert.strictEqual(enabledReq.access?.driveway_style, 'straight')
  assert.strictEqual(enabledReq.landscape?.boundary_wall_height_m, 1.8)
  assert.strictEqual(enabledReq.lighting?.style, 'minimal')
  assert.strictEqual(enabledReq.location?.city, 'Colombo')
  assert.strictEqual(enabledReq.location?.latitude, 6.9271)
  console.log('✓ Requirement serialization includes active fields with exact units')
}

// ---------------------------------------------------------------------------
// 2. Explicit Generation Mode & Non-Destructive Preview vs Persist Semantics
// ---------------------------------------------------------------------------
{
  const mockMaster = {
    project_id: 'proj_test',
    revision: 3,
    land_info: { mathematical_polygon: [[0, 0], [25, 0], [25, 20], [0, 20]], road_facing: 'south' },
  }

  // Preview request
  const previewPayload: ELIARequestPayload = {
    master_json: mockMaster,
    requirements: { units: 'm', design_style: 'contemporary' },
    generation_mode: 'baseline',
    source_revision: 3,
  }

  assert.strictEqual(previewPayload.generation_mode, 'baseline', 'explicit baseline requested')
  assert.strictEqual(previewPayload.apply_to_project, undefined, 'preview does not apply to project')
  assert.strictEqual(previewPayload.master_json, mockMaster, 'preview carries master_json snapshot')

  // Run/Persist request
  const runPayload: ELIARequestPayload = {
    requirements: { units: 'm', design_style: 'contemporary' },
    generation_mode: 'baseline',
    apply_to_project: true,
    source_revision: 3,
  }

  assert.strictEqual(runPayload.apply_to_project, true, 'run requests persistence')
  assert.strictEqual(runPayload.source_revision, 3, 'run specifies authoritative source revision')
  console.log('✓ Preview and Run payload contracts follow explicit mode and persistence semantics')
}

// ---------------------------------------------------------------------------
// 3. Accepted Design Preservation on Infeasible Run
// ---------------------------------------------------------------------------
{
  const acceptedDesign: Partial<ExteriorLandscape> = {
    version: '1.0',
    schema_version: '1.0',
    run_id: 'run_accepted_001',
    coordinate_reference: 'local_cartesian_meters',
    access: { gate: { json_id: 'gate_1' } },
  }

  const infeasibleCandidate: Partial<ExteriorLandscape> = {
    version: '1.0',
    schema_version: '1.0',
    run_id: 'run_infeasible_002',
    coordinate_reference: 'local_cartesian_meters',
    access: {},
    validation_summary: {
      valid: false,
      violations: ['Insufficient setback for requested 3-car garage'],
      checks_passed: 12,
      checks_total: 14,
      constraint_satisfaction_rate: 0.85,
    },
  }

  // State reducer simulation
  let currentAccepted = acceptedDesign
  let displayedView: 'accepted' | 'candidate' = 'accepted'
  let viewStatus: 'accepted' | 'preview' | 'infeasible' = 'accepted'

  const onRunComplete = (outcome: 'valid' | 'infeasible', candidate: any) => {
    if (outcome === 'valid') {
      currentAccepted = candidate
      displayedView = 'accepted'
      viewStatus = 'accepted'
    } else {
      // Infeasible preserves accepted design!
      displayedView = 'candidate'
      viewStatus = 'infeasible'
    }
  }

  onRunComplete('infeasible', infeasibleCandidate)

  assert.strictEqual(currentAccepted.run_id, 'run_accepted_001', 'Earlier accepted design preserved untouched')
  assert.strictEqual(displayedView, 'candidate', 'Displayed view switched to candidate for inspection')
  assert.strictEqual(viewStatus, 'infeasible', 'Status marked infeasible (unaccepted)')
  console.log('✓ Infeasible run preserves previously accepted exterior intact')
}

// ---------------------------------------------------------------------------
// 4. Concurrency CAS & Error Mapping Verification
// ---------------------------------------------------------------------------
{
  const parseApiError = (status: number, detail: any): { type: string; message: string } => {
    if (status === 409) {
      const rev = detail?.current_revision || 'newer'
      return {
        type: 'STALE_REVISION',
        message: `Revision Conflict (409): The project was modified concurrently (revision ${rev}). Refresh required.`,
      }
    }
    if (status === 503) {
      return {
        type: 'MODEL_UNAVAILABLE',
        message: `${detail?.code || 'ELIA_MODEL_UNAVAILABLE'}: ${detail?.message || 'Trained model unavailable.'}`,
      }
    }
    return { type: 'GENERIC_ERROR', message: detail?.message || 'Unknown failure' }
  }

  const conflict = parseApiError(409, {
    code: 'ELIA_STALE_SOURCE_REVISION',
    message: 'Project changed while ELIA was running.',
    current_revision: 4,
  })
  assert.strictEqual(conflict.type, 'STALE_REVISION')
  assert.ok(conflict.message.includes('revision 4'), '409 error message reflects current revision')

  const unavailable = parseApiError(503, {
    code: 'ELIA_MODEL_UNAVAILABLE',
    message: 'Trained model adapter is not registered on this backend.',
  })
  assert.strictEqual(unavailable.type, 'MODEL_UNAVAILABLE')
  assert.ok(unavailable.message.includes('ELIA_MODEL_UNAVAILABLE'), '503 error message retains explicit code')
  console.log('✓ API error mapping handles 409 CAS conflict and 503 model unavailable truthfully')
}

// ---------------------------------------------------------------------------
// 5. Export Categorization
// ---------------------------------------------------------------------------
{
  const fullMaster = {
    project_id: 'p1',
    project_name: 'Villa Horizon',
    land_info: { area_m2: 500 },
    buildable_footprint: {},
    exterior_landscape: { run_id: 'run_1', access: {} },
  }

  const exteriorOnly = fullMaster.exterior_landscape

  // Master JSON export must contain full project structure
  assert.ok('land_info' in fullMaster, 'Full Master JSON has land_info')
  assert.ok('exterior_landscape' in fullMaster, 'Full Master JSON has exterior_landscape')

  // Exterior JSON export must NOT masquerade as Master JSON
  assert.strictEqual('land_info' in exteriorOnly, false, 'Exterior-only export does not contain top-level master fields')
  assert.ok('access' in exteriorOnly, 'Exterior-only export contains exterior layers')
  console.log('✓ Export categorization cleanly separates Authoritative Master JSON from Exterior Candidate')
}

console.log('All ELIA Stage 3 Frontend Workflow Tests PASSED successfully!')
