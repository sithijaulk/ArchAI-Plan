import assert from 'assert'
import * as THREE from 'three'
import {
  sourceToScene,
  sceneToSource,
  eliaToThree,
  polygonToShape,
  polygonToLineLoops,
  featureCanopyRadius,
  featureHeight,
  deduplicateGates,
  extractNormalizedUpstreamGeometry,
  normalizePolygonCoordinates,
} from './eliaGeometry.js'

console.log('Running ELIA Geometry & Contract tests...')

// 1. Forward and Inverse Coordinate Transformations
{
  const origin = [15.0, 10.0]
  const scale = 2.5
  const sourceX = 25.0
  const sourceY = 18.0
  const elevM = 3.5

  const [sceneX, sceneY, sceneZ] = sourceToScene(sourceX, sourceY, elevM, origin, scale)
  assert.strictEqual(sceneX, (25.0 - 15.0) * 2.5, 'sceneX matches formula')
  assert.strictEqual(sceneY, 3.5 * 2.5, 'sceneY matches elevation formula')
  assert.strictEqual(sceneZ, -(18.0 - 10.0) * 2.5, 'sceneZ matches -sourceY formula')

  const inv = sceneToSource(sceneX, sceneY, sceneZ, origin, scale)
  assert.ok(Math.abs(inv.sourceX - sourceX) < 1e-9, 'inverse maps back sourceX')
  assert.ok(Math.abs(inv.sourceY - sourceY) < 1e-9, 'inverse maps back sourceY')
  assert.ok(Math.abs(inv.elevationM - elevM) < 1e-9, 'inverse maps back elevation')
  console.log('✓ Forward and inverse coordinate transformations verified')
}

// 2. Polygon Mesh and Boundary Alignment
{
  const origin = [10.0, 5.0]
  const scale = 1.8
  const testRing = [
    [10.0, 5.0],
    [20.0, 5.0],
    [20.0, 15.0],
    [10.0, 15.0],
  ]

  // Shape in local coordinates: u = (x - ox)*scale, v = (y - oy)*scale
  const shape = polygonToShape([testRing], origin, scale)
  assert.ok(shape, 'shape created')

  // Under Three.js Euler X rotation of -Math.PI / 2:
  // (u, v, 0) becomes scene (u, 0, -v)
  for (const [x, y] of testRing) {
    const expectedSceneX = (x - origin[0]) * scale
    const expectedSceneZ = -(y - origin[1]) * scale

    // Vector3 from eliaToThree
    const v3 = eliaToThree(x, y, 0, origin, scale)
    assert.ok(Math.abs(v3.x - expectedSceneX) < 1e-9, 'line point X matches expected')
    assert.ok(Math.abs(v3.z - expectedSceneZ) < 1e-9, 'line point Z matches expected')
  }
  console.log('✓ Polygon fill and boundary alignment verified with zero coordinate offset')
}

// 3. Hole Preservation in Three.js and Data Extraction
{
  const polyWithHole = [
    // Outer ring
    [[0, 0], [30, 0], [30, 20], [0, 20], [0, 0]],
    // Interior hole
    [[10, 5], [20, 5], [20, 15], [10, 15], [10, 5]],
  ]

  const normalized = normalizePolygonCoordinates(polyWithHole)
  assert.strictEqual(normalized.length, 2, 'both exterior and hole rings preserved')

  const shape = polygonToShape(polyWithHole, [0, 0], 1)
  assert.strictEqual(shape.holes.length, 1, 'interior hole preserved in THREE.Shape.holes')

  const lineLoops = polygonToLineLoops(polyWithHole, 0, [0, 0], 1)
  assert.strictEqual(lineLoops.length, 2, 'both outer and hole line loops generated')
  console.log('✓ Hole preservation in Three.js and geometry models verified')
}

// 4. Actual Vegetation Dimensions from Backend Schema
{
  const backendNode = {
    json_id: 'tree_1',
    position: [12.0, 14.0],
    height_m: 4.8,
    canopy_radius_m: 2.2,
    dimensions: {}, // Empty dimensions object from backend
  }

  const radius = featureCanopyRadius(backendNode)
  const height = featureHeight(backendNode)
  assert.strictEqual(radius, 2.2, 'featureCanopyRadius reads top-level canopy_radius_m')
  assert.strictEqual(height, 4.8, 'featureHeight reads top-level height_m')
  console.log('✓ Actual vegetation dimensions mapped correctly from backend schema')
}

// 5. Gate Deduplication
{
  const access = {
    gate: { json_id: 'gate_main', position: [5.0, 0.0], width_m: 4.0 },
    gates: [
      { json_id: 'gate_main', position: [5.0, 0.0], width_m: 4.0 }, // Duplicate
      { json_id: 'gate_pedestrian', position: [8.0, 0.0], width_m: 1.2 },
    ],
  }

  const deduplicated = deduplicateGates(access)
  assert.strictEqual(deduplicated.length, 2, 'duplicate gate removed')
  assert.strictEqual(deduplicated[0].json_id, 'gate_main')
  assert.strictEqual(deduplicated[1].json_id, 'gate_pedestrian')
  console.log('✓ Gate deduplication verified')
}

// 6. Upstream Master JSON Normalization & EliaViewModel
{
  const upstreamMasterFt = {
    revision: 3,
    units: 'ft',
    land_info: {
      mathematical_polygon: {
        type: 'Polygon',
        coordinates: [[[0, 0], [100, 0], [100, 60], [0, 60], [0, 0]]],
      },
    },
    house_exterior_polygon: [[20, 15], [60, 15], [60, 45], [20, 45], [20, 15]],
    building: { height: 20 }, // 20 ft
  }

  const landscapeMatching = {
    source_revision: 3,
    version: '1.0',
  }

  const vm = extractNormalizedUpstreamGeometry(upstreamMasterFt, landscapeMatching)
  assert.strictEqual(vm.geometryState, 'ready', 'viewModel is ready')
  assert.strictEqual(vm.sourceRevision, 3)
  assert.ok(vm.landPolygon, 'land polygon extracted')
  // 100 ft * 0.3048 = 30.48 m
  assert.ok(Math.abs(vm.landPolygon.coordinates[0][1][0] - 30.48) < 1e-4, 'units normalized to meters once')
  // 20 ft * 0.3048 = 6.096 m
  assert.ok(Math.abs(vm.buildingHeightM - 6.096) < 1e-4, 'building height normalized to meters')
  assert.strictEqual(vm.isHeightEstimated, false, 'height was supplied from upstream')

  // Revision mismatch check
  const landscapeStale = {
    source_revision: 2, // Stale!
  }
  const vmStale = extractNormalizedUpstreamGeometry(upstreamMasterFt, landscapeStale)
  assert.strictEqual(vmStale.geometryState, 'revision_mismatch', 'detects stale revision')
  console.log('✓ Upstream Master JSON normalization and EliaViewModel derivation verified')
}

console.log('All ELIA frontend geometry and contract checks passed successfully!')
