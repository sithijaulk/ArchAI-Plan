# ESAI Furniture Catalog Repository

## Data Source
Stored in JSON format at [furniture_catalog.json](file:///backend/app/components/esai_engine/data/furniture_catalog.json) and managed via [FurnitureCatalogRepository](file:///backend/app/components/esai_engine/catalog.py).

## Schema
Each catalog item includes:
- `id`: Unique identifier (e.g., `BED_KING_01`, `SOFA_3SEATER_01`, `KITCHEN_COUNTER_BASE_01`).
- `category`: [AssetCategory](file:///backend/app/components/esai_engine/contracts.py) enum (bed, sofa, dining_table, kitchen_counter, basin, commode, etc.).
- `name`: Display name.
- `supported_room_types`: Array of compatible room types.
- `dimensions`: `{ width, depth, height }` in meters.
- `physical_footprint_type`: Geometry type (e.g., `rectangle`).
- `default_clearance_rule_id`: Referenced rule from ergonomic standards repository.
- `supported_rotations`: Array of allowed discrete orientations `[0, 90, 180, 270]`.
- `placement_preferences`: Wall affinities, daylight orientations, and pairings.
- `functional_relations`: Related furniture categories.
- `mobility`: `movable` vs `fixed`.
- `rendering_model_id`: 3D model asset identifier.
- `material_variants`: Available textures and material finishes.
- `enabled`: Boolean toggle.

## Represented Room Categories
1. **Bedrooms**: King Bed, Queen Bed, Twin Bed, Nightstand, 3-Door Hinged Wardrobe, Sliding Wardrobe, Dressing Table.
2. **Living Spaces**: 3-Seater Sofa, 2-Seater Loveseat, Armchair, Coffee Table, Media TV Console, Bookshelf.
3. **Dining**: 6-Person Dining Table, Dining Chair.
4. **Kitchen**: Standard Kitchen Counter Run (fixed), Central Kitchen Island (fixed).
5. **Bathroom**: Vanity Basin (fixed), Commode / WC (fixed), Walk-In Shower Enclosure (fixed).
6. **Study & Office**: Executive Desk, Ergonomic Office Chair.
