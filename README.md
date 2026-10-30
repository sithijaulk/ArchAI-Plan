# Component 1: GAB-Gen (Geo-Spatial AI Blueprint Generator)

**Owner / Author:** H.Y.K. Sithumini  
**Project:** ArchAI-Plan  
**Module:** Component 1 (`backend/app/components/gab_gen`)

---

## 📌 Executive Summary

**GAB-Gen (Geo-Spatial AI Blueprint Generator)** is the foundational module (Component 1) of the **ArchAI-Plan** system. It bridges the gap between raw legal survey/deed documents and generative architectural layout planning. 

The module extracts boundary and measurement details from land surveys, performs mathematically rigorous coordinate reconstruction, validates geometric properties against land extent declarations, enforces local authority setback and building regulations, computes legal buildable footprints, and deterministically allocates spaces into room polygons and multi-storey floor plans. 

All generated geometry and architectural parameters are packed and exported via the standardized **Master JSON** contract, serving as the single source of truth for downstream modules (VSAI-Rectifier, ESAI-Engine, and ELIA-Engine).

---

## 🚀 Key Responsibilities & Capabilities

1. **Survey Ingestion & Parsing:**
   - Ingestion of survey/deed plan scans, PDFs, and manual boundary entries.
   - Assisted extraction of boundary edge lengths and bearings using OpenCV preprocessing and EasyOCR.
   - Interactive verification workflows allowing user review and refinement of boundary segments.

2. **Mathematical Vector Reconstruction:**
   - Canonical $P_0(0,0)$ origin coordinate reconstruction using trigonometric boundary traverses.
   - Conversion across standard land units (Perches, Square Feet, Square Meters, Acres, Hectares).
   - Strict closure error calculations and validation (ensuring valid, closed, non-self-intersecting 2D polygons via Shapely).
   - Declared area cross-checks against mathematically reconstructed areas with configurable tolerances.

3. **Regulatory Compliance & Rule Engine:**
   - Deterministic zoning and municipal setback resolution (e.g., UDA - Urban Development Authority regulations).
   - Road widening reservations, front setbacks, rear boundary setbacks, and lateral side clearance calculations.
   - Edge classification (Street/Road frontages, Rear edges, Side boundaries).

4. **Buildable Footprint Computation:**
   - Shapely geometric setback buffering and negative offset slicing.
   - Elimination of non-buildable pockets and resolution of minimum buildable envelopes.

5. **Space Allocation & Multi-Floor Blueprint Generation:**
   - Target room requirements translation (Bedrooms, Living, Dining, Kitchen, Bathrooms, Stairwells, Corridors).
   - Multi-storey floor plan distribution respecting structural alignments (vertical stair alignment across levels).
   - Wall segment derivation (thicknesses, internal/external boundaries, door/window openings).

6. **Validation & Master JSON Synthesis:**
   - Auditable spatial validation ensuring containment within the buildable footprint.
   - Non-destructive updates to the project's **Master JSON** file.

---

## 🏗️ Architectural Sub-Modules

Located at `backend/app/components/gab_gen/`:

| Directory | Sub-module | Primary Responsibility |
|---|---|---|
| `input/` | Survey & Client Input | Validates uploaded survey scans, deed details, client room requirements, storey counts, and scale. |
| `survey_vision/` | Survey Vision & OCR | Preprocesses survey plan images, extracts candidate boundary line vectors, orientation/north marks, and text blocks. |
| `measurement_association/` | Measurement Matching | Pairs OCR text/numbers with corresponding boundary line segments based on spatial proximity and orientation. |
| `vector_reconstruction/` | Vector Geometry Reconstruction | Solves polygon traverse coordinates $(X_i, Y_i)$, evaluates closure, and verifies polygon sanity. |
| `regulations/` | Regulatory Rules Engine | Resolves jurisdictional zoning bylaws, road reservations, and minimum setbacks. |
| `buildable_footprint/` | Buildable Area Computation | Clips parcel boundary polygons with regulatory setbacks to form the legal building envelope. |
| `space_allocation/` | Space Allocation Engine | Rule-based algorithm partitioning the buildable area into functional living zones and rooms. |
| `blueprint/` | Blueprint Generation | Constructs rooms, wall segments, door/window openings, and floor definitions. |
| `validation/` | Spatial & Regulatory Validator | Executes strict geometry sanity checks, area thresholds, room containment, and safe failure reporting. |
| `output/` | Master JSON Builder | Builds and serializes the GAB-Gen payload into the ArchAI-Plan Master JSON document. |
| `adapters/` | System Adapters | Database abstractions, router bindings, and API adapters for the FastAPI framework. |
| `model_runtime/` | ML & Model Runtime | Model adapters and runtime integration for OCR and future machine learning layout enhancements. |

---

## 🛠️ Tech Stack & Dependencies

- **Language:** Python 3.11+
- **API Framework:** FastAPI, Uvicorn, Pydantic
- **Geometry & Spatial Analysis:** Shapely, NumPy, SciPy
- **Computer Vision & OCR:** OpenCV (`cv2`), EasyOCR, Pillow
- **Data Serialization & Validation:** Pydantic v2, JSON Schema

---

## 🔄 End-to-End Execution Pipeline

```text
[Survey Scan / Deed Entry]
           │
           ▼
[EasyOCR & Line Detection] ──> [Measurement Association]
                                           │
                                           ▼
                            [Vector Traverse Reconstruction]
                                           │
                                           ▼
                          [Land Geometry & Closure Validation]
                                           │
                                           ▼
                           [Regulatory Setback Computation]
                                           │
                                           ▼
                              [Legal Buildable Footprint]
                                           │
                                           ▼
                            [Deterministic Space Allocation]
                                           │
                                           ▼
                           [Floor & Room Blueprint Generation]
                                           │
                                           ▼
                             [Master JSON Output Generator]
```

---

## 🧪 Testing & Verification

To run tests specifically covering Component 1 (GAB-Gen):

```bash
# Navigate to the backend directory
cd backend

# Run GAB-Gen test suite
pytest tests/ -k "gab" -v
```

---

## 👤 Author Information

- **Developer:** H.Y.K. Sithumini
- **Role:** Component 1 Lead Developer (GAB-Gen)
- **Project:** ArchAI-Plan Research Project
