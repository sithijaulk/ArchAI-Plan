# GAB-Gen Compliance Validation Architecture & Engine Specification

**Document Version:** 1.0.0  
**Effective Date:** 2026-10-20  
**Component:** Component 1 — GAB-Gen (Geo-Spatial AI Blueprint Generator)  
**Strict Prohibition:** No budget estimation, bill of quantities, construction cost calculation, or financial optimization.

---

## 1. Compliance Architecture Overview

GAB-Gen decouples layout generation from deterministic legal validation:
```
┌─────────────────────────────────┐
│ Client Requirements & Land Deed │
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│ Mathematical Geometry Engine    │ -> Canonical P0 vector coordinates, closure check
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│ Jurisdiction Resolver           │ -> Western Province 47 LAs, UDA vs CMC
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│ Deterministic Buildable Engine  │ -> Edge-aware setbacks, street lines, coverage
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│ Space Allocation & Candidate    │ -> AI / Rule-based candidate floor plans
│ Floor Plan Generator            │
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│ Independent Regulatory Checker  │ -> Evaluates 100% of applicable rules:
│ (Deterministic Engine)          │    - Room areas & minimum widths (Schedule 7)
│                                 │    - Floor clear heights (Reg. 67)
│                                 │    - Stair widths, risers & treads (Schedule 8)
│                                 │    - Natural ventilation & light (Reg. 70)
│                                 │    - Air well & light well sizes (Schedule 10)
│                                 │    - Parking stall geometry (Schedule 11/12)
│                                 │    - Maximum coverage & rear space (Schedule 6)
│                                 │    - Roof terrace guard walls & heights (Reg. 57/67)
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│ Centralized Master JSON Synthes.│ -> Machine-readable & human-readable reports
└─────────────────────────────────┘
```

---

## 2. Hard Legal Constraints vs. Optimization Preferences

| Constraint Category | Regulatory Source | Parameter / Threshold | Engine Action |
|---|---|---|---|
| **Front Setback** | UDA Gaz. 2235/54 Sched. 3 / CMC By-law 12 | 3.0 m (Standard Access Road) | **Hard Boundary Clip** |
| **Rear Space** | UDA Gaz. 2235/54 Sched. 6 Form C / CMC Form C2 | 2.3 m (<= 2 floors) / 3.0 m (3-4 floors) | **Hard Boundary Clip** |
| **Side Setback** | UDA Gaz. 2235/54 Sched. 6 Form C / CMC Form C2 | 1.0 m (Openings) / 0.0 m (Blind wall GF) | **Hard Boundary Clip** |
| **Max Plot Coverage** | UDA Gaz. 2235/54 Sched. 6 Form C / CMC Form C2 | Max 65% for residential plots | **Hard Capacity Bound** |
| **Single Dwelling Room** | UDA Gaz. 2235/54 Sched. 7 (a) | Min 11.0 m², Min width 3.0 m | **Hard Room Check** |
| **Primary Bedroom** | UDA Gaz. 2235/54 Sched. 7 (b)(i) | Min 9.5 m², Min width 2.5 m | **Hard Room Check** |
| **Additional Bedroom** | UDA Gaz. 2235/54 Sched. 7 (b)(ii) | Min 8.5 m², Min width 2.5 m | **Hard Room Check** |
| **Kitchen** | UDA Gaz. 2235/54 Sched. 7 (d) | Min 5.5 m², Min width 1.8 m | **Hard Room Check** |
| **Bathroom / Toilet** | UDA Gaz. 2235/54 Sched. 7 (e)-(g) | Min 1.7 m² (toilet) / 2.0 m² (combined), Min width 1.0 m / 1.5 m | **Hard Room Check** |
| **Ceiling Height** | UDA Gaz. 2235/54 Reg. 67(1) | Habitable rooms avg >= 2.8m, min >= 2.4m; toilets/corridors >= 2.1m | **Hard Elevation Check** |
| **Staircase Geometry** | UDA Gaz. 2235/54 Sched. 8 | Min width 750mm (residential), Max riser 175mm, Min tread 250mm, Headroom 2.1m | **Hard Stair Core Check** |
| **Natural Light/Vent.** | UDA Gaz. 2235/54 Reg. 70(2) | Openings >= 20% floor area for habitable, >= 10% for utilities | **Hard Opening Check** |
| **Air Well (Light Well)** | UDA Gaz. 2235/54 Sched. 10 | Habitable rooms min clear width 3.0m, min area 9.0 m²; Utility rooms min 1.0m width, min 1.0 m² area | **Hard Spatial Check** |
| **Vehicle Parking** | UDA Gaz. 2235/54 Sched. 11 & 12 | 1 stall per unit (stall 2.5m × 5.0m, aisle >= 3.6m to 6.0m) | **Hard Parking Check** |
| **Roof Terrace Guard Wall** | UDA Gaz. 2235/54 Reg. 57(3) | Min 2.0m guard wall on adjoining boundary, 1.0m safety parapet elsewhere | **Hard Roof Check** |
