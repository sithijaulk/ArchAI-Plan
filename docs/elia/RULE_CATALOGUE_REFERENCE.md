# ELIA Engine — Rule Engine & Botanical Catalogue Reference

> **Component 4**: Eco-Spatial Landscape Intelligence (ELIA Engine)  
> **Rule Engine Version**: `2.1`  
> **Total Versioned Rules**: 54 Explicit Rules  
> **Botanical Catalogue Version**: `2.1` (21 Verified Residential Species)

---

## 1. Rule Architecture & Evaluation Model

The ELIA Rule Engine provides automated, independent verification of exterior layouts. It evaluates candidates against 54 explicit rules without delegating safety checks to uncalibrated neural activations.

### 1.1 Five Evaluation Categories
Every rule belongs to one of five core categories:
1. **Geometric Validity**: Physical boundaries, obstacle non-intersection, land containment, and coordinate validity.
2. **Environmental Suitability**: Sunlight exposure, shadow aspect, climate zone match, and water availability.
3. **Legal Assessment**: Road reserve setbacks, gate access clearances, boundary wall height limits, and utility safety buffers.
4. **Elevated Installation**: Structural load schedules on balconies and slabs, parapet heights, and rooftop edge setbacks.
5. **User Preference**: Satisfaction of requested species counts, style alignments, seating presence, and material selections.

### 1.2 Four Rule Evaluation Classes
- **Legal Rules**: Hard regulatory constraints derived from planning guidelines (e.g. UDA Planning Regulations Sri Lanka, CEB solar interconnection guidelines). Violations block acceptance (`approval_status="blocked"`).
- **Engineering Rules**: Physical safety clearances (e.g. 50 ft well-to-septic separation, turning radius feasibility, structural load thresholds). Violations block acceptance.
- **Planner Rules**: Architectural good-practice heuristics (e.g. tree canopy separation, shaded seating locations). Failure flags `review_required`.
- **Data-Quality Rules**: Coordinate validity, finite numbers, unit declarations, and schema compliance. Failure raises HTTP 422.

---

## 2. Missing-Evidence Contract & Status Semantics

ELIA enforces a strict **Zero-Fabrication Contract**:
- Missing upstream evidence (e.g., absent structural engineer certificate, missing soil test, or unknown roof slope) is evaluated as **`unknown`** or **`review_required`**.
- **`unknown` is NEVER treated as `pass`**.
- **Hard Safety Rule Failure**: Generates `approval_status="blocked"`. Saving as an accepted design is strictly rejected by the backend.
- **Missing Structural / Verification Evidence**: When basic geometry passes but professional certification is absent, candidate status becomes `approval_status="conditional_draft_review_required"`. The user may inspect the 3D preview, but the layout is clearly designated as a conditional draft requiring professional sign-off.
- **Legal Disclaimer**: Generic distances and setback guidelines in the rule engine are configurable rules-of-thumb based on standard urban development codes. They do **not** substitute for certified professional engineer (PE), geotechnical, or licensed land surveyor approval.

---

## 3. The 54 Versioned Rules Inventory

| Rule Group | ID Range | Focus & Scope | Representative Rules | Hard vs Advisory |
|---|---|---|---|---|
| **A: Access & Circulation** | A01 – A06 | Gate position, driveway width, turning radius, walkway connectivity, garage clearance. | A01 (Gate on road), A02 (Driveway clearance), A03 (Walkway path continuity) | Hard (A01, A02), Advisory (A04) |
| **G: Geometric Validity** | G01 – G05 | Boundary containment, zero building overlap, non-negative dimensions, coordinate finiteness. | G01 (No house intersection), G02 (Boundary containment), G04 (Valid polygon) | Hard (All G rules) |
| **B: Balconies & Terraces** | B01 – B10 | Balcony load capacity, saturated soil weight, door clearance, railing height. | B01 (Load limit), B06 (Waterproofing check), B09 (Drainage & structural review) | Hard (B01), Review Required (B06, B09) |
| **R: Roof & Elevated** | R01 – R05 | Rooftop access, roof perimeter setback, structural suitability for green roof/terrace. | R01 (Accessible roof status), R03 (Parapet safety clearance) | Review Required (R01, R03) |
| **V: Vegetation & Flora** | V01 – V06 | Mature canopy clearance, root setback from foundations, climate zone match, sunlight adequacy. | V01 (Canopy overlap boundary), V02 (Root foundation distance), V04 (Sunlight match) | Hard (V01, V02), Advisory (V04) |
| **W: Walls & Fences** | W01 – W04 | Boundary wall height compliance, sightline clearance at corners, vertical greenery attachment. | W01 (Maximum wall height), W02 (Corner visibility triangle) | Hard (W02), Advisory (W01) |
| **X: Solar PV Racking** | X01 – X11 | Rooftop setback (1.0m edge clearance), pitch/azimuth orientation, shadow avoidance. | X10 (Rooftop perimeter buffer), X11 (Coplanar vs tilted racking clearance) | Hard (X10), Advisory (X11) |
| **U: Utilities & Health** | U01 – U04 | 50 ft (15.24 m) separation between water wells and septic tanks, drain clearances. | U01 (Well-septic separation distance), U02 (Relocation permission verification) | Hard (U01, U02) |
| **C: Concept Alignment** | C01 – C04 | Material palette conformity, greenery ratio matching client concept (Modern, Greeny, Minimalist). | C01 (Concept style flora mix), C02 (Hardscape-to-softscape balance) | Advisory (All C rules) |

---

## 4. Verified Plant Catalogue Specification (Version 2.1)

The ELIA botanical catalogue (`backend/app/components/elia_engine/data/vegetation_catalog.json`) contains **21 residential species** calibrated for tropical and subtropical climates (e.g. Sri Lankan Low Country Wet, Intermediate, and Dry zones).

### 4.1 Catalogue Schema & Verified Attributes
Each entry contains empirically verified horticultural parameters:
- `vegetation_id`: Unique canonical string identifier (e.g. `areca_catechu`, `mesua_ferrea`, `plumeria_obtusa`).
- `category`: Classification (`shade_tree`, `small_tree`, `shrub`, `ground_cover`, `climber`, `cascading_creeper`, `planter`).
- `display_name` & `scientific_name`: Common English / Sinhala name and botanical binomial.
- `climate_suitability`: Array of viable agro-ecological zones (`wet_zone`, `intermediate_zone`, `dry_zone`, `coastal`).
- `sun_requirement`: `full_sun`, `partial_shade`, or `shade_tolerant`.
- `water_demand`: `low`, `moderate`, or `high`.
- `maintenance_level`: `low`, `moderate`, or `high`.
- `mature_height_m`: Typical mature tree/shrub height in meters.
- `canopy_radius_m`: Radius of mature foliage crown (governs geometric boundary setback Rule V01).
- `root_clearance_m`: Recommended lateral separation from structural foundations and underground pipes (Rule V02).
- `vertical_suitability`: Boolean indicating whether species is suitable for vertical green wall trellis.
- `planter_suitability`: Boolean indicating whether species can thrive in elevated balcony containers (Rule B01).
- `verified_species_data`: Boolean flag distinguishing real verified botanical data from generic placeholders.

### 4.2 Verified Species Inventory

| Vegetation ID | Category | Common Name | Botanical Name | Canopy Radius (m) | Foundation Clearance (m) | Planter Suitable? |
|---|---|---|---|:---:|:---:|:---:|
| `areca_catechu` | `small_tree` | Areca Palm (Puwak) | *Areca catechu* | 1.5 | 2.0 | No |
| `plumeria_obtusa` | `small_tree` | White Frangipani (Araliya) | *Plumeria obtusa* | 2.0 | 2.5 | Yes (large) |
| `azadirachta_indica` | `shade_tree` | Neem (Kohomba) | *Azadirachta indica* | 4.0 | 4.5 | No |
| `mesua_ferrea` | `shade_tree` | Ironwood (Na) | *Mesua ferrea* | 3.5 | 4.0 | No |
| `lagerstroemia_speciosa` | `shade_tree` | Queen's Crape Myrtle (Muruta) | *Lagerstroemia speciosa* | 3.5 | 3.5 | No |
| `bougainvillea_spectabilis`| `climber` | Great Bougainvillea | *Bougainvillea spectabilis* | 1.0 | 1.0 | Yes |
| `heliconia_psittacorum` | `shrub` | Parakeet Flower | *Heliconia psittacorum* | 0.8 | 1.0 | Yes |
| `codiaeum_variegatum` | `shrub` | Garden Croton (Kosamba) | *Codiaeum variegatum* | 0.7 | 0.8 | Yes |
| `ixora_sri_lanka` | `shrub` | Jungle Flame (Rathambala) | *Ixora coccinea* | 0.6 | 0.6 | Yes |
| `murraya_paniculata` | `shrub` | Orange Jessamine (Etteriya) | *Murraya paniculata* | 1.0 | 1.2 | Yes |
| `nephrolepis_exaltata` | `ground_cover`| Boston Fern | *Nephrolepis exaltata* | 0.4 | 0.3 | Yes |
| `ophiopogon_japonicus` | `ground_cover`| Mondo Grass | *Ophiopogon japonicus* | 0.2 | 0.2 | Yes |
| `portulaca_grandiflora` | `ground_cover`| Moss Rose | *Portulaca grandiflora* | 0.2 | 0.2 | Yes |
| `bougainvillea_glabra` | `climber` | Lesser Bougainvillea | *Bougainvillea glabra* | 1.0 | 0.8 | Yes |
| `cascading_creeper` | `cascading_creeper`| Generic Curtain Creeper | *Vernonia elaegnifolia* | 0.5 | 0.5 | Yes |

---

## 5. Plant Alternatives & Suitability Workflow

1. **Suitability Evaluation (`POST /plants/evaluate-suitability`)**:
   - Compares plant environmental requirements (sunlight, soil volume, climate) against parcel conditions at proposed placement position.
   - If unsuitable (e.g. shade tree proposed in deep building shadow, or invasive roots near septic tank), marks status as `unsuitable` and returns up to 3 compatible alternatives from the verified catalogue.
2. **Explicit User Acceptance (`POST /plants/alternatives`)**:
   - Alternatives are **never automatically accepted or placed**.
   - The user must explicitly submit a decision (`"accept"` or `"reject"`).
   - Accepting an alternative does not automatically approve the final layout; the candidate must still pass the 54-rule validator.
