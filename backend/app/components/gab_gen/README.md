# GAB-Gen (Geo-Spatial AI Blueprint Generator) Backend Module

Component 1 of ArchAI-Plan.

## Sub-module Architecture & Responsibilities

- **input/**: Deed/survey upload metadata, client requirement validation, land size, scale, storey count, room programme, input normalization.
- **survey_vision/**: Future Stage-2 image preprocessing, candidate line detection, EasyOCR integration, north/orientation detection, survey text extraction.
- **measurement_association/**: OCR text-to-edge association, spatial proximity, orientation matching, confidence/consistency checks.
- **vector_reconstruction/**: Bearing normalization, trigonometric coordinate reconstruction, ordered X-Y land vertices, closure calculations, reconstructed land geometry.
- **regulations/**: Structured regulatory-rule loading, rule source metadata, edge classification, setback configuration.
- **buildable_footprint/**: Shapely-based legal/buildable region generation.
- **space_allocation/**: Deterministic Stage-1 allocation interface, later Stage-2 XGBoost inference adapter.
- **blueprint/**: Floor definitions, room polygon generation, wall segment generation, baseline structural geometry.
- **validation/**: Geometry validation, area validation, containment, room requirement validation, safe-failure reporting.
- **output/**: GAB-Gen Master JSON construction, serialization, export preparation.
- **adapters/**: Common project/database integration, model abstraction interfaces, rendering/API adapters.
- **data/**: Local component data storage placeholder.
- **model_runtime/**: Future Stage-2 model loaders, model version metadata, EasyOCR runtime adapter, XGBoost runtime adapter.
