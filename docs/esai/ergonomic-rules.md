# Neufert & Ergonomic Standards Reference

## Standards Provenance
All clearances and physical dimensions are drawn from verified architectural authorities:
- **Ernst Neufert**: *Architects' Data*, 4th International Edition.
- **Julius Panero & Martin Zelnik**: *Human Dimension & Interior Space: A Source Book of Design Reference Standards*.
- **ADA Standards**: *Accessible and Usable Buildings and Facilities*.

## Rule Verification Hierarchy
Every rule in [ergonomic_rules.json](file:///backend/app/components/esai_engine/data/ergonomic_rules.json) contains an explicit `verification_status`:
- `verified`: Formally cited from Neufert or standard anthropometric literature; enforceable as a hard/soft constraint.
- `recommended`: Standard industry practice guidelines.
- `unverified`: Experimental or internal draft guidelines; **not enforceable as mandatory compliance constraints** until verified.

## Standard Clearance Rules in ESAI
| Rule ID | Applicable Categories | Direction | Minimum Threshold | Source Reference | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `BED_ACCESS_PRIMARY` | `bed` | both_sides | 0.70 m (700 mm) | Neufert 4th Ed. — Bedrooms | `verified` |
| `BED_ACCESS_SECONDARY` | `bed` | left / side | 0.55 m (550 mm) | Neufert 4th Ed. — Single Beds | `verified` |
| `WARDROBE_HINGED_FRONT` | `wardrobe` | front | 0.90 m (900 mm) | Neufert 4th Ed. — Wardrobes | `verified` |
| `WARDROBE_SLIDING_FRONT` | `wardrobe` | front | 0.75 m (750 mm) | Panero & Zelnik — Storage | `verified` |
| `LIVING_SOFA_FRONT` | `sofa`, `armchair` | front | 0.40 m (400 mm) | Neufert 4th Ed. — Seating | `verified` |
| `DINING_CHAIR_PULLOUT` | `dining_table` | all_sides | 0.80 m (800 mm) | Neufert 4th Ed. — Dining | `verified` |
| `DESK_CHAIR_MOVEMENT` | `desk`, `workstation` | front | 0.90 m (900 mm) | Neufert 4th Ed. — Desks | `verified` |
| `KITCHEN_WORK_CLEARANCE` | `kitchen_counter` | front | 1.05 m (1050 mm) | Neufert 4th Ed. — Kitchens | `verified` |
| `KITCHEN_AISLE_CLEARANCE` | `kitchen_island` | all_sides | 1.20 m (1200 mm) | Neufert 4th Ed. — Islands | `verified` |
| `BATH_COMMODE_CLEARANCE` | `commode` | front | 0.60 m (600 mm) | Neufert 4th Ed. — Bathrooms | `verified` |
| `BATH_BASIN_FRONT` | `basin` | front | 0.70 m (700 mm) | Neufert 4th Ed. — Washbasins | `verified` |
| `BATH_SHOWER_ENTRY` | `shower_enclosure` | front | 0.70 m (700 mm) | Neufert 4th Ed. — Showers | `verified` |
| `GENERAL_CIRCULATION` | `other`, `side_table` | circulation | 0.75 m (750 mm) | Neufert 4th Ed. — Corridors | `verified` |
| `ACCESSIBLE_CIRCULATION` | `all` | circulation | 0.90 m (900 mm) | ADA / Neufert Barrier-Free | `verified` |
| `CUSTOM_EXPERIMENTAL_CLEARANCE` | `other` | front | 0.50 m (500 mm) | Draft Research Internal | `unverified` |
