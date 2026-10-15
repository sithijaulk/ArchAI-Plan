# ESAI Structural Input Contract

## Overview
ESAI parses structural room polygons, doors, windows, and fixed obstructions from the Centralized Master JSON (`floor_plan` block).

## Canonical Units & Coordinate Conventions
- **Canonical Distance Unit**: Meters (`m`).
- **Supported Input Units**:
  - `m` (meters) — factor: 1.0
  - `cm` (centimeters) — factor: 0.01
  - `mm` (millimeters) — factor: 0.001
  - `ft` (feet) — factor: 0.3048
  - `in` (inches) — factor: 0.0254
- **Axes Convention**:
  - Horizontal floor plan coordinates use `X` and `Y`.
  - Elevation/ceiling height uses `Z`.
  - Rotations are in degrees: `0°`, `90°`, `180°`, `270°`.

## Input Mapping Formats
ESAI supports both multi-floor formats (`floor_plan.floors[]`) and direct single-floor formats (`floor_plan.rooms[]`).

```json
{
  "project_id": "proj_123",
  "project_name": "Modern Residence",
  "unit": "m",
  "floor_plan": {
    "floors": [
      {
        "floor_id": "GF",
        "floor_name": "Ground Floor",
        "elevation": 0.0,
        "rooms": [
          {
            "room_id": "RM_MBED_01",
            "name": "Master Bedroom",
            "room_type": "master_bedroom",
            "ceiling_height": 2.8,
            "polygon": [[0.0, 0.0], [5.0, 0.0], [5.0, 4.2], [0.0, 4.2]],
            "doors": [
              {
                "id": "D1",
                "start": [0.0, 0.8],
                "end": [0.0, 1.7],
                "leaf_width": 0.9,
                "hinge": "left",
                "opening_direction": "inward",
                "swing_angle": 90.0,
                "protected_depth": 0.9
              }
            ],
            "windows": [
              {
                "id": "W1",
                "start": [2.0, 4.2],
                "end": [3.5, 4.2],
                "length": 1.5,
                "sill_height": 0.9,
                "height": 1.2,
                "opening_type": "sliding",
                "protected_access_depth": 0.6
              }
            ],
            "fixed_obstructions": []
          }
        ]
      }
    ]
  }
}
```

## Validation Rules
- Polygon must have >= 3 vertices.
- Polygon rings must be valid without self-intersections.
- Room area must be strictly positive (> 0.0001 m²).
- Units must be known and convert explicitly to meters.
