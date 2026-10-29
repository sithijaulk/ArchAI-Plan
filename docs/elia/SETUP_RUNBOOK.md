# ELIA Engine — Reproducible Setup & Operational Runbook

> **Component 4**: Eco-Spatial Landscape Intelligence (ELIA Engine)  
> **System Architecture**: FastAPI Backend (Python) + Next.js / Three.js Frontend (TypeScript)  
> **Repository Root**: Project-relative paths throughout (compatible with Windows PowerShell and POSIX bash)

---

## 1. System Overview & Technology Stack

The ELIA Engine operates as an integrated micro-service and frontend component within the ArchAI-Plan platform.

- **Backend Framework**: Python 3.11–3.14 with FastAPI, Pydantic v2, SQLAlchemy ORM, and Shapely.
- **Machine Learning**: PyTorch / NumPy CPU-inference Convolutional UNet (`elia-garden-layout-v1.0`).
- **Database**: MySQL 8.0 (production/staging) or isolated SQLite (local test/development).
- **Frontend Framework**: Next.js 14+ (App Router), React, TypeScript, Three.js (`@react-three/fiber`), TailwindCSS.
- **External Providers**: Open-Meteo Solar API (live irradiance and clear-sky models; graceful deterministic fallback when offline).

---

## 2. Prerequisites & Supported Runtime Versions

| Software Component | Supported Versions | Verification Command |
|---|---|---|
| **Python** | 3.11.x, 3.12.x, 3.13.x, 3.14.x | `python --version` |
| **Node.js** | 18.x, 20.x, 22.x, 24.x | `node --version` |
| **npm** | 9.x, 10.x+ | `npm --version` |
| **MySQL** *(optional for SQLite test)* | 8.0+ | `mysql --version` |

---

## 3. Environment Variables & Configuration

ELIA relies on platform environment variables for database connectivity and external service endpoints. **Never store real credentials or secrets in source control.**

### Backend Configuration (`backend/.env` or process environment)
```bash
# Database connection string (MySQL in production/staging; defaults to SQLite if unset in tests)
DATABASE_URL=mysql+pymysql://<DB_USER>:<DB_PASSWORD>@localhost:3306/archai_plan

# Application environment
ENVIRONMENT=development
LOG_LEVEL=INFO

# Admin API Secret (shared auth token or bearer secret)
JWT_SECRET_KEY=<SECURE_RANDOM_SECRET_KEY>

# Optional: Dedicated disposable MySQL URL for running isolated MySQL persistence tests
# ELIA_TEST_MYSQL_URL=mysql+pymysql://<DB_USER>:<DB_PASSWORD>@localhost:3306/elia_test_db
```

### Frontend Configuration (`frontend/.env.local`)
```bash
# Points to local or hosted FastAPI backend
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

---

## 4. Installation & Setup Instructions

### 4.1 Backend Setup

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment**:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS (bash)**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Verify Model Artifact & Resource Files**:
   The trained layout weights and rule files reside in `backend/app/components/elia_engine/`:
   - Model weights: `backend/app/components/elia_engine/model_artifacts/garden_layout_v1/weights.npz`
   - Model manifest: `backend/app/components/elia_engine/model_artifacts/garden_layout_v1/manifest.json`
   - Plant catalogue: `backend/app/components/elia_engine/data/vegetation_catalog.json`
   - Lighting rules: `backend/app/components/elia_engine/data/lighting_rules.json`
   - Access rules: `backend/app/components/elia_engine/data/access_rules.json`

   Verify artifact integrity using SHA-256:
   - **Windows PowerShell**:
     ```powershell
     Get-FileHash backend/app/components/elia_engine/model_artifacts/garden_layout_v1/weights.npz -Algorithm SHA256
     # Expected: F96E15976963A06960D76F836F86AA85D4986C1634FCACBC7FB3BD849C2FE79B
     ```
   - **Linux / macOS**:
     ```bash
     sha256sum backend/app/components/elia_engine/model_artifacts/garden_layout_v1/weights.npz
     # Expected: f96e15976963a06960d76f836f86aa85d4986c1634fcacbc7fb3bd849c2fe79b
     ```

### 4.2 Frontend Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install Node.js dependencies**:
   ```bash
   npm install
   ```

3. **Verify TypeScript compilation**:
   ```bash
   npx tsc --noEmit
   ```

---

## 5. Startup Commands & Ports

### 5.1 Starting the Backend Server
- **Default Port**: `8000`
- **Command** (from `backend/` with active `.venv`):
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```
- **Readiness Verification**:
  ```bash
  curl http://localhost:8000/api/health
  # Response: {"status":"ok","app":"ArchAI-Plan","env":"development"}
  ```
- **ELIA Rules & Metadata Endpoint Verification**:
  ```bash
  curl http://localhost:8000/api/elia-engine/rules
  # Returns 54 versioned rules with categories and verification levels
  ```

### 5.2 Starting the Frontend Dev Server
- **Default Port**: `3000`
- **Command** (from `frontend/`):
  ```bash
  npm run dev -- -p 3000
  ```
- **Accessing the ELIA Interface**:
  Open a modern browser (Chrome, Firefox, Edge, Safari) at:
  `http://localhost:3000/features/elia-engine`

---

## 6. Verification & Test Execution Suite

### 6.1 Backend Tests
Run from the repository root or `backend/` directory:
```bash
# 1. Run the Phase 7 End-to-End Integration Suite (8 comprehensive scenarios)
pytest backend/tests/test_elia_phase7_end_to_end.py -o pythonpath=backend -vv

# 2. Run the Full Backend Regression Suite (534 tests)
pytest backend/tests/ -o pythonpath=backend -q
```

### 6.2 Frontend Tests
Run from the `frontend/` directory:
```bash
# 1. Run Stage 3 Production Behavior & State Reconciliation Tests (57 tests)
npx tsx src/lib/test_elia_stage3_workflow.ts

# 2. Run Panel Feedback, Factor Mapping, and Undo/Redo Tests (7 tests)
npx tsx src/lib/test_elia_panel_feedback.ts

# 3. Run Three.js Geometry & Metric Coordinate Transformation Tests (6 tests)
npx tsx src/lib/test_elia_geometry.mjs
```

---

## 7. Troubleshooting Guide

| Issue / Error Code | Root Cause | Actionable Remediation |
|---|---|---|
| `ELIA_MODEL_UNAVAILABLE` | PyTorch artifact `weights.npz` missing or corrupted. | Check file presence in `backend/app/components/elia_engine/model_artifacts/garden_layout_v1/`. Verify SHA-256 hash against manifest. Run in baseline mode if model is intentionally uninstalled. |
| `ELIA_CONFLICTING_MASTER_FIELDS` | Upstream Master JSON has mismatched coordinate definitions between aliases (e.g. 5-point closed ring vs 4-point polygon). | Ensure upstream polygon fields match; ELIA adapter resolves canonical geometry without fabricating points. |
| `ELIA_STALE_SOURCE_REVISION` (HTTP 409) | The project was modified concurrently between preview generation and save submission. | Reload project context (`GET /context`) to obtain the current revision number and re-submit save with matching `source_revision`. |
| `ELIA_INVALID_CANDIDATE` (HTTP 422) | Proposed candidate violates hard geometric rules (e.g. house collision, boundary overhang, utility separation). | Candidate design is rejected; prior accepted design in database remains strictly unmodified. Inspect `violations` array for specific rule failures. |
| `MySQL Connection Refused (10061)` | Local MySQL server is not running or blocked by firewall. | Start the local MySQL service (`net start MySQL80` on Windows, `systemctl start mysql` on Linux). Alternatively, test suites automatically use isolated in-memory SQLite. |
| `Open-Meteo Timeout / Offline` | External network connectivity to `api.open-meteo.com` unavailable. | System automatically logs provider status `"offline_fallback"` and calculates clear-sky deterministic irradiance based on Master JSON latitude and solar angles without halting generation. |
