# ELIA Engine — Eco-Spatial Landscape Intelligence

Component 4: Eco-Spatial Landscape Intelligence (ELIA Engine) in ArchAI-Plan.

ELIA plans exterior residential space from an authoritative upstream Centralized Master JSON. Production generation operates on a deterministic **Rules + Geometric Layout Planner / Optimizer** architecture.

Production generation does not depend on trained neural models, model weights (`weights.npz`), image classifiers, Colab checkpoints, or user-uploaded reference photos.

## Architecture and Core Algorithms

The production planning pipeline follows:
Authoritative project geometry + explicit user preferences
→ Preference normalization and scope validation
→ Feasibility screening and applicable rule selection
→ Deterministic geometric layout generation and optimization:
  - **A\* Ray-Marching Pathfinding**: Generates collision-free driveways, pedestrian walkways, and maintenance corridors.
  - **2D Oriented Bounding Box (OBB) Packing**: Packs solar photovoltaic arrays and modular exterior elements within verified boundary envelopes.
  - **Poisson-Disk Clearance Sampling**: Distributes vegetation crown envelopes, seating nodes, and outdoor lighting while respecting mature spread radii and physical setback zones.
  - **Analytical Directional Solar Simulation**: Samples diurnal sun positions and shadow projections across equinox/solstice ranges.
→ Final multi-category geometry and rule validation (79 versioned rules)
→ Safe candidate editing with undo history, form synchronization, and 3D translation gizmo
→ Centralized Master JSON `exterior_landscape` update and frontend 2D/3D visualization.

Production generation does NOT use neural networks or genetic algorithms. Historical experimental artifacts remain strictly isolated and labeled non-production.

## Coordinates, Orientation, and Evidence Standards

All planning geometry is converted to meters. `units` at the Master JSON root declares its source length unit; when absent, the project default is meters. Latitude and longitude must be supplied in the request or the Master JSON; ELIA never guesses a site location.

ELIA consumes an existing constructed-house exterior footprint and land boundary; a buildable zone is not a substitute for the house footprint. The input adapter accepts `land_info.mathematical_polygon`, legacy boundary fields, and supported house-exterior fields from the floor-plan and structural layers. It maps `floor_plan.ground_floor.utilities.water_well` and `septic_tank` (`center`, `position`, or `x`/`y` coordinates). Polygon interior rings (holes) are strictly preserved.

North is inherited from the upstream Master JSON (`land_info.calculated_north_bearing` or `north_angle`). ELIA does not redetect north. The normalized angle is degrees clockwise from local `+Y` toward local `+X`; zero means local `+Y` is north. Conflicting angles or missing required orientation produce explicit validation errors.

### Zero-Fabrication Solar & Elevated Geometry Contract
- Roof surfaces must be authoritatively defined in Master JSON (`house.roof.surfaces` or `roof_faces`).
- ELIA never invents missing roof elevation (no 6m default), missing pitch (no 20°/0° default), or missing azimuth (no 180° default).
- Missing roof parameters produce an actionable `status="evidence_missing"` requirement, not proven infeasibility.
- Structural certification requires verifiable professional evidence (`roof_allowance_kg_m2 >= 150` and an engineer license or report reference); bare booleans are rejected.
- Uncertified solar proposals are presented as provisional geometric previews (`approval_status="provisional_review_required"`), keeping them distinct from accepted authoritative installations.
- All placed module footprints are preserved with stable IDs, coordinates, dimensions (`width_m`, `length_m`), tilt, and azimuth.

## Versioned Exterior Rule Engine (v2.1 Registry)

The registry defines **79 explicit, versioned exterior rules** across 5 evaluation categories:
- **Geometric Validity (25 rules)**: Upstream boundary immutability, polygon containment, mature canopy clearances, tree preservation, utility setback buffers, and OBB collision envelopes.
- **Elevated Installation (23 rules)**: Balcony/terrace load allowances, drainage runoff, guard routes, extensive vs accessible rooftop planting, and structural certification gates.
- **Environmental Suitability (14 rules)**: Solar shadow analysis, wind exposure, soil moisture drainage, and species climate compatibility.
- **Legal Assessment (9 rules)**: Setback regulations, boundary clearances, well/septic separation screening, and road access widths.
- **User Preference Satisfaction (8 rules)**: Style concept satisfaction, plant inclusion/exclusion enforcement, lighting styles, and actionable remedy explanations.

### Rule Applicability and Evaluation Contract
- **Not all rules evaluate for every request**: Rules are triggered strictly according to applicable target elements and project context. Elevated rules only evaluate when balconies/terraces/roofs are present; sanitation rules only evaluate when septic/well infrastructure is documented.
- **Rule Outcomes**: `pass`, `fail`, `unknown`, `not_applicable`, `review_required`.
- **Evidence Integrity**: Missing evidence remains `unknown` or `review_required`; unknown evidence NEVER counts as a pass.
- **Enforcement Consequence**: Hard boundary and physical violations block acceptance (`approval_status="blocked"`). Uncertified elevated proposals remain provisional drafts (`approval_status="provisional_review_required"`).

### Vegetation Catalogue v2.1
The authoritative plant catalogue contains exactly **21 entries**:
- **14 Verified Sri Lankan Species**: Documented with botanical research citations S1–S12, mature height, canopy radius, root depth, growth rate, and climate tolerance (*Portulaca grandiflora*, *Nephrolepis exaltata*, *Ixora ‘Sri Lanka’*, *Murraya paniculata*, *Bougainvillea glabra*, *Lagerstroemia speciosa*, etc.).
- **7 Generic Placeholder Templates**: Clearly flagged with `is_generic=true` and null botanical measurements, used solely for geometric envelope planning without claiming verified botanical suitability.

## API Specification

Supported Generation Modes:
- `rules_planner` (Default / Production): Deterministic rule-based layout optimizer.
- `baseline` (Alias for `rules_planner`).
- Requests specifying unsupported neural modes return HTTP 400 with `UNSUPPORTED_GENERATION_MODE`.

Project Endpoints (Require authenticated administrator role):
- `POST /api/projects/{project_id}/elia-engine/run` — Executes ELIA exterior planning and persists accepted candidate to Master JSON via compare-and-swap revision locking.
- `GET /api/projects/{project_id}/elia-engine/context` — Fetches current project geometry, upstream revision, and existing exterior state.
- `POST /api/projects/{project_id}/elia-engine/validate-input` — Pre-validates requirements and upstream geometry.
- `GET /api/projects/{project_id}/elia-engine/result` — Retrieves latest accepted exterior landscape.
- `GET /api/projects/{project_id}/elia-engine/solar/current` — Retrieves live Open-Meteo weather estimates and pvlib solar position.
- `POST /api/elia-engine/preview` — Non-persisted preview generator for instant feedback.

## Persistence and Database

- **Production Database**: Application persistence uses **MySQL** via SQLAlchemy (`mysql+pymysql://`), enforcing transaction safety, monotonic revision increments (`source_revision`), and optimistic concurrency control (CAS).
- **Test Database**: Unit and component tests run on isolated in-memory SQLite schemas. Live MySQL integration tests are opt-in and require `ELIA_TEST_MYSQL_URL`.
