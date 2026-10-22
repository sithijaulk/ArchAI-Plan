# ESAI Integration & Stage 2 Handoff Specification

## Stage 1 Current Status
- **FastAPI Backend**: Fully operational with ESAI routers included.
- **PostgreSQL Persistence**: Handled via `projects.master_json["interior_layout"]` and dedicated tables (`esai_room_requirements`, `esai_design_preferences`, `esai_saved_configs`). Alembic migration `002_esai_engine.py` is present.
- **Master JSON Preservation**: Structural inputs (`floor_plan`, `buildable_footprint`, `land_info`, etc.) are immutable and strictly preserved.
- **Controlled 501 Endpoint**: `/api/projects/{project_id}/esai-engine/run` returns HTTP 501 until GA implementation.

## Exact Stage 2 Integration Entry Points
Stage 2 will implement the Genetic Algorithm (GA) furniture placement optimizer using PyGAD / Shapely. The exact integration points are:

1. **Service Entry Point**:
   - Class: [EsaiEngineService](file:///backend/app/components/esai_engine/service.py)
   - Method: `run_optimization(project_id: str, room_id: str, config: Optional[dict]) -> dict`
   - Will consume `RoomDTO`, `DoorDTO`, `WindowDTO` from [parser.py](file:///backend/app/components/esai_engine/parser.py), client requirements from [requirements.py](file:///backend/app/components/esai_engine/requirements.py), and constraints from [rules.py](file:///backend/app/components/esai_engine/rules.py).

2. **Router Trigger Point**:
   - File: [esai.py](file:///backend/app/routers/esai.py)
   - Function: `run_esai_engine(project_id: str, db: Session)`
   - Replace HTTP 501 with async / background execution of `service.run_optimization()`.

3. **Master JSON Serialized Output Format for Stage 2**:
   When the optimizer completes, it will write generated placements into `master_json["interior_layout"]["rooms"][room_id]["furniture_layout"]`:
   ```json
   {
     "furniture_layout": [
       {
         "instance_id": "req_bed_01",
         "catalog_id": "BED_KING_01",
         "position": {"x": 2.5, "y": 1.0},
         "rotation": 0,
         "dimensions": {"width": 1.93, "depth": 2.03, "height": 0.6},
         "clearance_polygon": [...]
       }
     ],
     "fitness_score": 0.94,
     "metrics": {
       "collision_overlap_area": 0.0,
       "circulation_compliance": 1.0,
       "door_clearance_preserved": true
     }
   }
   ```
