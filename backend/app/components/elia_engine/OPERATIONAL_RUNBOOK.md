# ELIA Engine — Operational Runbook

> Component 4: Eco-Spatial Landscape Intelligence (ELIA Engine)  
> Environment: Windows (PowerShell) & Linux/macOS (bash)

This runbook documents operational procedures for backend startup, regression testing, isolated PostgreSQL testing, and live baseline verification for Component 4 (ELIA Engine).

---

## 1. Environment Activation

### Windows (PowerShell)
```powershell
# Navigate to backend directory
cd C:\Users\MY\OneDrive\Desktop\research\ArchAI-Plan\backend

# Activate the dedicated virtual environment
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS (bash)
```bash
cd backend
source .venv/bin/activate
```

---

## 2. Starting the Backend Process

The backend is built with FastAPI and served via Uvicorn.

```powershell
# Windows PowerShell
.\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Readiness Verification
```powershell
# Check process readiness
curl.exe -s http://localhost:8000/api/health
# Expected: {"status":"ok","app":"ArchAI-Plan","env":"development"}
```
> [!NOTE]
> `/api/health` verifies process and HTTP server availability; it does not verify PostgreSQL connectivity.

---

## 3. Running Regression & Contract Tests

All unit, contract, and SQLite regression tests run with pytest:

```powershell
# Run full repository test suite
.\.venv\Scripts\python -m pytest tests -q

# Run all ELIA-specific tests (unit, geometry, parser, lighting, service, api, contracts, operational)
.\.venv\Scripts\python -m pytest -k elia -v

# Run dedicated Stage 1 contract verification tests
.\.venv\Scripts\python -m pytest tests/test_elia_stage1_contracts.py -v

# Run dedicated Stage 2 operational lifecycle tests
.\.venv\Scripts\python -m pytest tests/test_elia_stage2_operational.py -v
```

---

## 4. Running the Isolated PostgreSQL Integration Test

The PostgreSQL persistence integration test ([`tests/test_elia_postgres_integration.py`](../../../tests/test_elia_postgres_integration.py)) is opt-in and requires an active PostgreSQL server and disposable test database.

### Prerequisites
1. A running PostgreSQL server (local daemon or Docker container).
2. A designated disposable test database (e.g. `elia_test_db`).

### Execution Command
```powershell
# Set process-scoped environment variable (do not commit real credentials)
$env:ELIA_TEST_POSTGRES_URL="postgresql+psycopg2://<DB_USER>:<DB_PASSWORD>@localhost:5432/<TEST_DB_NAME>"

# Run the PostgreSQL integration test
.\.venv\Scripts\python -m pytest tests/test_elia_postgres_integration.py -v

# Clear the environment variable after testing
Remove-Item env:ELIA_TEST_POSTGRES_URL
```

> [!CAUTION]
> Never point `ELIA_TEST_POSTGRES_URL` at a production or primary development database containing user data.

---

## 5. Live Baseline Operational Verification

To verify the live flow against an active backend process with a real upstream project:

```powershell
# Run non-destructive live verification
.\.venv\Scripts\python scripts/verify_elia_operational.py `
  --base-url http://localhost:8000 `
  --token "<ADMIN_JWT_TOKEN>" `
  --project-id "<REAL_PROJECT_ID>"

# Include live baseline persistence and reload verification:
.\.venv\Scripts\python scripts/verify_elia_operational.py `
  --base-url http://localhost:8000 `
  --token "<ADMIN_JWT_TOKEN>" `
  --project-id "<REAL_PROJECT_ID>" `
  --live-run
```

---

## 6. Frontend Geometry & Contract Verification

To verify frontend coordinate mappings, hole preservation, vegetation dimensions, and view model extraction:

```powershell
cd C:\Users\MY\OneDrive\Desktop\research\ArchAI-Plan\frontend
npx tsx src/lib/test_elia_geometry.mjs
```
