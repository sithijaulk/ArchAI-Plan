# ESAI REST API Contracts

All endpoints are registered on the FastAPI backend under two routers:
- Project Router: `/api/projects/{project_id}/esai-engine`
- Global Knowledge Router: `/api/esai`

## Project Endpoints

### 1. Controlled Run Route (Stage 2 Placeholder)
- **Method**: `POST`
- **Path**: `/api/projects/{project_id}/esai-engine/run`
- **Status**: `501 Not Implemented`
- **Response**:
```json
{
  "detail": "ESAI-Engine Genetic Algorithm optimizer is scheduled for Stage 2. Stage 1 provides complete backend data contracts, geometry validation, requirements persistence, and catalog services."
}
```

### 2. Context & Discovery
- `GET /api/projects/{project_id}/esai-engine/context`
  - Returns project metadata, source units, floor and room counts.
- `GET /api/projects/{project_id}/esai-engine/floors`
  - Returns list of floors with IDs, names, and elevations.
- `GET /api/projects/{project_id}/esai-engine/rooms?floor_id={id}`
  - Returns all rooms (optionally filtered by floor) with parsed polygons, doors, windows, and computed area in m².
- `GET /api/projects/{project_id}/esai-engine/rooms/{room_id}`
  - Returns a single room by ID or 404.

### 3. Client Requirements Persistence
- `GET /api/projects/{project_id}/esai-engine/requirements`
  - Retrieves saved room requirements for the project.
- `PUT /api/projects/{project_id}/esai-engine/requirements`
  - Validates and saves room requirements to MySQL (`esai_room_requirements`) and merges them into `projects.master_json["interior_layout"]`.

### 4. Input Validation
- `POST /api/projects/{project_id}/esai-engine/validate-input`
  - Performs non-mutating validation of the structural floor plan against ESAI geometry rules. Returns structured errors, warnings, and informational notices.

### 5. Saved Configurations CRUD
- `GET /api/projects/{project_id}/esai-engine/configurations`
- `POST /api/projects/{project_id}/esai-engine/configurations`
- `PUT /api/projects/{project_id}/esai-engine/configurations/{config_id}`
- `DELETE /api/projects/{project_id}/esai-engine/configurations/{config_id}`

## Global Knowledge Endpoints
- `GET /api/esai/catalog?category={cat}&room_type={type}`
- `GET /api/esai/catalog/{catalog_id}`
- `GET /api/esai/standards?enforceable_only={bool}`
- `GET /api/esai/room-profiles`
