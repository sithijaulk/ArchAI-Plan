# ESAI-Engine — Stage 1 Backend Architecture

## Overview
Component 3: **ESAI-Engine (Ergonomic Spatial Intelligence AI)** provides ergonomic furniture planning, anthropometric circulation modeling, and spatial requirements management for residential architectural projects.

Stage 1 establishes the complete backend infrastructure without implementing the Genetic Algorithm (GA) optimizer, which is reserved for Stage 2.

## Core Responsibilities & Boundaries
- **Ownership**: ESAI manages client furniture requirements, internal catalog querying, Neufert clearance standard validation, and the `interior_layout` partition of the Centralized Master JSON.
- **Strict Boundary**: ESAI **never** alters room boundary polygons, external walls, structural door/window coordinates, or partitions owned by other components (`land_info`, `buildable_footprint`, `floor_plan`, `structural_rectification`, `exterior_landscape`).
- **Run Endpoint Status**: The `POST /api/projects/{project_id}/esai-engine/run` route returns a controlled **HTTP 501 Not Implemented** until Stage 2.

## Key Modules
- [contracts.py](file:///backend/app/components/esai_engine/contracts.py): Canonical DTOs, Enums, coordinate models, and unit conversion logic.
- [parser.py](file:///backend/app/components/esai_engine/parser.py): Immutable structural input parser reading the Centralized Master JSON.
- [normalizer.py](file:///backend/app/components/esai_engine/normalizer.py): Floor and room discovery helpers.
- [catalog.py](file:///backend/app/components/esai_engine/catalog.py): In-memory singleton loader for the typed furniture catalog.
- [rules.py](file:///backend/app/components/esai_engine/rules.py): Neufert / Architects' Data standards loader enforcing verification flags.
- [geometry.py](file:///backend/app/components/esai_engine/geometry.py): Deterministic 2D Shapely geometry functions (bounding boxes, area, containment, collision).
- [openings.py](file:///backend/app/components/esai_engine/openings.py): Door and window geometry and clearance envelopes.
- [validators.py](file:///backend/app/components/esai_engine/validators.py): Cross-validation of client requests against catalog, rules, and spatial geometry.
- [repositories.py](file:///backend/app/components/esai_engine/repositories.py): SQLAlchemy database persistence for room requirements, design preferences, and saved configurations.
- [service.py](file:///backend/app/components/esai_engine/service.py): Domain service orchestrating backend operations.
