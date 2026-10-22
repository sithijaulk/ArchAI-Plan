# ELIA Engine — Release Notes & Deployment Plan

> **Component 4**: Eco-Spatial Landscape Intelligence (ELIA Engine)  
> **Release Target**: Production Ready (Release Candidate v1.0.0)  
> **Completion Classification**: **B. Implementation Complete; Verification Blocked**  
> *(All ELIA-owned code is implemented, all 534 backend unit/integration tests and 70 frontend production tests pass cleanly; end-to-end multi-layer persistence was fully verified in isolated SQLite sessions matching the production schema; full live MySQL persistence verification was blocked solely by local MySQL server port 3306 unavailability).*

---

## 1. Summary of Completed Capabilities

1. **Authoritative Master JSON Integration**:
   - Ingests and enforces immutability for Component 1 (land boundary polygon, road facing, north bearing), Component 2 (house footprint, roof geometry, ground floor plan), and Component 3 (interior rooms and furniture).
2. **Preference Contract Normalization**:
   - Supports Modern, Greeny, and Minimalistic concepts; garage and vehicle requirements; straight and curved A* driveways; pedestrian walkways; verified plant species and quantities; garden seating; perimeter and zone lighting; boundary walls; utility safety buffers; solar PV; and elevated balcony greenery.
3. **Multi-Feature Feasibility Assessment**:
   - Evaluates spatial footprint fit, boundary setbacks, utility buffers (50 ft well-to-septic separation), solar orientation, and balcony load thresholds concurrently.
4. **Verified Plant Catalogue (v2.1)**:
   - 21 verified species calibrated for tropical/subtropical agro-ecological zones with micro-climate suitability checks and explicit alternative acceptance workflows.
5. **Hybrid Neural & Deterministic Generation**:
   - PyTorch 5-stage Convolutional UNet (`elia-garden-layout-v1.0`, ~162 ms CPU latency) predicts 2D probability heatmaps for trees, seating, and lighting.
   - Deterministic planners construct road-aligned gates, straight/curved A* driveways, solar photovoltaic arrays, and balcony container gardens.
6. **54-Rule Real-Time Validator**:
   - Independent verification across Geometric Validity, Environmental Suitability, Legal Assessment, Elevated Installation, and User Preference. Hard violations generate `approval_status="blocked"`.
7. **Three.js Viewport Synchronization**:
   - Zero-offset metric rendering, boundary hole preservation, elevated surface associations, and layer toggles.
8. **Transactional Compare-And-Swap (CAS) Persistence**:
   - Two-phase state transitions (`revision: 1 → 2 processing → 3 completed`), stale revision detection (HTTP 409 conflict), and immutable `ComponentRun` history tracking.

---

## 2. Defects Resolved in Phase 7 Integration

1. **Driveway Serialization Missing Fields (`ELIA_SERIALIZATION_ERROR`)**:
   - *Fixed*: Added required `json_id: "DRIVEWAY_001"`, `type: "driveway"`, and `units: "m"` to driveway outputs in both `layout_decoder.py` and `service.py`, eliminating Pydantic HTTP 500 validation crashes.
2. **Spatial Collisions in Neural Layout Decoding**:
   - *Fixed*: Updated `layout_decoder.py` to use `_entrance_target` (offsetting targets outside the house wall), subtracted `house_poly` from driveway and walkway polygons, and applied a lateral perpendicular offset (`±2.6m`) for the pedestrian path, resolving house and driveway intersection violations.
3. **Lighting Preference Normalization Cleared When `required` Was Omitted**:
   - *Fixed*: Changed condition in `requirements.py` from `if not lighting.get("required"):` to `if lighting.get("required") is False:` and stored `normalized["lighting"] = lighting`, ensuring active child preferences (such as `preferred_spacing`) are normalized and validated against minimum spacing rules.
4. **SQLite Test Environment Threading & Alias Clashes**:
   - *Fixed*: Configured `connect_args={"check_same_thread": False}` in test database fixtures and unified boundary aliases in the Master JSON test fixture.

---

## 3. Deployment & Release Runbook

### 3.1 Pre-Deployment Verification Checklist
- [x] All 534 backend unit and integration tests passing (`pytest backend/tests/ -o pythonpath=backend -q`).
- [x] Phase 7 end-to-end integration suite passing (`pytest backend/tests/test_elia_phase7_end_to_end.py`).
- [x] Frontend TypeScript compilation passing with 0 errors (`npx tsc --noEmit`).
- [x] Frontend Stage 3 state reconciliation tests passing (57/57 tests).
- [x] Panel feedback and Three.js geometry tests passing (13/13 tests).
- [x] Model weights artifact verified against SHA-256 hash (`f96e1597...`).
- [x] Components 1–3 and shared database models strictly untouched.

### 3.2 Deployment Procedure (Reviewable Plan — Not Automatically Executed)

1. **Deploy Backend**:
   ```bash
   cd backend
   # 1. Activate production virtual environment
   source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
   
   # 2. Install production dependencies
   pip install -r requirements.txt
   
   # 3. Verify model artifact SHA-256 hash
   python -c "import hashlib; print(hashlib.sha256(open('app/components/elia_engine/model_artifacts/garden_layout_v1/weights.npz','rb').read()).hexdigest())"
   # Verify output matches: f96e15976963a06960d76f836f86aa85d4986c1634fcacbc7fb3bd849c2fe79b
   
   # 4. Start backend service
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

2. **Deploy Frontend**:
   ```bash
   cd frontend
   # 1. Install production dependencies
   npm ci
   
   # 2. Build production Next.js bundle
   npm run build
   
   # 3. Start production server
   npm run start -- -p 3000
   ```

3. **Post-Deployment Smoke Verification**:
   ```bash
   # Verify service health
   curl -s http://localhost:8000/api/health
   # Verify ELIA rules
   curl -s http://localhost:8000/api/elia-engine/rules
   # Verify plant catalogue
   curl -s http://localhost:8000/api/elia-engine/plant-catalogue
   ```

---

## 4. Safe Rollback Procedure

Because ELIA is fully self-contained and **did not modify shared database schemas or introduce database migrations**, rolling back is fast and deterministic.

1. **Code Rollback**:
   Check out the previous known-good Git commit:
   ```bash
   git checkout <PREVIOUS_KNOWN_STABLE_COMMIT>
   ```

2. **Model Rollback**:
   If the neural model is flagged, ELIA can immediately fall back to the deterministic baseline pipeline by passing `generation_mode: "baseline"` in requests, or disabling the model adapter in `configure_model_adapter(None)`.

3. **Database Compatibility**:
   Saved projects with `current_component: "elia_engine"` contain standard Master JSON with `exterior_landscape`. Reverting code to a previous commit does not corrupt existing projects; prior component layers (C1–C3) remain intact.

---

## 5. Scope & Invariance Guarantees

1. **Components 1–3**: Zero modifications.
2. **Shared Infrastructure**: Zero changes to shared auth, database models, Alembic migrations, or shared API stores.
3. **No Financial Features**: Obsolete financial keys are stripped on ingress/egress.
4. **No Photo Uploads**: Client reference photos are excluded by platform design.
