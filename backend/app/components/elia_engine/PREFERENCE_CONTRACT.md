# Component 4 — ELIA Engine: User Preferences Contract (Stage 1)

This document specifies the authoritative preference contract for ELIA Engine (Component 4). It defines the exact mapping between frontend controls, canonical API fields, normalization semantics, generation capabilities, and persistence behavior.

---

## 1. Precedence and Input Semantics

The ELIA preference evaluation follows a strict four-level precedence hierarchy:

```
Authoritative geometry & hard constraints (Land boundaries, road-side, north, house polygon, existing surveyed utilities)
  ↓
Explicit user selections (Form inputs explicitly submitted by the user)
  ↓
Concept defaults (Suggested defaults derived from Design Concept, e.g., Modern, Greeny, Minimalistic)
  ↓
Planner defaults (Fallback engineering defaults, e.g., default gate width 3.6m, driveway width 3.0m)
```

### Value States

Values are strictly distinguished across five distinct states — absent, false, zero, null, and auto are never conflated:

| State | Representation | Semantics |
|---|---|---|
| **Not requested** | Absent / undefined | Feature toggle is not active. Dependent child fields are omitted from request. |
| **Explicitly disabled** | `false` | User actively disabled the feature (e.g., `garage_required: false`). |
| **Enabled with value** | `true` with numeric/string value | Feature is enabled and configured (e.g., `vehicle_count: 2`). |
| **Auto / No preference** | `"auto"`, `"no_preference"` | User delegates choice to spatial planner/concept. |
| **Unknown / Not provided**| `null`, `"unknown"` | Information is unverified or absent; requires site assessment. |

---

## 2. Preference Contract Matrix (Groups A – K)

### Group A: Design Concept

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Design Concept | `design_style` | string enum: `"modern"`, `"greeny"`, `"minimalistic"` | None | `"modern"` | None | `vegetation.py`, `rule_evaluator.py`, `service.py`, `model_adapter.py` | Supported. Affects target planting density, open space, and rule evaluation. | Persisted in `requirements.design_style` and `master_json.processing.elia_engine.theme_concept`. Legacy alias `"minimalist"` normalizes to `"minimalistic"`, `"contemporary"` normalizes to `"modern"`. |

*Note: Changing concept never silently overwrites user-edited values. Users can explicitly click "Reapply Concept Defaults" to reset fields to concept defaults.*

---

### Group B: Parking and Garage

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Vehicle Parking Required | `access.parking_required` | `boolean` | None | `true` | None | `gate_garage.py`, `service.py` | Supported. | Persisted in `requirements.access.parking_required`. |
| Number of Vehicles | `access.vehicle_count` | `integer` (>= 1 when parking required, or 0) | count | `1` | `access.parking_required == true` | `gate_garage.py`, `validator.py` | Supported. | Persisted in `requirements.access.vehicle_count`. |
| Vehicle Profiles / Types | `access.vehicle_profiles` | `list[VehicleProfileInput]` (`vehicle_type`: `"car"`, `"compact_car"`, `"suv"`, `"van"`, `"custom"`) | None | `[{"vehicle_type": "car"}]` | `access.parking_required == true` | `gate_garage.py`, `vehicle_access.py` | Supported. Dimension catalogue verified from `vehicle_profiles.json`. | Persisted in `requirements.access.vehicle_profiles`. |
| Garage Required | `access.garage_required` | `boolean` | None | `false` | `access.parking_required == true` | `gate_garage.py`, `service.py` | Supported. Placed within residual space with road access. | Persisted in `requirements.access.garage_required`. |
| Parking Type Preference | `access.parking_type` | string enum: `"garage"`, `"covered"`, `"open"`, `"no_preference"` | None | `"no_preference"` | `access.parking_required == true` | `gate_garage.py`, `rule_evaluator.py` | Supported (garage vs open space). Covered canopy requires verified structure. | Persisted in `requirements.access.parking_type`. |
| Garage Capacity | `access.garage_capacity` | `integer` (1 to 3 in baseline; up to 10 in model) | count | `1` | `access.garage_required == true` | `gate_garage.py`, `validator.py` | Supported. Validated against residual building footprint. | Persisted in `requirements.access.garage_capacity`. Omitted when `garage_required == false`. |
| Turning Space Required | `access.turning_space_required` | `boolean` | None | `true` | `access.parking_required == true` | `gate_garage.py`, `vehicle_access.py` | Supported (2D turning radius geometry check). | Persisted in `requirements.access.turning_space_required`. |

*Validation Contradictions: Zero vehicle count (`vehicle_count == 0`) with `garage_required == true` or `garage_capacity > 0` is strictly rejected with `ELIA_CONTRADICTORY_REQUIREMENTS`.*

---

### Group C: Driveway, Walkways, and Gate

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Driveway Required | `access.driveway_required` | `boolean` | None | `true` | None | `gate_garage.py`, `service.py` | Supported. | Persisted in `requirements.access.driveway_required`. |
| Driveway Style | `access.driveway_style` | string enum: `"auto"`, `"straight"`, `"curved"` | None | `"auto"` | `access.driveway_required == true` | `gate_garage.py` | Supported (straight/auto pathfinding; curved reported as preference). | Persisted in `requirements.access.driveway_style`. |
| Driveway Surface Material | `access.driveway_surface` | string enum: `"interlock"`, `"paving_stones"`, `"concrete"`, `"gravel"`, `"grass"`, `"asphalt"`, `"mixed"` | None | `"interlock"` | `access.driveway_required == true` | `service.py`, `output.py` | Supported (metadata/surface attribute). | Persisted in `requirements.access.driveway_surface`. |
| Pedestrian Access Path Required | `landscape.pedestrian_path_required` | `boolean` | None | `false` | None | `outdoor_elements.py`, `pathfinding.py` | Supported. Generates walkway from gate to main entrance. | Persisted in `requirements.landscape.pedestrian_path_required`. |
| Garden Walking Paths Required | `landscape.garden_path_required` | `boolean` | None | `false` | None | `outdoor_elements.py`, `pathfinding.py` | Supported. Generates garden stroll paths. | Persisted in `requirements.landscape.garden_path_required`. |
| Walking Path Surface | `access.walking_path_surface` | string enum: `"paving_stones"`, `"interlock"`, `"gravel"`, `"stepping_stones"`, `"grass"`, `"mixed"` | None | `"paving_stones"` | `pedestrian_path_required == true` or `garden_path_required == true` | `outdoor_elements.py` | Supported (pathway surface attribute). | Persisted in `requirements.access.walking_path_surface`. |
| Gate Required | `access.gate_required` | `boolean` | None | `true` | None | `gate_garage.py` | Supported. | Persisted in `requirements.access.gate_required`. |
| Gate Type | `access.gate_type` | string enum: `"sliding"`, `"swing"`, `"bi_fold"`, `"unspecified"` | None | `"unspecified"` | `access.gate_required == true` | `gate_garage.py`, `rule_evaluator.py` | Supported. Evaluated against road boundary and clearance. | Persisted in `requirements.access.gate_type`. |
| Gate Opening Mechanism | `access.gate_opening_mechanism` | string enum: `"swing_inward"`, `"swing_outward"`, `"sliding"`, `"bi_fold"`, `"manual"`, `"automated"`, `"unspecified"` | None | `"unspecified"` | `access.gate_required == true` | `gate_garage.py`, `rule_evaluator.py` | Supported for inward/sliding; outward opening flagged under boundary clearance rule. | Persisted in `requirements.access.gate_opening_mechanism`. |
| Gate Width Preference | `access.gate_width_m` | `FiniteFloat` (min 1.0, max 10.0) | meters | `3.6` | `access.gate_required == true` | `gate_garage.py` | Supported. Scaled to meters; verified against road boundary edge length. | Persisted in `requirements.access.gate_width_m`. |
| Gate Appearance / Style | `access.gate_style` | string enum: `"modern_slat"`, `"wrought_iron"`, `"solid_timber"`, `"mesh"`, `"minimalist"`, `"unspecified"` | None | `"unspecified"` | `access.gate_required == true` | `gate_garage.py` | Captured as aesthetic preference (render styling). | Persisted in `requirements.access.gate_style`. |

---

### Group D: Ground Finishes

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Garden Ground Finish | `landscape.garden_ground_finish` | string enum: `"grass"`, `"interlock"`, `"paving_stones"`, `"mixed"` | None | `"grass"` | `landscape.garden_required == true` | `service.py`, `rule_evaluator.py` | Supported. | Persisted in `requirements.landscape.garden_ground_finish`. |
| Lawn Required | `landscape.lawn_required` | `boolean` | None | Derived from `garden_ground_finish == "grass"` or explicit | `landscape.garden_required == true` | `service.py` | Supported. | Persisted in `requirements.landscape.lawn_required`. |
| Open Space Ratio | `landscape.preferred_open_space_ratio` | `FiniteFloat` (0.0 to 1.0) | ratio | `None` (concept default) | None | `service.py`, `rule_evaluator.py` | Captured and assessed in factors assessment. Exact geometry optimization is Stage 2. | Persisted in `requirements.landscape.preferred_open_space_ratio`. |

*Ground Finish Combination: Distinct preferences are maintained for vehicle driveway (`access.driveway_surface`), pedestrian walkways (`access.walking_path_surface`), and garden zones (`landscape.garden_ground_finish`). Users can select interlock/paving on driveways and paths while maintaining grass in garden areas without redrawing polygons.*

---

### Group E: Garden and Ground Planting

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Garden Required | `landscape.garden_required` | `boolean` | None | `true` | None | `service.py`, `vegetation.py` | Supported. | Persisted in `requirements.landscape.garden_required`. |
| Greenery Density | `landscape.greenery_density` | string enum: `"low"`, `"medium"`, `"high"` | None | `"medium"` | `landscape.garden_required == true` | `vegetation.py`, `rule_evaluator.py` | Supported. Determines target plant node counts and spacing. | Persisted in `requirements.landscape.greenery_density`. |
| Trees Required | `landscape.trees_required` | `boolean` | None | `true` | `landscape.garden_required == true` | `vegetation.py` | Supported. | Persisted in `requirements.landscape.trees_required`. |
| Desired Tree Quantity | `landscape.tree_quantity` | `integer` (>= 0) or `null` | count | `null` (auto based on density) | `landscape.trees_required == true` | `vegetation.py` | Supported. | Persisted in `requirements.landscape.tree_quantity`. |
| Compact Trees Preference | `landscape.compact_trees_preference` | `boolean` | None | `false` | `landscape.trees_required == true` | `vegetation.py` | Supported (prioritizes `small_tree` category). | Persisted in `requirements.landscape.compact_trees_preference`. |
| Shade Tree Preference | `landscape.shade_tree_preference` | `boolean` | None | `false` | `landscape.trees_required == true` | `vegetation.py` | Supported (places `shade_tree` in high afternoon-sun zones). | Persisted in `requirements.landscape.shade_tree_preference`. |
| Shrubs Required | `landscape.shrubs_required` | `boolean` | None | `false` | `landscape.garden_required == true` | `vegetation.py` | Supported (`shrub` category). | Persisted in `requirements.landscape.shrubs_required`. |
| Shrubs Quantity | `landscape.shrubs_quantity` | `integer` (>= 0) or `null` | count | `null` | `landscape.shrubs_required == true` | `vegetation.py` | Supported. | Persisted in `requirements.landscape.shrubs_quantity`. |
| Flower Beds Required | `landscape.flower_beds_required` | `boolean` | None | `false` | `landscape.garden_required == true` | `vegetation.py` | Supported (`ground_cover` nodes). | Persisted in `requirements.landscape.flower_beds_required`. |
| Ground Planters / Pots Required | `landscape.ground_planters_required` | `boolean` | None | `false` | `landscape.garden_required == true` | `vegetation.py`, `outdoor_elements.py` | Supported (`planter` category). | Persisted in `requirements.landscape.ground_planters_required`. |
| Ground Planters Count | `landscape.ground_planters_count` | `integer` (>= 0) or `null` | count | `null` | `landscape.ground_planters_required == true` | `vegetation.py` | Supported. | Persisted in `requirements.landscape.ground_planters_count`. |
| Garden Seating Required | `landscape.garden_seating_required` | `boolean` | None | `false` | `landscape.garden_required == true` | `outdoor_elements.py` | Supported (places bench/chair in shade). | Persisted in `requirements.landscape.garden_seating_required`. |
| Garden Seating Count | `landscape.garden_seating_count` | `integer` (>= 0) | count | `1` | `landscape.garden_seating_required == true` | `outdoor_elements.py` | Supported. | Persisted in `requirements.landscape.garden_seating_count`. |
| Garden Table Set Required | `landscape.garden_table_set_required` | `boolean` | None | `false` | `landscape.garden_required == true` | `outdoor_elements.py` | Supported. | Persisted in `requirements.landscape.garden_table_set_required`. |
| Garden Table Set Count | `landscape.garden_table_set_count` | `integer` (>= 0) | count | `1` | `landscape.garden_table_set_required == true` | `outdoor_elements.py` | Supported. | Persisted in `requirements.landscape.garden_table_set_count`. |
| Maintenance Preference | `landscape.maintenance_preference` | string enum: `"low"`, `"medium"`, `"high"`, `"no_preference"` | None | `"no_preference"` | None | `vegetation.py`, `rule_evaluator.py` | Supported. Filters botanical catalogue entries by maintenance level. | Persisted in `requirements.maintenance_preference`. |
| Preferred Plant Catalogue IDs | `landscape.preferred_plant_ids` | `list[string]` | None | `[]` | None | `vegetation.py` | Supported. Strictly validated against `vegetation_catalog.json` stable IDs. | Persisted in `requirements.preferred_plant_ids`. |
| Plant Catalogue IDs to Avoid | `landscape.plant_ids_to_avoid` | `list[string]` | None | `[]` | None | `vegetation.py` | Supported. Strictly filtered out during plant selection. | Persisted in `requirements.plant_ids_to_avoid`. |

---

### Group F: Walls and Vertical Greenery

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Boundary Wall Required | `landscape.boundary_wall_required` | `boolean` | None | `false` | None | `outdoor_elements.py`, `service.py` | Supported. Aligned along property boundary. | Persisted in `requirements.landscape.boundary_wall_required`. |
| Boundary Wall Type | `landscape.boundary_wall_type` | string enum: `"masonry"`, `"rendered_brick"`, `"green_wall"`, `"timber_fence"`, `"retaining_wall"`, `"chain_link"`, `"unspecified"` | None | `"masonry"` | `boundary_wall_required == true` | `outdoor_elements.py` | Supported. | Persisted in `requirements.landscape.boundary_wall_type`. |
| Boundary Wall Height | `landscape.boundary_wall_height_m` | `FiniteFloat` (0.5 to 6.0) | meters | `1.8` | `boundary_wall_required == true` | `outdoor_elements.py`, `shadow.py` | Supported. Converted to meters; casts shadow in simulation. | Persisted in `requirements.landscape.boundary_wall_height_m`. |
| Wall Climbing Plants | `vertical_greenery.wall_climbing_plants` | `boolean` | None | `false` | `vertical_greenery.enabled == true` | `vertical_greenery.py` | Supported (`climber` nodes on exterior building walls). | Persisted in `requirements.vertical_greenery.wall_climbing_plants`. |
| Wall Mounted Greenery | `vertical_greenery.wall_mounted_greenery` | `boolean` | None | `false` | `vertical_greenery.enabled == true` | `vertical_greenery.py` | Supported (wall planter brackets). | Persisted in `requirements.vertical_greenery.wall_mounted_greenery`. |
| Hanging / Trailing Greenery | `vertical_greenery.hanging_trailing_greenery` | `boolean` | None | `false` | `vertical_greenery.enabled == true` | `vertical_greenery.py` | Supported (`cascading_creeper` on suitable vertical surfaces). | Persisted in `requirements.vertical_greenery.hanging_trailing_greenery`. |
| Willingness to Consider Vertical Alternatives | `vertical_greenery.accept_vertical_alternatives` | `boolean` | None | `false` | None | `vertical_greenery.py`, `service.py` | Supported. Allows planner to fallback to vertical greenery when ground space is constrained. | Persisted in `requirements.vertical_greenery.accept_vertical_alternatives`. |

---

### Group G: Balcony Preferences

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Balcony Planting Required | `balconies.planting_required` | `boolean` | None | `false` | Balcony surfaces exist in Master JSON | `service.py`, `model_adapter.py` | **Preference capture complete; generation unsupported.** 2D exterior planner does not place balcony furniture. Explicitly reported in `unsupported_preferences`. | Persisted in `requirements.balconies.planting_required`. |
| Potted Plants | `balconies.potted_plants` | `boolean` | None | `false` | `balconies.planting_required == true` | `service.py` | **Unsupported generation.** | Persisted in `requirements.balconies.potted_plants`. |
| Hanging / Trailing Plants | `balconies.hanging_plants` | `boolean` | None | `false` | `balconies.planting_required == true` | `vertical_greenery.py` | Supported when attached to valid balcony elevation; otherwise reported unsupported. | Persisted in `requirements.balconies.hanging_plants`. |
| Balcony Seating Required | `balconies.seating_required` | `boolean` | None | `false` | Balcony surfaces exist in Master JSON | `service.py` | **Unsupported generation.** Reported in `unsupported_preferences`. | Persisted in `requirements.balconies.seating_required`. |
| Target Balcony IDs | `balconies.target_balcony_ids` | `list[string]` | None | `[]` | Balcony surfaces exist | `service.py`, `model_adapter.py` | Associated with actual `json_id` from `master.balconies`. | Persisted in `requirements.balconies.target_balcony_ids`. |

---

### Group H: Rooftop / Terrace Preferences

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Rooftop Planting Required | `terrace.planting_required` | `boolean` | None | `false` | Terrace surfaces exist in Master JSON | `service.py`, `model_adapter.py` | **Preference capture complete; layout generation unsupported in 2D engine.** Explicitly reported in `unsupported_preferences`. | Persisted in `requirements.terrace.planting_required`. |
| Rooftop Planters / Pots | `terrace.planters_required` | `boolean` | None | `false` | `terrace.planting_required == true` | `service.py` | **Unsupported generation.** | Persisted in `requirements.terrace.planters_required`. |
| Rooftop Seating Required | `terrace.seating_required` | `boolean` | None | `false` | Terrace surfaces exist in Master JSON | `service.py` | **Unsupported generation.** | Persisted in `requirements.terrace.seating_required`. |
| Rooftop Tables Required | `terrace.tables_required` | `boolean` | None | `false` | Terrace surfaces exist in Master JSON | `service.py` | **Unsupported generation.** | Persisted in `requirements.terrace.tables_required`. |
| Target Terrace IDs | `terrace.target_terrace_ids` | `list[string]` | None | `[]` | Usable flat terrace exists | `service.py` | Associated with actual terrace surfaces from Master JSON. | Persisted in `requirements.terrace.target_terrace_ids`. |

---

### Group I: Outdoor Lighting

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Outdoor Lighting Required | `lighting.required` | `boolean` | None | `false` | None | `lighting.py`, `service.py` | Supported. | Persisted in `requirements.lighting.required`. |
| Lighting Style | `lighting.style` | string enum: `"minimal"`, `"bollard"`, `"spotlight"`, `"lantern"`, `"strip"` | None | `"minimal"` | `lighting.required == true` | `lighting.py` | Supported. Strictly validated against `lighting_rules.json`. | Persisted in `requirements.lighting.style`. |
| Garden Lighting Zone | `lighting.garden_lighting` | `boolean` | None | `false` | `lighting.required == true` | `lighting.py` | Supported (maps to `"garden"` zone). | Persisted in `requirements.lighting.garden_lighting`. |
| Pathway Lighting Zone | `lighting.pathway_lighting` | `boolean` | None | `false` | `lighting.required == true` | `lighting.py` | Captured as preference intent (flagged if pathway zone unmounted). | Persisted in `requirements.lighting.pathway_lighting`. |
| Seating Area Lighting Zone | `lighting.seating_lighting` | `boolean` | None | `false` | `lighting.required == true` | `lighting.py` | Supported (maps to `"seating"` zone). | Persisted in `requirements.lighting.seating_lighting`. |
| Boundary Wall Lighting Zone| `lighting.wall_lighting` | `boolean` | None | `false` | `lighting.required == true` | `lighting.py` | Supported (maps to `"boundary_wall"` zone). | Persisted in `requirements.lighting.wall_lighting`. |
| Preferred Fixture Spacing | `lighting.preferred_spacing_m`| `FiniteFloat` (gt 0) | meters | `8.0` | `lighting.required == true` | `lighting.py` | Supported. Must meet configured minimum spacing. | Persisted in `requirements.lighting.preferred_spacing_m`. |
| Desired Fixture Count | `lighting.desired_fixture_count` | `integer` (>= 0) or `null` | count | `null` | `lighting.required == true` | `lighting.py` | Supported as planning guideline. When specified alongside spacing, spacing takes precedence. | Persisted in `requirements.lighting.desired_fixture_count`. |

---

### Group J: Water Features and Utilities

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Well Required | `water_features.well_required` | `boolean` | None | `false` | None | `utility_safety.py`, `service.py` | **Preference capture complete; automated well placement unsupported.** Does NOT alter existing surveyed well. Reported in `unsupported_preferences`. | Persisted in `requirements.water_features.well_required`. |
| Garden Taps Required | `water_features.garden_taps_required` | `boolean` | None | `false` | None | `service.py` | **Preference capture complete; plumbing tap layout unsupported.** Reported in `unsupported_preferences`. | Persisted in `requirements.water_features.garden_taps_required`. |
| Garden Taps Count | `water_features.garden_taps_count` | `integer` (>= 1) | count | `1` | `water_features.garden_taps_required == true` | `service.py` | **Unsupported generation.** | Persisted in `requirements.water_features.garden_taps_count`. |
| Pond Required | `water_features.pond_required` | `boolean` | None | `false` | None | `service.py` | **Preference capture complete; water body layout generation unsupported.** Reported in `unsupported_preferences`. | Persisted in `requirements.water_features.pond_required`. |
| Swimming Pool Required | `water_features.swimming_pool_required` | `boolean` | None | `false` | None | `service.py` | **Preference capture complete; swimming pool layout generation unsupported.** Reported in `unsupported_preferences`. | Persisted in `requirements.water_features.swimming_pool_required`. |
| Septic Tank Required | `water_features.septic_tank_required`| `boolean` | None | `false` | None | `utility_safety.py` | Supported for safety clearance evaluation against water features. Never relocates authoritative existing septic tank. | Persisted in `requirements.water_features.septic_tank_required`. |

---

### Group K: Solar Preferences

| UI Label | Canonical API Field | Type & Allowed Values | Unit | Default Semantics | Parent Dependency | Backend Consumer | Generation Support | Persistence & Restoration |
|---|---|---|---|---|---|---|---|---|
| Solar Panels Required | `solar.panels_required` | `boolean` | None | `false` | None | `solar.py`, `service.py` | **Preference capture complete; 3D PV panel layout generation unsupported.** Solar irradiance simulation is supported. Reported in `unsupported_preferences`. | Persisted in `requirements.solar.panels_required`. |
| Preferred Roof Surface | `solar.preferred_roof_surface` | string enum: `"flat_roof"`, `"south_facing"`, `"north_facing"`, `"auto"`, `"any"` | None | `"auto"` | `solar.panels_required == true` | `solar.py` | Supported in solar shadow score weighting. | Persisted in `requirements.solar.preferred_roof_surface`. |
| Placement Priority | `solar.placement_priority` | string enum: `"maximum_yield"`, `"concealed_from_street"`, `"balanced"` | None | `"balanced"` | `solar.panels_required == true` | `solar.py` | Captured as planning priority. | Persisted in `requirements.solar.placement_priority`. |
| Include Live Solar Conditions | `solar.include_live_solar` | `boolean` | None | `false` | None | `solar.py`, `service.py` | Supported. Fetches live solar angles from project location. | Persisted in `requirements.solar.include_live_solar` and root `include_live_solar`. |

---

## 3. Unsupported Generation Features

When preferences are captured for features whose automated spatial placement is not yet supported in the Stage 1 generator, ELIA:
1. Retains and serializes the user's explicit intent.
2. Reports the exact feature name in `exterior_landscape.preference_fulfillment.unsupported_preferences`.
3. Never fabricates fake placements or claims the request was fulfilled.
4. Exposes clear user-facing notices in the frontend UI near the affected controls.

The complete list of captured but ungenerated features in Stage 1 is:
- `swimming_pool` (requires Stage 2 structural, setback, and excavation feasibility)
- `pond` (requires Stage 2 water body containment and drainage modeling)
- `new_well` (requires Stage 2 hydrogeological separation and municipal setback verification)
- `garden_taps` (requires Stage 2 exterior MEP routing)
- `solar_panels` (requires Stage 2 3D roof panel array placement)
- `rooftop_terrace` (requires Stage 2 multi-level structural access and parapet validation)
- `balcony_furniture` (requires Stage 2 upper-level architectural floor-plan integration)

---

## 4. Inactive Dependent Fields Policy

When a parent feature is toggled off (e.g., `garage_required: false`, `trees_required: false`, `boundary_wall_required: false`, `lighting.required: false`):
- Frontend serialization strictly omits child properties from the payload.
- Backend normalization clears or omits inactive child properties so stale values cannot inadvertently participate in generation or rule checks.
- Temporary form values in the UI may be kept in local state for convenience should the user re-enable the parent, but they are excluded from serialized API requests.
