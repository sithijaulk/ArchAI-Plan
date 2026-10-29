# ESAI Client Requirements Schema

## Overview
Clients can configure per-room furniture demands, custom dimensions, priorities, locked items, and overall project interior preferences.

## Room Requirements Payload
```json
{
  "room_id": "RM_MBED_01",
  "floor_id": "GF",
  "room_type": "master_bedroom",
  "furniture_density": "standard",
  "circulation_priority": "standard",
  "accessibility_profile": "standard",
  "items": [
    {
      "instance_id": "req_bed_01",
      "catalog_id": "BED_KING_01",
      "category": "bed",
      "quantity": 1,
      "is_required": true,
      "priority": "hard",
      "allowed_rotations": [0, 90, 180, 270],
      "preferred_walls": ["north"],
      "user_locked": false,
      "material_preference": "wood_oak",
      "color_finish": "natural_wood"
    },
    {
      "instance_id": "req_side_01",
      "catalog_id": "NIGHTSTAND_01",
      "category": "bedside_table",
      "quantity": 2,
      "is_required": true,
      "priority": "soft"
    }
  ],
  "notes": "Prefer king bed placed opposite master bathroom door."
}
```

## Hard vs Soft Constraints
- **Hard Constraints**: Ergonomic safety, non-overlapping footprints, door swing clearance, room polygon containment.
- **Soft Preferences**: Aesthetic alignments, secondary clearances, visual styling, color finishes.
- Client style preferences are never allowed to override physical or ergonomic safety clearances.
