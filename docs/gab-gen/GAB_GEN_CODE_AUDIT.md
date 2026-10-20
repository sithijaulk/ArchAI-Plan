# Component 1 (GAB-Gen) Implementation Audit Report

**Branch:** `feature/gab-gen`  
**Initiative:** ArchAI-Plan Research Platform  
**Scope:** Strict source-code & test verification for Geo-Spatial AI Blueprint Generator (GAB-Gen)  
**Execution Environment:** macOS, Python 3.14.7, Node.js / Next.js 14  
**Date:** October 19, 2026  

---

## Executive Summary

This audit assesses the actual code implemented within `feature/gab-gen` without relying on documentation assertions. Code verification was performed by reading line-by-line source files and executing automated test suites against the backend (`pytest`).

### Overall Status Breakdown:
* **Survey Extraction & Preprocessing (OpenCV / EasyOCR):** **Implemented**
* **Canonical P0 Trigonometric Reconstruction & Closure:** **Implemented**
* **Regulatory Rules Engine & Metadata Traceability:** **Implemented**
* **Buildable Footprint (Edge-aware Setbacks):** **Implemented**
* **Irregular-Land-Aware Floor-Plan Generation:** **Implemented**
* **Multi-Storey Allocation & Consistent Staircase Core:** **Implemented**
* **Floor-Specific Room IDs and Labels:** **Implemented**
* **Actual Vector Measurements & Annotations:** **Implemented**
* **Editable Blueprint Synchronization:** **Implemented**
* **Centralized Master JSON Non-Destructive Merging:** **Implemented**
* **Selectable Roof Designs:** **Missing**
* **ML / XGBoost Room Allocation Model:** **Partial (Schema Defined, Deterministic Rule-Based Baseline Active)**

---

## Detailed Requirement-by-Requirement Audit

### 1. Irregular-Land-Aware Floor-Plan Generation

* **Status:** **Implemented**
* **Exact Source File & Function:**
  - `backend/app/components/gab_gen/vector_reconstruction/reconstruct.py` -> `reconstruct_polygon`
  - `backend/app/components/gab_gen/buildable_footprint/compute.py` -> `compute_buildable_footprint`
  - `backend/app/components/gab_gen/blueprint/generator.py` -> `generate_blueprint_floors`, `partition_polygon_proportional`
* **What the Code Actually Does:**
  1. `reconstruct_polygon` parses legal traverse edges (distances and bearings/azimuths), projects $(dx, dy)$ using trigonometric formulas from origin $P_0(0,0)$ in canonical meters ($+X=\text{East}, +Y=\text{North}$).
  2. `compute_buildable_footprint` clips the irregular land boundary with edge-specific setbacks (Front: 3.0m, Rear: 2.3m, Sides: 1.0m) using Shapely polygon difference. If setbacks cause the parcel to collapse, it halts with status `infeasible`.
  3. `generate_blueprint_floors` slices the actual irregular Shapely `Polygon` (not an axis-aligned bounding box). Slicing occurs proportionally to required room areas using recursive/sequential slab intersection (`cutter_box.intersection(current_poly)`), guaranteeing all generated room boundaries strictly reside within the irregular buildable polygon.
* **Missing Functionality / Edge Cases:**
  - Curved boundary deeds (e.g. arc cul-de-sacs) are not discretized; the traverse reconstructor assumes linear polyline edges.
* **Test Evidence:**
  - `tests/test_gab_gen.py::test_buildable_footprint_traceability` -> **PASSED**
  - `tests/test_gab_gen.py::test_buildable_footprint_collapsed_returns_infeasible` -> **PASSED**
  - `tests/test_gab_gen.py::test_blueprint_generated_area_near_target` -> **PASSED**

---

### 2. Floor-Specific Room IDs and Labels

* **Status:** **Implemented**
* **Exact Source File & Function:**
  - `backend/app/components/gab_gen/space_allocation/allocator.py` -> `RuleBasedSpaceAllocationProvider.allocate_space` (Lines 267–387)
  - `backend/app/components/gab_gen/blueprint/generator.py` -> `generate_blueprint_floors` (Lines 52–126)
  - `frontend/src/features/gab-gen/components/preview/PlanPreview2D.tsx` (Lines 205–259)
* **What the Code Actually Does:**
  1. Floor identifiers are structured as `F0` (Ground Floor), `F1` (First Floor), `F2` (Second Floor), `F3` (Third Floor).
  2. Staircase core is consistently assigned ID `{floor_id}_STAIR` (e.g., `F0_STAIR`, `F1_STAIR`).
  3. Rooms receive deterministic, unique floor-prefixed IDs based on room type and per-floor index:
     `r_id = f"{floor_id}_{r_data['type'][:3].upper()}_{idx+1}"` (e.g., `F0_LIV_1`, `F0_KIT_2`, `F1_MAS_1`, `F1_BED_2`).
  4. Room labels display human-readable names (`rm.name`) and calculated areas (`rm.area.toFixed(1)} m²`) in the 2D SVG canvas (`PlanPreview2D.tsx:236-256`).
* **Missing Functionality / Bugs:**
  - None found in generation logic. Unique constraints across floors are maintained.
* **Test Evidence:**
  - `tests/test_gab_gen.py::test_four_storey_dynamic_allocation` -> **PASSED**
  - `tests/test_gab_gen_features.py::test_blueprint_room_edit_constraint_enforcement` -> **PASSED**

---

### 3. Actual Vector Measurements and Visual Preview

* **Status:** **Implemented**
* **Exact Source File & Function:**
  - `backend/app/components/gab_gen/vector_reconstruction/reconstruct.py` -> `reconstruct_polygon` (Lines 118–155)
  - `backend/app/components/gab_gen/blueprint/generator.py` -> `derive_wall_segments` (Lines 256–311)
  - `frontend/src/features/gab-gen/components/preview/PlanPreview2D.tsx` (Lines 278–298)
* **What the Code Actually Does:**
  1. Traversed edge distances are preserved in meters (`round(dist_m, 4)`) along with normalized azimuth degrees.
  2. Wall segments are generated with discrete `thickness` (exterior: 0.22m, interior: 0.12m) and length calculated via Euclidean distance.
  3. In `PlanPreview2D.tsx`, when `showDimensions` is active, the SVG calculates edge midpoint and vector Euclidean distance `Math.hypot(nextP.x - p.x, nextP.y - p.y)` and renders dimension labels (`{dist.toFixed(1)}m`) in monospace blue font directly along the boundary segments.
* **Missing Functionality / Bugs:**
  - Interior room wall dimensions (e.g. wall length annotations on room partitions) are not displayed; dimension tags are currently rendered along the outer land perimeter edges.
* **Test Evidence:**
  - `tests/test_gab_gen.py::test_bearing_normalization_quadrants` -> **PASSED**
  - `tests/test_gab_gen.py::test_canonical_coordinates_negative_crossings` -> **PASSED**

---

### 4. Selectable Roof Designs

* **Status:** **Missing**
* **Exact Source File & Investigation:**
  - Grep search across the entire repository for `roof` returned **0 matches**.
  - `frontend/src/features/gab-gen/components/input/RequirementsForm.tsx`: No input field, dropdown, or toggle for roof style (e.g., Gable, Hip, Flat Concrete Slab, Mono-pitch).
  - `backend/app/components/gab_gen/schemas.py`: `ClientRequirementsInput` lacks a `roof_type` attribute.
  - `frontend/src/features/gab-gen/components/preview/PlanPreview3D.tsx`: Three.js scene only extrudes ground base, floor slabs, room volumes, and vertical walls up to height 2.7m; no roof mesh geometry is rendered.
* **What the Code Actually Does:**
  - The system terminates vertical extrusion at the top floor ceiling slab without generating or offering a roof structure.
* **Missing Functionality / Bugs:**
  - Missing `roof_type` parameter in client requirements schema.
  - Missing roof geometry builder in backend blueprint generator.
  - Missing 3D mesh representation in `PlanPreview3D.tsx`.

---

### 5. Editable Blueprint Synchronization

* **Status:** **Implemented**
* **Exact Source File & Function:**
  - `backend/app/components/gab_gen/blueprint/editor.py` -> `validate_room_edit`, `apply_room_edit`
  - `backend/app/routers/gab_gen.py` -> `edit_blueprint_room` (`POST /projects/{project_id}/gab-gen/edit-room`)
  - `frontend/src/features/gab-gen/components/preview/BlueprintViewer.tsx` -> `handleNudgeRoom` (Lines 41–74)
  - `frontend/src/features/gab-gen/api/index.ts` -> `gabGenExtendedApi.editRoom`
* **What the Code Actually Does:**
  1. Room selection: Users click any room polygon in `PlanPreview2D.tsx` to highlight it in pink.
  2. Nudge interaction: `BlueprintViewer.tsx` displays directional buttons (`←`, `→`, `↑`, `↓`) moving vertices by `dx = ±0.5m` or `dy = ±0.5m`.
  3. Server-side constraint enforcement:
     - Checks polygon topological validity.
     - Checks containment within `buildable_poly.buffer(0.05)`.
     - Checks room intersection/overlap with all other rooms on that floor (`inter.area > 0.1 m²` triggers violation).
  4. Non-destructive sync: On success, recalculates wall segments, updates `project.master_json["floor_plan"]`, commits to the database, and calls `onUpdate(updatedMasterJson)` to update React state.
* **Missing Functionality / Bugs:**
  - Frontend nudge UI offers fixed 0.5m discrete increments; freeform drag-and-drop handles are not implemented in the SVG.
* **Test Evidence:**
  - `tests/test_gab_gen_features.py::test_blueprint_room_edit_constraint_enforcement` -> **PASSED**

---

### 6. Centralized Master JSON Architecture

* **Status:** **Implemented**
* **Exact Source File & Function:**
  - `backend/app/components/gab_gen/output/master_json_builder.py` -> `build_gab_master_json`
  - `backend/app/routers/gab_gen.py` -> `generate_blueprint`, `edit_blueprint_room`
* **What the Code Actually Does:**
  1. Non-destructive deepcopy: Accepts `existing_master_json` and performs `copy.deepcopy()`.
  2. Isolated ownership: Modifies only GAB-Gen keys:
     - `input_metadata`
     - `survey_extraction`
     - `land_info`
     - `geometry_validation`
     - `regulatory_rules`
     - `buildable_footprint`
     - `client_requirements`
     - `space_allocation`
     - `floor_plan`
     - `gab_gen_validation`
     - `processing.gab_gen`
  3. Preserves all other component sections untouched (e.g. `structural_rectification`, `interior_layout`, `exterior_landscape`).
* **Missing Functionality / Bugs:**
  - None. Adheres strictly to the platform Master JSON specification (`shared/master-json.schema.json`).
* **Test Evidence:**
  - `tests/test_gab_gen.py::test_master_json_preserves_unrelated_sections` -> **PASSED**

---

### 7. AI Model / XGBoost Spatial Allocation

* **Status:** **Partial (Schema Defined, Deterministic Rule-Based Baseline Active)**
* **Exact Source File & Function:**
  - `training/gab_gen/schema.py`: Codifies feature vectors (land area, setback ratios, room counts, aspect ratios) and train/val/test splits (70/15/15, seed 42).
  - `backend/app/components/gab_gen/space_allocation/allocator.py` -> `RuleBasedSpaceAllocationProvider`
* **What the Code Actually Does:**
  - The active allocator is a deterministic heuristic provider.
  - Sizing is retrieved from `gab_baseline_room_program.json`.
  - Machine learning model weights (`.json` / `.bin`) are deliberately omitted pending empirical survey dataset collection.
* **Missing Functionality:**
  - Actual XGBoost trained model inference pipeline is not yet attached to runtime.

---

## Complete Test Suite Execution Results

Executed directly via `pytest` inside the `backend` environment:

```text
============================= test session starts ==============================
platform darwin -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/kavindyasithumini/Documents/research/backend
plugins: anyio-4.15.1
collected 25 items

tests/test_gab_gen.py::test_bearing_normalization_quadrants PASSED       [  4%]
tests/test_gab_gen.py::test_north_angle_does_not_double_rotate_normalized_azimuth PASSED [  8%]
tests/test_gab_gen.py::test_canonical_coordinates_negative_crossings PASSED [ 12%]
tests/test_gab_gen.py::test_missing_verified_jurisdiction_requires_configuration PASSED [ 16%]
tests/test_gab_gen.py::test_research_test_rules_require_explicit_mode PASSED [ 20%]
tests/test_gab_gen.py::test_buildable_footprint_traceability PASSED      [ 24%]
tests/test_gab_gen.py::test_buildable_footprint_collapsed_returns_infeasible PASSED [ 28%]
tests/test_gab_gen.py::test_mandatory_rooms_never_silently_scaled_down PASSED [ 32%]
tests/test_gab_gen.py::test_explicit_floor_conflict_returns_infeasible PASSED [ 36%]
tests/test_gab_gen.py::test_four_storey_dynamic_allocation PASSED        [ 40%]
tests/test_gab_gen.py::test_blueprint_generated_area_near_target PASSED  [ 44%]
tests/test_gab_gen.py::test_master_json_preserves_unrelated_sections PASSED [ 48%]
tests/test_gab_gen_features.py::test_acre_conversion PASSED              [ 52%]
tests/test_gab_gen_features.py::test_arp_notation_parsing PASSED         [ 56%]
tests/test_gab_gen_features.py::test_drawing_scale_validation PASSED     [ 60%]
tests/test_gab_gen_features.py::test_inconsistent_requirements_rejected PASSED [ 64%]
tests/test_gab_gen_features.py::test_regulatory_rule_metadata_traceability PASSED [ 68%]
tests/test_gab_gen_features.py::test_blueprint_room_edit_constraint_enforcement PASSED [ 72%]
tests/test_gab_gen_api.py::test_gab_context_endpoint PASSED              [ 76%]
tests/test_gab_gen_api.py::test_upload_invalid_file PASSED               [ 80%]
tests/test_gab_gen_api.py::test_upload_corrupt_image PASSED              [ 84%]
tests/test_gab_gen_api.py::test_upload_valid_survey PASSED               [ 88%]
tests/test_gab_gen_api.py::test_generate_without_survey_rejected PASSED  [ 92%]
tests/test_gab_gen_api.py::test_generate_without_requirements_rejected PASSED [ 96%]
tests/test_gab_gen_api.py::test_generate_full_pipeline_success PASSED    [100%]

======================= 25 passed, 28 warnings in 0.73s ========================
```

---

## Action Items & Recommendations

1. **Implement Selectable Roof Designs:**
   - Add `roof_type: Literal["flat_slab", "gable", "hip", "mono_pitch"] = "flat_slab"` to `ClientRequirementsInput` in `backend/app/components/gab_gen/schemas.py`.
   - Add roof type selector dropdown to `RequirementsForm.tsx`.
   - Add parametric roof mesh generator to `PlanPreview3D.tsx` to visualize roof pitched geometry above the top floor.
2. **Interior Wall Dimension Labels:**
   - Extend `PlanPreview2D.tsx` to compute and display wall length annotations for interior dividing walls in addition to perimeter deed edges.
3. **Curved Boundary Discretization:**
   - Extend `reconstruct.py` to support arc segment interpolation for curved deed boundaries.
