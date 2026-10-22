# ELIA Engine — Viva Demonstration Script & Technical Q&A

> **Component 4**: Eco-Spatial Landscape Intelligence (ELIA Engine)  
> **Viva / Defense Presentation Guide**: Step-by-step 12-stage demonstration sequence and concise examiner Q&A answers.

---

## 1. Step-by-Step Viva Demonstration Script (12-Stage Sequence)

| Stage | Action / Step | UI Screen & Controls | Examiner Explanation (What to Say) | Verified System Evidence |
|:---:|---|---|---|---|
| **1** | **Open Active Project** | Select project from platform project dashboard or open `/features/elia-engine?project_id=<id>`. | *"We open an authorized active residential project. ELIA immediately fetches the centralized Master JSON from the backend without prompting the user to upload raw geometry."* | `GET /api/projects/{id}/elia-engine/context` returns 200 with revision number and project name. |
| **2** | **Show Inherited Context** | Three.js Viewer shows site boundary, building footprint, floor plans, and utilities. | *"Notice that the parcel boundary (Component 1), building footprint and roof surfaces (Component 2), and room layout (Component 3) are already fixed and immutable. ELIA treats these as authoritative ground truth."* | Upstream layers displayed with distinct layer toggles. No upload/paste controls exist for Master JSON. |
| **3** | **Configure Preferences** | Set concept to **"Greeny"**, vehicle count to 1, gate required, straight driveway, 4 shade trees, garden seating, solar PV, and balcony greenery. | *"The user configures explicit structured preferences across access, planting, lighting, and solar. ELIA normalizes all units to metric and enforces dependent field consistency."* | Normalized JSON payload reflects metric values (`units: "m"`), with disabled parents cleanly omitting inactive children. |
| **4** | **Show Feasibility Result** | Click **"Check Feasibility"**. Review feasibility summary card. | *"Before executing any generative planning, ELIA evaluates multi-feature spatial feasibility. Total free ground area is not assumed to mean everything fits; setback clearances, utility buffers, and balcony loads are verified together."* | `POST /api/projects/{id}/elia-engine/feasibility` returns `overall_status: "feasible"`, spatial metrics, and zero conflict alerts. |
| **5** | **Plant Selection & Alternatives** | Select a plant species (e.g. `plumeria_obtusa`) from the verified catalogue. Test an alternative suggestion. | *"ELIA queries the verified horticultural catalogue of 21 species. If an unsuitable plant is requested for deep shadow or shallow soil, ELIA suggests alternatives, but never places them without explicit user acceptance."* | `GET /plant-catalogue` filters by category; `POST /plants/alternatives` registers the explicit user acceptance. |
| **6** | **Generate Exterior Layout** | Select **"Trained Model Mode"** and click **"Generate Exterior Design"**. | *"We trigger hybrid generation. A PyTorch Convolutional UNet runs real inference on CPU, converting 9 architectural raster masks into 4 continuous spatial density heatmaps."* | Latency: ~162 ms inference. Returned JSON has `generation_mode: "trained_model"` and `model_version: "elia-garden-layout-v1.0"`. |
| **7** | **Explain Hybrid Division** | Highlight different elements in the result breakdown. | *"We clearly delineate what is learned vs. what is rule-based: Tree canopies, seating zones, and lighting clusters are placed by UNet heatmap peak detection. Gates, driveways, solar racking, and elevated balcony planters are placed by deterministic geometric planners."* | Metrics card confirms exact count of model-placed vs planner-placed elements. |
| **8** | **Inspect Three.js 3D Viewer** | Orbit, pan, and zoom in Three.js viewport. Toggle layers (Trees, Access, Solar, Lighting). | *"In the Three.js viewport, generated elements match the output JSON coordinates with zero offset. Trees render with canopy radius and trunk height; solar panels align coplanar to the pitched roof; boundary walls and driveway corridors are accurately dimensioned."* | Visual rendering aligns with metric coordinate system; boundary holes and fixed house footprint are strictly preserved. |
| **9** | **Review Unmet Conditions** | Open Rule Evaluations tab. Point out any `review_required` or advisory notices. | *"ELIA adheres to a zero-fabrication contract. Because this project lacks a certified structural engineer load schedule for the balcony, Rule B06 flags `review_required`. The candidate is labeled a 'conditional draft' rather than falsely certified as fully compliant."* | 54 rules evaluated. Category summaries distinguish passed rules from advisory planner notices. |
| **10** | **Execute Transactional Save** | Click **"Save Accepted Design"**. | *"When saving, ELIA validates the candidate against the current authoritative context. It executes a two-phase Compare-And-Swap transaction, incrementing the project revision from 1 to 3 and recording an immutable ComponentRun record."* | `POST /save-candidate` returns HTTP 200, revision 3. An immediate duplicate submission yields HTTP 409 conflict. |
| **11** | **Reload & Verify Persistence** | Refresh the browser page or trigger context reload. | *"We reload the page from scratch. The accepted exterior design, selected preferences, and run provenance restore faithfully from the backend database at revision 3."* | Reloaded context matches saved state; prior accepted design was never cleared by temporary state changes. |
| **12** | **Verify Upstream Invariance & Export** | Inspect Master JSON export. Check Component 1–3 layers. | *"Finally, we inspect the exported Master JSON. Component 1 land boundaries, Component 2 house footprints and floor plans, and Component 3 interior layouts are 100% bitwise identical to the original upstream project."* | C1, C2, and C3 geometry fields match original upstream hashes. |

---

## 2. Concise Viva Technical Questions & Answers

### Q1: What is Component 4 (ELIA Engine), and what is its objective?
**Answer**: ELIA (Eco-Spatial Landscape Intelligence) is the exterior design and landscape planning engine for ArchAI-Plan. Its objective is to generate customized, code-compliant, and ecologically viable exterior layouts—including vehicle access, driveways, garden planting, outdoor living, exterior lighting, solar PV, and elevated greenery—conditioned on fixed upstream architectural geometry and explicit client requirements.

### Q2: What data does ELIA inherit from Components 1, 2, and 3?
**Answer**: ELIA inherits:
- **Component 1**: Surveyed land boundary polygon, road-facing edge, calculated north bearing, and length units.
- **Component 2**: Fixed house footprint polygon, roof geometry (slopes, ridges, flat terraces), building elevations, and ground floor plan.
- **Component 3**: Interior layout, room functions, furniture positions, and main entrance coordinates.  
*All upstream data is authoritative and strictly immutable.*

### Q3: What did you train, and what is the model architecture?
**Answer**: We trained a 5-stage Convolutional UNet (`elia-garden-layout-unet`) that takes a $9 \times 96 \times 96$ tensor of normalized architectural raster masks (land, house, road, entrance, utilities, shadows, density, style) and predicts a $4 \times 96 \times 96$ output tensor of spatial probability heatmaps for tree canopies, seating areas, lighting nodes, and path guidance. The model contains 186k parameters and executes CPU forward inference in ~162 ms.

### Q4: What parts of ELIA are rule-based or deterministic, and why?
**Answer**: High-liability structural, circulation, and regulatory elements are deterministic:
- Vehicular gates, straight/curved A* driveways, and pedestrian walkways (governed by road access and turning radii).
- Rooftop solar PV packing (governed by roof pitch, azimuth, and 1.0 m edge setbacks).
- Balcony and terrace planter packing (governed by structural load thresholds).
- The 54-rule validator.  
*Why*: Neural networks cannot guarantee zero-collision or legal compliance; safety must be mathematically validated by deterministic algorithms.

### Q5: Why don't you allow users to upload reference photos or Master JSON files?
**Answer**:
1. User photos are 2D perspectives without metric scale, depth, or boundary coordinates, and do not represent authoritative site geometry.
2. The Master JSON is the centralized platform contract produced by Components 1–3. Allowing user upload or paste would enable bypassing upstream site measurements, breaking data provenance, and introducing fabricated geometry.

### Q6: How do user preferences affect layout generation?
**Answer**: Preferences act as multi-level conditioning:
- Style preferences (Modern, Greeny, Minimalist) are encoded directly into input tensor channels 7 and 8 and filter plant catalogue categories.
- Greenery density scales tensor channel 6 and sets target planting numbers.
- Specific plant IDs are matched against micro-climate suitability.
- Vehicle profiles and counts determine garage dimensions, driveway widths, and turning radius envelopes.

### Q7: How do you prevent collisions with the house, boundaries, and utilities?
**Answer**: Through a three-tier defense:
1. **Raster Masking**: House and utility buffer zones (e.g. 50 ft well-septic separation) are masked out in the input tensor.
2. **Constrained Decoding**: Non-Maximum Suppression (NMS) checks boundary containment (`land.covers(point)`) and foundation setbacks (`distance(house) >= radius`).
3. **54-Rule Validator**: The entire candidate is independently validated before save; any polygon collision triggers immediate rejection (`ELIA_INVALID_CANDIDATE`).

### Q8: What happens when the parcel space is insufficient to fulfill all requests?
**Answer**: ELIA never fabricates space or overlaps elements. During feasibility assessment, it detects spatial conflicts and flags `infeasible`. During layout generation, elements that cannot fit with valid clearances are omitted and recorded in the `unmet_requirements` array, and the layout is saved as a conditional draft rather than an accepted compliant design.

### Q9: How do you handle missing evidence (e.g. unknown roof slope or absent structural certificate)?
**Answer**: Under our strict Zero-Fabrication Contract, missing evidence is evaluated as `unknown` or `review_required`. An unknown check is **never** treated as a pass. If hard legal/engineering evidence is missing, the design is marked `conditional_draft_review_required`.

### Q10: What happens when the model, external API, or database fails?
**Answer**:
- **Model Unavailable / Corrupted**: The system falls back cleanly to the deterministic baseline planner without crashing.
- **Solar API Offline**: The system automatically falls back to clear-sky deterministic irradiance modeling without inventing fake data.
- **Database Concurrency Conflict**: If another process modified the project, ELIA aborts with HTTP 409 (`ELIA_STALE_SOURCE_REVISION`), preserving the prior accepted design.

### Q11: How was the model evaluated, and what were the findings?
**Answer**: The model was evaluated across 5 geometrically distinct held-out residential test sites (rectangular, narrow infill, L-shaped, corner lot, acreage). Compared to a deterministic grid baseline, the hybrid UNet model achieved **95.0% tree requirement satisfaction** (vs 0.0% for grid heuristics on tight plots) and 100% seating satisfaction, with a 162 ms average CPU latency.

### Q12: What are the main limitations and future work?
**Answer**:
1. **Kinematic Turning**: Vehicle turning is estimated via 2D centerline turning radii; full 3D swept-path multi-axle kinematic simulation is out of scope.
2. **2D Model Scope**: The UNet operates in 2D ground space; elevated balcony/rooftop features are planned deterministically.
3. **Future Work**: Integration of 3D point-cloud terrain elevation models, expansion of the botanical catalogue to arid and alpine climate zones, and automated municipal building permit XML export.
