# GAB-Gen Component Documentation

**Component 1: Geo-Spatial AI Blueprint Generator**  
*Research Initiative: ArchAI-Plan*  
*Active Branch:* `feature/gab-gen`

---

## 1. Actual Implemented Architecture

```
User Input & Survey Upload
   ├── PDF / JPG / PNG File Validation & Pillow verification
   ├── Location & Authority selection (Province, District, Local Authority)
   ├── Land & Scale Input (Perches, Acres, Sq.Ft, Sq.M; Drawing Scale 1:N)
   └── Building Programme & Counts (Bedrooms, Bathrooms, Living, Kitchen)
           │
           ▼
Survey Vision Pipeline (OpenCV + EasyOCR)
   ├── PyMuPDF PDF-to-image rasterization
   ├── Denoising (Bilateral), CLAHE contrast, Otsu binarization
   ├── Line segment detection (HoughLinesP) & deskew angle detection
   ├── EasyOCR text & bounding box extraction
   └── Measurement Associator (lines <-> distances, bearings, north, road edge)
           │
           ▼
Verification & Provenance Interface
   ├── Visual verification table with provenance tags (`ocr`, `image_geometry`, `user`)
   ├── Live 2D vector preview in Canonical P0 coordinate system
   └── User confirmation required before generation
           │
           ▼
Regulatory Rules Engine
   ├── Contextual rule resolution (UDA Sri Lanka Gazette 2235/54, CMC by-laws)
   ├── Traceable metadata (version, effective date, review date, official reference)
   └── Zero fallback fabrication (returns configuration_required if rules missing)
           │
           ▼
Buildable Footprint & Space Allocation Engine
   ├── Canonical P0 polygon reconstruction with vector closure checking
   ├── Edge-aware setback clipping via Shapely
   ├── Rule-based multi-storey allocation (1-4 floors) with capacity protection
   └── Deterministic proportional spatial partitioning & wall segment derivation
           │
           ▼
Interactive Blueprint Editor & Previews
   ├── 2D interactive plan with clickable room selection and nudge movement
   ├── Real-time constraint checking (buildable containment, room overlaps)
   ├── 3D Three.js extrusion with exploded-storey inspection
   └── Non-destructive Master JSON synchronization
```

---

## 2. Installation & Prerequisites

### Backend Dependencies
- Python 3.11+
- Virtual environment: `backend/.venv`
- Packages: `fastapi`, `uvicorn`, `sqlalchemy`, `shapely`, `pillow`, `pymupdf`, `opencv-python-headless`, `easyocr`, `torch`, `torchvision`, `pytest`, `httpx`

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install opencv-python-headless pymupdf easyocr torch torchvision pytest httpx
```

### Frontend Dependencies
- Node.js 18+
- Packages: Next.js 14, Three.js, @react-three/fiber, @react-three/drei, Lucide React, Zustand, Axios

```bash
cd frontend
npm install
```

---

## 3. Starting the Services

### Backend:
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```
Backend Swagger Documentation: `http://localhost:8000/docs`

### Frontend:
```bash
cd frontend
npm run dev
```
Application interface: `http://localhost:3000/features/gab-gen`

---

## 4. Running Automated Tests

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -v
```
All **25 tests** pass (vector geometry, unit conversion, logical requirement consistency, rule metadata, buildable collapse detection, multi-storey allocation, and room editing constraints).

---

## 5. How Survey & Deed Plans Are Processed

1. **Upload:** User uploads deed/survey plan image (JPG, PNG) or PDF document. File payload is verified for magic bytes and format integrity.
2. **Auto-Extract (EasyOCR):** User can click **"Auto-Extract from Deed (EasyOCR)"** in Step 3. The backend rasterizes PDFs, applies bilateral filtering and Otsu binarization, runs EasyOCR, extracts text/bbox confidence, detects line angles with Hough transforms, and pairs distances and bearings with boundary edges.
3. **Verification:** The user inspects the extracted boundary table. Provenance is preserved (`ocr` vs `user`). If measurements are ambiguous, flags are raised and the user corrects them directly.

---

## 6. How Regulatory Rules Are Selected & Validated

1. Based on the selected Province, District, and Local Authority (e.g. Colombo Municipal Council), `RegulatoryEngine.resolve_jurisdiction` resolves the governing regulatory context.
2. Official rules (UDA Extraordinary Gazette No. 2235/54, CMC Building By-laws) are loaded with complete metadata: version, review date, and source clauses.
3. Front setback (3.0m), rear clearance (2.3m), and side setbacks (1.0m) are applied specifically per edge classification.
4. If no verified rule covers the jurisdiction, the engine halts with `regulatory_configuration_required` rather than fabricating synthetic legal constraints.

---

## 7. How Blueprints Are Generated, Edited, and Saved

1. **Generation:** Reconstructs canonical polygon at origin P0 (0,0), subtracts edge-specific setbacks, calculates buildable footprint, places staircase cores consistently across floors, and partitions remaining usable space proportionally to room requirements.
2. **Editing:** In the 2D Vector view, the user clicks on any room polygon. A pink selection indicator activates with directional move buttons (`←`, `→`, `↑`, `↓`).
3. **Live Constraint Checking:** Any room move is validated through `POST /projects/{id}/gab-gen/edit-room`. If the room crosses the buildable footprint boundary or overlaps with another room by > 0.1 m², the modification is blocked with a descriptive constraint violation message. Valid edits immediately update walls, areas, and Master JSON.

---

## 8. Current Limitations & Unimplemented Features

- **XGBoost AI Model:** Intentionally not trained yet. The rule-based deterministic allocator serves as the baseline until trained models are vetted.
- **Complex Curved Deed Boundaries:** Reconstructor currently supports linear polyline boundaries. Curved cadastre arcs require arc-segment discretization in future iterations.
- **Blind Wall Permits:** Automated blind-wall boundary clearance exemptions require neighbor consent documentation.

---

## 9. Preparation for Future XGBoost Model Training

The feature schema, data dictionary, targets, and split strategies are formally codified in:
`training/gab_gen/schema.py`

Prerequisites before training begins:
1. Empirical cadastre and residential dataset collection.
2. Stratified training/validation/test splits (70/15/15) with fixed random seed (`42`).
3. Baseline evaluation against the current deterministic rule-based benchmark.
