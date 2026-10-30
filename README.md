# Component 4: ELIA-Engine (Eco-Spatial Landscape Intelligence)

**Owner / Author:** Prasad P.A.D.H  
**Project:** ArchAI-Plan  
**Module:** Component 4 (`backend/app/components/elia_engine`)

---

## 📌 Executive Summary

**ELIA-Engine (Eco-Spatial Landscape Intelligence)** is Component 4 of the **ArchAI-Plan** platform. It manages ecological, environmental, and exterior landscape architecture for residential developments.

Operating directly on upstream outputs from the Centralized Master JSON (parcel boundary, building footprint, structural openings, orientation, and utility points), ELIA generates deterministic, environmentally sustainable, and regulation-compliant exterior layouts. It plans vehicle access paths, pedestrian walkways, solar photovoltaic arrays, vegetation envelopes, outdoor amenities, exterior lighting, and drainage buffers without fabricating missing evidence.

---

## 🚀 Key Responsibilities & Capabilities

1. **Exterior Residual Space Analysis:**
   - Subtracts the house footprint and reserved utility zones from the total land parcel boundary.
   - Preserves polygon interior holes, courtyards, and verified existing site trees/features.
   - Inherits authoritative orientation (true north bearing) directly from upstream land data without re-detecting or guessing.

2. **Deterministic Geometric Planning & Optimization:**
   - **A\* Ray-Marching Pathfinding:** Plans collision-free vehicular driveways, entry walks, and garden service paths connecting gates, carports, and doorways.
   - **2D Oriented Bounding Box (OBB) Packing:** Optimally places modular exterior assets and rooftop/ground solar photovoltaic (PV) arrays within verified boundary envelopes.
   - **Poisson-Disk Clearance Sampling:** Distributes mature tree canopies, shrubs, groundcover, lighting fixtures, and seating zones respecting physical root/canopy radii and boundary setbacks.
   - **Analytical Directional Solar Simulation:** Simulates diurnal solar trajectories and shadow projections across solstice/equinox periods to verify plant lighting and solar collector placement.

3. **Versioned Exterior Rule Engine (79 Explicit Rules):**
   - **Geometric Validity (25 rules):** Immutability of parcel boundaries, mature canopy clearances, tree preservation zones, utility separation buffers, and OBB collision envelopes.
   - **Elevated Installation (23 rules):** Roof terrace structural capacity gates (`roof_allowance_kg_m2 >= 150`), drainage runoff clearances, guard railing, and vertical greenery safety.
   - **Environmental Suitability (14 rules):** Diurnal solar shadow exposure, wind buffers, and soil moisture compatibility.
   - **Legal Assessment (9 rules):** Municipal boundary clearances, driveway sightlines, and septic tank to drinking well separation buffers.
   - **User Preference Satisfaction (8 rules):** Aesthetic style compliance, species whitelist/blacklist enforcement, and outdoor living features.

4. **Curated Botanical Catalogue:**
   - 14 verified tropical species native/adapted to Sri Lankan climatic conditions with complete botanical metrics (mature height, canopy radius, root depth, growth rate, moisture needs).
   - Structured fallback templates for generic landscape massing.

5. **Safe Master JSON Synthesis & 2D/3D Visualization:**
   - Non-destructive export into the Centralized Master JSON under `exterior_landscape` and `processing.elia_engine`.
   - Real-time 2D canvas layers and Three.js 3D exterior asset visualization.

---

## 🏗️ Architectural Sub-Modules

Located at `backend/app/components/elia_engine/`:

| Sub-module / File | Responsibility |
|---|---|
| `service.py` | Orchestrates the end-to-end ELIA workflow, lifecycle hooks, and project coordination. |
| `schemas.py` | Pydantic data schemas, coordinate representations, and API models. |
| `adapter.py` | Translates upstream Master JSON layers into ELIA's internal spatial domain models. |
| `feasibility.py` | Evaluates site feasibility, slope, residual buildable zones, and environmental constraints. |
| `pathfinding.py` | A* ray-marching algorithm for access roads, pedestrian paths, and driveway circulation. |
| `solar_planner.py` | Rooftop/ground solar panel layout planner, string orientation, and tilt angles. |
| `solar.py` & `shadow.py` | Sun path calculations, solar azimuth/elevation, and shadow ray casting. |
| `plants.py` & `vegetation.py` | Botanical catalog resolution, mature canopy distribution, and root clearance enforcement. |
| `gate_garage.py` | Entrance gate positioning, vehicle turning radius validation, and garage access. |
| `lighting.py` | Nighttime exterior illumination planning, pathway safety fixtures, and ambient lights. |
| `outdoor_elements.py` | Sits, patios, water features, gazebos, and modular landscape asset placement. |
| `rule_registry.py` & `rule_evaluator.py` | Versioned 79-rule evaluation engine scoring compliance across all landscape elements. |
| `elevated_features.py` | Balcony, terrace, and rooftop greening validation with structural load verification. |
| `output.py` | Serializes exterior plans into standard GeoJSON and Master JSON structures. |

---

## 🛠️ Tech Stack & Dependencies

- **Language:** Python 3.11+
- **Spatial Geometry:** Shapely, NumPy, SciPy (Spatial Voronoi / Delaunay, KD-Tree)
- **Grid & Path Planning:** NetworkX, custom A* Ray-Marching
- **API & Schemas:** FastAPI, Pydantic v2
- **Frontend Visualization:** Next.js, Three.js, React Three Fiber

---

## 🔄 End-to-End Execution Pipeline

```text
[Master JSON: Land, House Footprint, Utilities, North]
                         │
                         ▼
           [Input Adapter & Verification]
                         │
                         ▼
        [Residual Exterior Space Computation]
                         │
                         ▼
           [Site Feasibility Assessment]
                         │
                         ▼
   ┌─────────────────────┴─────────────────────┐
   │                                           │
   ▼                                           ▼
[Vehicle & Pedestrian Pathfinding]   [Analytical Solar & Shadow Analysis]
   │                                           │
   ▼                                           ▼
[Gate, Carport & Utility Buffers]    [Solar PV Array Placement (OBB)]
   │                                           │
   └─────────────────────┬─────────────────────┘
                         │
                         ▼
         [Poisson-Disk Vegetation & Lighting]
                         │
                         ▼
       [79-Rule Compliance Engine Evaluation]
                         │
                         ▼
      [Master JSON Update & 2D/3D Synchronization]
```

---

## 🧪 Testing & Verification

To run tests specifically covering Component 4 (ELIA-Engine):

```bash
# Navigate to the backend directory
cd backend

# Run ELIA-Engine test suite
pytest tests/ -k "elia" -v
```

---

## 👤 Author Information

- **Developer:** Prasad P.A.D.H
- **Role:** Component 4 Lead Developer (ELIA-Engine)
- **Project:** ArchAI-Plan Research Project
