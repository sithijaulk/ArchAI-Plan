"""
Phase 3 Knowledge Base Builder & Validator
Builds and verifies:
1. furniture_catalog.json (complete asset catalog)
2. finishes_catalog.json (wall, floor, ceiling, countertop, cabinet finishes)
3. styles_catalog.json (aesthetic compatibility matrices)
4. ergonomic_rules.json (audited Neufert & anthropometric rules with verified provenance)
5. room_profiles.json (all normalized room types)
6. functional_relations.json (inter-asset spatial rules)
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "app", "components", "esai_engine", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ─── 1. FURNITURE CATALOG ──────────────────────────────────────────────────────

# Preserve original items and expand with comprehensive catalog
catalog_path = os.path.join(DATA_DIR, "furniture_catalog.json")
existing_items = []
if os.path.exists(catalog_path):
    with open(catalog_path, "r", encoding="utf-8") as f:
        existing_items = json.load(f).get("items", [])

existing_ids = {it["id"] for it in existing_items}

new_items = [
    # BEDS & SLEEPING VARIANTS
    {
        "id": "BED_DOUBLE_01",
        "category": "bed",
        "subtype": "double_bed",
        "name": "Standard Double Bed",
        "description": "Full-size double bed accommodating two adults (140 x 200 cm mattress).",
        "supported_room_types": ["bedroom", "guest_room", "master_bedroom"],
        "dimensions": {"width": 1.48, "depth": 2.05, "height": 0.55},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "BED_ACCESS_PRIMARY",
        "supported_rotations": [0, 90, 180, 270],
        "placement_preferences": {"wall_affinity": "headboard_to_wall"},
        "functional_relations": ["bedside_table", "wardrobe"],
        "mobility": "movable",
        "rendering_model_id": "model_bed_double_01",
        "material_variants": ["wood_oak", "wood_walnut", "upholstered_grey"],
        "color_variants": ["natural_oak", "walnut", "charcoal"],
        "required_services": [],
        "optional_services": [{"type": "power_general", "description": "Bedside reading light outlet"}],
        "provenance": "Neufert Architects' Data (p. 254) & Standard Metric Sizing",
        "enabled": True
    },
    {
        "id": "BED_TWIN_PAIR_01",
        "category": "bed",
        "subtype": "twin_beds",
        "name": "Twin Beds Arrangement",
        "description": "Paired twin single beds with central nightstand buffer.",
        "supported_room_types": ["bedroom", "guest_room"],
        "dimensions": {"width": 2.25, "depth": 2.00, "height": 0.50},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "BED_ACCESS_PRIMARY",
        "supported_rotations": [0, 90, 180, 270],
        "placement_preferences": {"wall_affinity": "headboard_to_wall"},
        "functional_relations": ["bedside_table", "wardrobe"],
        "mobility": "movable",
        "rendering_model_id": "model_bed_twin_pair_01",
        "material_variants": ["wood_white", "wood_natural"],
        "provenance": "Architects' Data (Neufert) Bedroom Configurations",
        "enabled": True
    },
    {
        "id": "BED_BUNK_01",
        "category": "bed",
        "subtype": "bunk_bed",
        "name": "Twin-over-Twin Bunk Bed",
        "description": "Two-tier vertical stacked bed with safety guardrail and fixed ladder.",
        "supported_room_types": ["bedroom"],
        "dimensions": {"width": 1.05, "depth": 2.05, "height": 1.70},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "BED_ACCESS_PRIMARY",
        "supported_rotations": [0, 90, 180, 270],
        "placement_preferences": {"wall_affinity": "headboard_to_wall", "side_wall_affinity": "long_side_against_wall"},
        "functional_relations": ["wardrobe", "desk"],
        "safety_considerations": "Minimum 800mm ceiling buffer required above top bunk mattress.",
        "mobility": "movable",
        "rendering_model_id": "model_bed_bunk_01",
        "material_variants": ["wood_pine", "painted_white", "metal_black"],
        "provenance": "ASTM F1427 & EN 747 Bunk Bed Safety Standards",
        "enabled": True
    },
    {
        "id": "BED_TRIPLE_SLEEPER_01",
        "category": "bed",
        "subtype": "triple_sleeper",
        "name": "Triple-Sleeper Bunk Bed",
        "description": "Distinct 3-person bunk configuration with double bed lower tier (140cm) and single bed upper tier (90cm).",
        "supported_room_types": ["bedroom", "guest_room"],
        "dimensions": {"width": 1.50, "depth": 2.05, "height": 1.75},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "BED_ACCESS_PRIMARY",
        "supported_rotations": [0, 90, 180, 270],
        "placement_preferences": {"wall_affinity": "headboard_to_wall"},
        "functional_relations": ["wardrobe", "bedside_table"],
        "safety_considerations": "Integrated ladder clearance required on long side.",
        "mobility": "movable",
        "rendering_model_id": "model_bed_triple_01",
        "material_variants": ["solid_pine", "metal_white"],
        "provenance": "European Standard EN 747 / Bunk & High Beds Specification",
        "enabled": True
    },
    {
        "id": "BED_STORAGE_01",
        "category": "bed",
        "subtype": "storage_bed",
        "name": "Queen Hydraulic Storage Bed",
        "description": "Queen bed with gas-lift hydraulic under-mattress storage chamber.",
        "supported_room_types": ["master_bedroom", "bedroom"],
        "dimensions": {"width": 1.62, "depth": 2.10, "height": 0.65},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "BED_ACCESS_PRIMARY",
        "supported_rotations": [0, 90, 180, 270],
        "placement_preferences": {"wall_affinity": "headboard_to_wall"},
        "functional_relations": ["bedside_table", "wardrobe"],
        "mobility": "movable",
        "rendering_model_id": "model_bed_storage_01",
        "material_variants": ["fabric_grey", "leather_tan"],
        "provenance": "Manufacturer Sizing Specifications",
        "enabled": True
    },
    # WARDROBES & BEDROOM STORAGE
    {
        "id": "WARDROBE_4DOOR_01",
        "category": "wardrobe",
        "subtype": "hinged_wardrobe",
        "name": "4-Door Hinged Master Wardrobe",
        "description": "Full-width hinged wardrobe with integrated shelving and hanging rails.",
        "supported_room_types": ["master_bedroom", "bedroom"],
        "dimensions": {"width": 2.00, "depth": 0.60, "height": 2.30},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "WARDROBE_HINGED_FRONT",
        "wall_attachment_required": True,
        "placement_preferences": {"back_against_wall": True},
        "functional_relations": ["bed", "dressing_table"],
        "mobility": "fixed",
        "rendering_model_id": "model_wardrobe_4d_01",
        "material_variants": ["matte_white", "wood_walnut", "smoked_glass"],
        "provenance": "Neufert Architects' Data (p. 256)",
        "enabled": True
    },
    {
        "id": "WARDROBE_WALKIN_UNIT_01",
        "category": "wardrobe",
        "subtype": "walk_in_wardrobe",
        "name": "Walk-In Modular Open Wardrobe",
        "description": "Open modular dressing unit without doors, optimized for dedicated dressing rooms.",
        "supported_room_types": ["master_bedroom"],
        "dimensions": {"width": 1.80, "depth": 0.55, "height": 2.20},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "WARDROBE_SLIDING_FRONT",
        "wall_attachment_required": True,
        "placement_preferences": {"back_against_wall": True},
        "functional_relations": ["dressing_table"],
        "mobility": "fixed",
        "rendering_model_id": "model_walkin_01",
        "material_variants": ["dark_ash", "warm_oak"],
        "provenance": "Architectural Graphic Standards: Residential Dressing Closets",
        "enabled": True
    },
    {
        "id": "CHEST_OF_DRAWERS_01",
        "category": "storage_cabinet",
        "subtype": "chest_of_drawers",
        "name": "6-Drawer Bedroom Dresser",
        "description": "Double column 6-drawer low storage chest.",
        "supported_room_types": ["master_bedroom", "bedroom", "guest_room"],
        "dimensions": {"width": 1.20, "depth": 0.48, "height": 0.85},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "WARDROBE_HINGED_FRONT",
        "wall_attachment_required": True,
        "placement_preferences": {"back_against_wall": True},
        "mobility": "movable",
        "rendering_model_id": "model_dresser_01",
        "material_variants": ["wood_oak", "white_lacquer"],
        "provenance": "ANSI/BIFMA Tip-Over Restraint Guidelines & Neufert",
        "enabled": True
    },
    # LIVING ROOM FURNITURE
    {
        "id": "SOFA_SECTIONAL_L_01",
        "category": "sofa",
        "subtype": "sectional_sofa",
        "name": "L-Shaped Sectional Corner Sofa",
        "description": "Spacious family sectional sofa with left or right chaise lounge return.",
        "supported_room_types": ["living_room", "family_living_area", "lounge", "tv_lounge"],
        "dimensions": {"width": 2.80, "depth": 2.10, "height": 0.85},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "LIVING_SOFA_FRONT",
        "supported_rotations": [0, 90, 180, 270],
        "placement_preferences": {"wall_affinity": "corner_or_freestanding"},
        "functional_relations": ["coffee_table", "tv_console"],
        "mobility": "movable",
        "rendering_model_id": "model_sofa_sectional_l_01",
        "material_variants": ["fabric_oatmeal", "fabric_slate", "leather_caramel"],
        "provenance": "Panero & Zelnik Human Dimension & Interior Space (p. 138)",
        "enabled": True
    },
    {
        "id": "RECLINER_ARMCHAIR_01",
        "category": "armchair",
        "subtype": "recliner",
        "name": "Ergonomic Swivel Recliner",
        "description": "Contoured single lounge recliner with extending footrest.",
        "supported_room_types": ["living_room", "family_living_area", "tv_lounge", "study"],
        "dimensions": {"width": 0.88, "depth": 0.95, "height": 1.05},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "SEATING_USE_SPACE",
        "functional_relations": ["side_table", "coffee_table"],
        "mobility": "movable",
        "rendering_model_id": "model_recliner_01",
        "material_variants": ["leather_black", "leather_cognac", "boucle_cream"],
        "provenance": "BIFMA Ergonomic Seating Standards",
        "enabled": True
    },
    {
        "id": "MEDIA_WALL_UNIT_01",
        "category": "media_wall",
        "subtype": "full_media_wall",
        "name": "Architectural Slat Media Wall Unit",
        "description": "Full-height timber acoustic slat wall panel with integrated floating TV console.",
        "supported_room_types": ["living_room", "family_living_area", "tv_lobby", "tv_lounge"],
        "dimensions": {"width": 2.40, "depth": 0.40, "height": 2.40},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "wall_attachment_required": True,
        "placement_preferences": {"back_against_wall": True},
        "functional_relations": ["sofa"],
        "required_services": [
            {"type": "tv_power", "description": "Quad gang TV power socket"},
            {"type": "tv_data", "description": "Cat6 RJ45 and coaxial RG6 data point"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_media_wall_01",
        "material_variants": ["black_slat_oak", "walnut_bronze"],
        "provenance": "Architectural Woodwork Standards (AWS)",
        "enabled": True
    },
    {
        "id": "SIDE_TABLE_01",
        "category": "side_table",
        "subtype": "side_table",
        "name": "Circular Accent Side Table",
        "description": "Compact occasional table for placing drinks or task lighting beside seating.",
        "supported_room_types": ["living_room", "lounge", "bedroom"],
        "dimensions": {"width": 0.45, "depth": 0.45, "height": 0.52},
        "physical_footprint_type": "circle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "GENERAL_CIRCULATION",
        "functional_relations": ["sofa", "armchair"],
        "mobility": "movable",
        "rendering_model_id": "model_side_table_01",
        "material_variants": ["marble_brass", "smoked_glass", "solid_walnut"],
        "provenance": "Standard Metric Furniture Dimensions",
        "enabled": True
    },
    # KITCHEN & PANTRY FIXTURES & APPLIANCES
    {
        "id": "KITCHEN_SINK_UNIT_01",
        "category": "sink",
        "subtype": "single_bowl_sink",
        "name": "Undermount Single Basin Sink Unit",
        "description": "Base cabinet with 600mm deep undermount stainless steel sink and mixer faucet provision.",
        "supported_room_types": ["kitchen", "pantry", "utility_room"],
        "dimensions": {"width": 0.80, "depth": 0.60, "height": 0.90},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "KITCHEN_WORK_CLEARANCE",
        "wall_attachment_required": True,
        "placement_preferences": {"back_against_wall": True},
        "functional_relations": ["kitchen_counter", "dishwasher"],
        "required_services": [
            {"type": "water_cold", "description": "1/2 inch cold water supply valve"},
            {"type": "water_hot", "description": "1/2 inch hot water supply valve"},
            {"type": "drainage", "description": "50mm PVC waste drainage trap"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_sink_01",
        "material_variants": ["stainless_steel", "composite_black_granite"],
        "provenance": "Neufert Architects' Data (p. 258) Kitchen Work Triangle",
        "enabled": True
    },
    {
        "id": "KITCHEN_DOUBLE_SINK_01",
        "category": "sink",
        "subtype": "double_bowl_sink",
        "name": "Double Basin Sink & Draining Board Unit",
        "description": "Wide base cabinet with twin deep bowls and vegetable prep basin.",
        "supported_room_types": ["kitchen"],
        "dimensions": {"width": 1.20, "depth": 0.60, "height": 0.90},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "KITCHEN_WORK_CLEARANCE",
        "wall_attachment_required": True,
        "placement_preferences": {"back_against_wall": True},
        "functional_relations": ["kitchen_counter", "dishwasher"],
        "required_services": [
            {"type": "water_cold", "description": "Cold water point"},
            {"type": "water_hot", "description": "Hot water point"},
            {"type": "drainage", "description": "Dual waste drain"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_sink_double_01",
        "material_variants": ["brushed_steel", "matte_anthracite"],
        "provenance": "Neufert Architects' Data (p. 258)",
        "enabled": True
    },
    {
        "id": "KITCHEN_WALL_CABINET_01",
        "category": "kitchen_counter",
        "subtype": "wall_cabinet",
        "name": "Overhead Wall Cabinet Unit",
        "description": "Double door overhead upper cabinet mounted above base counter.",
        "supported_room_types": ["kitchen", "pantry"],
        "dimensions": {"width": 0.90, "depth": 0.35, "height": 0.72},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "wall_attachment_required": True,
        "placement_preferences": {"mounted_height_m": 1.45},
        "mobility": "fixed",
        "rendering_model_id": "model_wall_cab_01",
        "material_variants": ["white_matte", "natural_wood", "fluted_glass"],
        "provenance": "Neufert (p. 259) Upper Kitchen Cabinet Clearances",
        "enabled": True
    },
    {
        "id": "KITCHEN_TALL_PANTRY_01",
        "category": "pantry_cabinet",
        "subtype": "tall_pantry",
        "name": "Floor-to-Ceiling Pantry Unit",
        "description": "Full height tall storage cabinet with pull-out internal wire baskets.",
        "supported_room_types": ["kitchen", "pantry"],
        "dimensions": {"width": 0.60, "depth": 0.60, "height": 2.20},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "wall_attachment_required": True,
        "default_clearance_rule_id": "KITCHEN_WORK_CLEARANCE",
        "mobility": "fixed",
        "rendering_model_id": "model_tall_pantry_01",
        "material_variants": ["matte_anthracite", "light_oak"],
        "provenance": "Kitchen Manufacturers Association (KCMA) Standards",
        "enabled": True
    },
    {
        "id": "REFRIGERATOR_FRENCH_DOOR_01",
        "category": "refrigerator",
        "subtype": "refrigerator",
        "name": "French Door Refrigerator & Freezer",
        "description": "500L multi-door freestanding refrigerator with dual door swing.",
        "supported_room_types": ["kitchen", "pantry"],
        "dimensions": {"width": 0.91, "depth": 0.76, "height": 1.78},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "KITCHEN_WORK_CLEARANCE",
        "required_services": [
            {"type": "power_appliance", "description": "15A dedicated continuous power socket (230V)"}
        ],
        "optional_services": [
            {"type": "water_cold", "description": "Filtered cold water line for ice maker"}
        ],
        "functional_relations": ["kitchen_counter"],
        "mobility": "movable",
        "rendering_model_id": "model_fridge_01",
        "material_variants": ["stainless_steel", "black_matte_steel"],
        "provenance": "AHAM Standard Refrigeration Sizing",
        "enabled": True
    },
    {
        "id": "COOKTOP_INDUCTION_01",
        "category": "cooktop",
        "subtype": "cooktop",
        "name": "4-Zone Flush Induction Cooktop",
        "description": "60cm ceramic glass induction hob for countertop cut-out installation.",
        "supported_room_types": ["kitchen"],
        "dimensions": {"width": 0.60, "depth": 0.52, "height": 0.06},
        "physical_footprint_type": "rectangle",
        "placement_mode": "countertop",
        "required_services": [
            {"type": "power_appliance", "description": "Dedicated 32A cooker connection unit with isolator"}
        ],
        "functional_relations": ["range_hood", "oven"],
        "mobility": "fixed",
        "rendering_model_id": "model_hob_01",
        "material_variants": ["black_ceramic_glass"],
        "provenance": "IEC 60335 Household Electrical Appliances Standards",
        "enabled": True
    },
    {
        "id": "RANGE_HOOD_CHIMNEY_01",
        "category": "range_hood",
        "subtype": "range_hood",
        "name": "Wall-Mounted Chimney Range Hood",
        "description": "High-extraction stainless steel cooker canopy with grease filters and LED task lights.",
        "supported_room_types": ["kitchen"],
        "dimensions": {"width": 0.90, "depth": 0.50, "height": 0.70},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "wall_attachment_required": True,
        "placement_preferences": {"mounted_height_m": 0.65, "aligned_above": "cooktop"},
        "required_services": [
            {"type": "power_general", "description": "High-level switched power outlet"},
            {"type": "exhaust_duct", "description": "150mm exterior wall exhaust vent connection"}
        ],
        "functional_relations": ["cooktop"],
        "mobility": "fixed",
        "rendering_model_id": "model_hood_01",
        "material_variants": ["brushed_stainless", "matte_black"],
        "provenance": "Neufert (p. 258) Minimum 650mm clearance above electric cooktop",
        "enabled": True
    },
    {
        "id": "DISHWASHER_BUILTIN_01",
        "category": "dishwasher",
        "subtype": "dishwasher",
        "name": "Fully-Integrated 60cm Dishwasher",
        "description": "14-place setting undercounter dishwasher with matching cabinet front.",
        "supported_room_types": ["kitchen"],
        "dimensions": {"width": 0.60, "depth": 0.55, "height": 0.82},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "KITCHEN_WORK_CLEARANCE",
        "required_services": [
            {"type": "power_appliance", "description": "13A unswitched socket under adjacent cabinet"},
            {"type": "water_cold", "description": "3/4 inch appliance water isolation valve"},
            {"type": "drainage", "description": "Spigot connection into sink waste trap"}
        ],
        "functional_relations": ["sink"],
        "mobility": "fixed",
        "rendering_model_id": "model_dishwasher_01",
        "material_variants": ["cabinet_matched_panel"],
        "provenance": "EN 50242 Electric Dishwashers Specification",
        "enabled": True
    },
    # BATHROOM & SANITARY FIXTURES
    {
        "id": "BATH_COMMODE_WALLHUNG_01",
        "category": "commode",
        "subtype": "wall_hung_toilet",
        "name": "Wall-Hung Rimless WC with Concealed Cistern",
        "description": "Hygienic wall-hung toilet bowl mounted on in-wall carrier frame with dual flush plate.",
        "supported_room_types": ["bathroom", "attached_bathroom", "common_bathroom", "toilet"],
        "dimensions": {"width": 0.36, "depth": 0.54, "height": 0.40},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "wall_attachment_required": True,
        "default_clearance_rule_id": "BATH_COMMODE_CLEARANCE",
        "required_services": [
            {"type": "water_cold", "description": "Concealed cistern cold feed point"},
            {"type": "drainage", "description": "110mm horizontal soil pipe connection"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_wc_wallhung_01",
        "material_variants": ["white_vitreous_china", "matte_black_ceramic"],
        "provenance": "Neufert Architects' Data (p. 262) & EN 997 WC Pan Specifications",
        "enabled": True
    },
    {
        "id": "BATH_DOUBLE_VANITY_01",
        "category": "vanity_unit",
        "subtype": "double_vanity",
        "name": "Floating Double-Sink Vanity Unit",
        "description": "1400mm floating wall-mounted bathroom console with twin integrated under-mount basins and drawers.",
        "supported_room_types": ["master_bedroom", "bathroom", "attached_bathroom"],
        "dimensions": {"width": 1.40, "depth": 0.52, "height": 0.50},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "wall_attachment_required": True,
        "default_clearance_rule_id": "BATH_BASIN_FRONT",
        "required_services": [
            {"type": "water_cold", "description": "Twin cold water isolation valves"},
            {"type": "water_hot", "description": "Twin hot water isolation valves"},
            {"type": "drainage", "description": "Twin 40mm waste outlets"}
        ],
        "functional_relations": ["bathroom_mirror"],
        "mobility": "fixed",
        "rendering_model_id": "model_double_vanity_01",
        "material_variants": ["fluted_oak", "matte_white_corian", "dark_walnut"],
        "provenance": "Neufert Architects' Data (p. 264)",
        "enabled": True
    },
    {
        "id": "BATH_WALKIN_SHOWER_01",
        "category": "shower_enclosure",
        "subtype": "walk_in_shower",
        "name": "Walk-In Glass Screen Shower Zone",
        "description": "Frameless 10mm toughened glass screen with flush tiled floor linear drain.",
        "supported_room_types": ["bathroom", "attached_bathroom", "common_bathroom"],
        "dimensions": {"width": 1.40, "depth": 0.90, "height": 2.05},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "BATH_SHOWER_ENTRY",
        "required_services": [
            {"type": "water_cold", "description": "Cold feed to thermostatic shower mixer"},
            {"type": "water_hot", "description": "Hot water feed to shower mixer"},
            {"type": "drainage", "description": "Linear stainless floor waste drain"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_walkin_shower_01",
        "material_variants": ["chrome_trim", "matte_black_hardware", "brushed_brass"],
        "provenance": "Neufert (p. 263) Shower Clearance Requirements",
        "enabled": True
    },
    {
        "id": "BATH_BATHTUB_FREESTANDING_01",
        "category": "bathtub",
        "subtype": "freestanding_bathtub",
        "name": "Freestanding Oval Soaking Tub",
        "description": "Contemporary mineral cast stone freestanding soaking bathtub with floor-mounted mixer tap.",
        "supported_room_types": ["master_bedroom", "bathroom", "attached_bathroom"],
        "dimensions": {"width": 1.70, "depth": 0.80, "height": 0.60},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "GENERAL_CIRCULATION",
        "required_services": [
            {"type": "water_cold", "description": "Under-floor cold water pipe to tub filler"},
            {"type": "water_hot", "description": "Under-floor hot water pipe to tub filler"},
            {"type": "drainage", "description": "40mm trapped floor waste drain"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_bathtub_free_01",
        "material_variants": ["matte_white_stone", "gloss_acrylic"],
        "provenance": "Neufert (p. 263) Bathtub Dimensions & Access Clearance",
        "enabled": True
    },
    {
        "id": "BATH_BATHTUB_BUILTIN_01",
        "category": "bathtub",
        "subtype": "builtin_bathtub",
        "name": "Built-In Alcove Bathtub",
        "description": "Enamelled steel alcove bathtub installed against walls with tiled front apron panel.",
        "supported_room_types": ["bathroom", "attached_bathroom", "common_bathroom"],
        "dimensions": {"width": 1.70, "depth": 0.75, "height": 0.55},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "wall_attachment_required": True,
        "default_clearance_rule_id": "BATH_SHOWER_ENTRY",
        "required_services": [
            {"type": "water_cold", "description": "Cold supply point"},
            {"type": "water_hot", "description": "Hot supply point"},
            {"type": "drainage", "description": "Waste trap connection"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_bathtub_builtin_01",
        "material_variants": ["white_enamel"],
        "provenance": "Neufert (p. 263)",
        "enabled": True
    },
    {
        "id": "BATH_HEATED_TOWEL_RAIL_01",
        "category": "towel_rail",
        "subtype": "heated_towel_rail",
        "name": "Electric Heated Ladder Towel Rail",
        "description": "Wall-mounted multi-rung ladder towel dryer with IPX4 splash-proof rating.",
        "supported_room_types": ["bathroom", "attached_bathroom", "common_bathroom"],
        "dimensions": {"width": 0.50, "depth": 0.12, "height": 1.10},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "wall_attachment_required": True,
        "required_services": [
            {"type": "power_general", "description": "Fused spur switch outside Zone 2 with IPX4 rating"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_towel_rail_01",
        "material_variants": ["polished_chrome", "matte_black", "brushed_nickel"],
        "provenance": "BS 7671 IET Wiring Regulations Bathroom Zones",
        "enabled": True
    },
    # DINING ROOM FURNITURE
    {
        "id": "DINING_TABLE_ROUND_4S_01",
        "category": "dining_table",
        "subtype": "round_dining_table",
        "name": "Round 4-Seater Dining Table",
        "description": "1100mm diameter round pedestal dining table for intimate dining and conversation.",
        "supported_room_types": ["dining_room", "dining_area", "kitchen"],
        "dimensions": {"width": 1.10, "depth": 1.10, "height": 0.75},
        "physical_footprint_type": "circle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "DINING_CHAIR_PULLOUT",
        "functional_relations": ["dining_chair"],
        "mobility": "movable",
        "rendering_model_id": "model_table_round_01",
        "material_variants": ["oak_pedestal", "white_marble_tulip"],
        "provenance": "Neufert Architects' Data (p. 260) Dining Space Requirements",
        "enabled": True
    },
    {
        "id": "DINING_TABLE_8S_01",
        "category": "dining_table",
        "subtype": "rectangular_dining_table",
        "name": "Rectangular 8-Seater Dining Table",
        "description": "Extended 2200mm solid wood dining table for hosting large dinner parties.",
        "supported_room_types": ["dining_room", "dining_area"],
        "dimensions": {"width": 2.20, "depth": 1.00, "height": 0.75},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "DINING_CHAIR_PULLOUT",
        "functional_relations": ["dining_chair"],
        "mobility": "movable",
        "rendering_model_id": "model_table_8s_01",
        "material_variants": ["solid_walnut", "smoked_oak"],
        "provenance": "Neufert Architects' Data (p. 260)",
        "enabled": True
    },
    {
        "id": "DINING_SIDEBOARD_01",
        "category": "storage_cabinet",
        "subtype": "sideboard",
        "name": "Dining Credenza / Buffet Sideboard",
        "description": "Four-door low sideboard for storing dinnerware, linens, and serving platters.",
        "supported_room_types": ["dining_room", "dining_area", "living_room"],
        "dimensions": {"width": 1.80, "depth": 0.45, "height": 0.80},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "placement_preferences": {"back_against_wall": True},
        "mobility": "movable",
        "rendering_model_id": "model_sideboard_01",
        "material_variants": ["walnut_brass", "fluted_oak"],
        "provenance": "Standard Residential Furniture Dimensions",
        "enabled": True
    },
    # STUDY & OFFICE FURNITURE
    {
        "id": "DESK_STANDING_01",
        "category": "desk",
        "subtype": "standing_desk",
        "name": "Motorized Height-Adjustable Standing Desk",
        "description": "Dual-motor sit-stand desk with memory presets and integrated cable management tray.",
        "supported_room_types": ["study", "study_office", "home_office", "bedroom"],
        "dimensions": {"width": 1.60, "depth": 0.80, "height": 0.72},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "DESK_CHAIR_MOVEMENT",
        "functional_relations": ["office_chair"],
        "required_services": [
            {"type": "power_general", "description": "Desk power outlet for motorized lifting mechanism and IT equipment"},
            {"type": "network_data", "description": "Cat6 high speed data point"}
        ],
        "mobility": "movable",
        "rendering_model_id": "model_standing_desk_01",
        "material_variants": ["oak_black_frame", "walnut_white_frame"],
        "provenance": "BIFMA G1 Ergonomics Guideline for Sit-Stand Desks",
        "enabled": True
    },
    # UTILITY & LAUNDRY APPLIANCES
    {
        "id": "WASHING_MACHINE_01",
        "category": "washing_machine",
        "subtype": "washing_machine",
        "name": "Front-Loading 9kg Washing Machine",
        "description": "Energy-efficient front-load washing machine with vibration dampening feet.",
        "supported_room_types": ["utility_room", "laundry_room", "bathroom"],
        "dimensions": {"width": 0.60, "depth": 0.60, "height": 0.85},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "KITCHEN_WORK_CLEARANCE",
        "required_services": [
            {"type": "power_appliance", "description": "Dedicated 13A electrical socket"},
            {"type": "water_cold", "description": "Washing machine cold water bib tap"},
            {"type": "drainage", "description": "40mm standpipe waste drain"}
        ],
        "mobility": "movable",
        "rendering_model_id": "model_washer_01",
        "material_variants": ["white", "graphite_grey"],
        "provenance": "IEC Appliance Standards",
        "enabled": True
    },
    {
        "id": "TUMBLE_DRYER_01",
        "category": "dryer",
        "subtype": "dryer",
        "name": "Heat Pump Condenser Clothes Dryer",
        "description": "Closed-loop heat pump dryer suitable for undercounter or stacked installation.",
        "supported_room_types": ["utility_room", "laundry_room"],
        "dimensions": {"width": 0.60, "depth": 0.60, "height": 0.85},
        "physical_footprint_type": "rectangle",
        "placement_mode": "floor_standing",
        "default_clearance_rule_id": "KITCHEN_WORK_CLEARANCE",
        "required_services": [
            {"type": "power_appliance", "description": "13A electrical socket"}
        ],
        "functional_relations": ["washing_machine"],
        "mobility": "movable",
        "rendering_model_id": "model_dryer_01",
        "material_variants": ["white", "graphite"],
        "provenance": "Manufacturer Sizing Specifications",
        "enabled": True
    },
    # LIGHTING FIXTURES
    {
        "id": "LIGHT_CEILING_PENDANT_01",
        "category": "pendant_light",
        "subtype": "pendant_light",
        "name": "Architectural Dining Pendant Light",
        "description": "Linear architectural LED pendant light with anti-glare diffuser and dimmable driver.",
        "supported_room_types": ["dining_room", "dining_area", "kitchen"],
        "dimensions": {"width": 1.20, "depth": 0.15, "height": 0.25},
        "physical_footprint_type": "rectangle",
        "placement_mode": "ceiling_mounted",
        "ceiling_attachment_required": True,
        "placement_preferences": {"centered_above": "dining_table", "drop_height_m": 0.75},
        "required_services": [
            {"type": "dimmer_switch", "description": "Ceiling junction box wired to wall dimmer"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_pendant_01",
        "material_variants": ["matte_black", "brushed_brass"],
        "provenance": "CIBSE Code for Lighting: Interior Lighting Standards",
        "enabled": True
    },
    {
        "id": "LIGHT_RECESSED_DOWNLIGHT_01",
        "category": "recessed_downlight",
        "subtype": "recessed_downlight",
        "name": "CRI95+ Deep Recessed LED Downlight",
        "description": "Architectural trimless downlight with 36-degree beam angle and warm dimming (2700K-1800K).",
        "supported_room_types": ["all"],
        "dimensions": {"width": 0.10, "depth": 0.10, "height": 0.12},
        "physical_footprint_type": "circle",
        "placement_mode": "ceiling_mounted",
        "ceiling_attachment_required": True,
        "required_services": [
            {"type": "light_switch", "description": "Switched ceiling circuit loop"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_downlight_01",
        "material_variants": ["matte_white", "matte_black"],
        "provenance": "EN 12464-1 Lighting of Work Places",
        "enabled": True
    },
    {
        "id": "CEILING_FAN_01",
        "category": "ceiling_fan",
        "subtype": "ceiling_fan",
        "name": "Aerodynamic DC Motor Ceiling Fan with Light",
        "description": "Whisper-quiet 52-inch 3-blade ceiling fan with integrated dimmable LED light.",
        "supported_room_types": ["bedroom", "master_bedroom", "living_room", "family_living_area"],
        "dimensions": {"width": 1.32, "depth": 1.32, "height": 0.35},
        "physical_footprint_type": "circle",
        "placement_mode": "ceiling_mounted",
        "ceiling_attachment_required": True,
        "placement_preferences": {"room_center": True, "min_blade_clearance_m": 2.30},
        "required_services": [
            {"type": "fan_point", "description": "Heavy-duty ceiling hook box with wall fan speed controller"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_fan_01",
        "material_variants": ["matte_white", "brushed_nickel", "natural_wood_blades"],
        "provenance": "UL 507 Electric Fans Safety Standards",
        "enabled": True
    },
    # SERVICES & ELECTRICAL FIXTURES (Proposed Conceptual Requirements)
    {
        "id": "SERVICE_SOCKET_BEDSIDE_01",
        "category": "usb_charging_point",
        "subtype": "bedside_socket",
        "name": "Dual Power Socket with USB-C PD Charging",
        "description": "Bedside wall-mounted plate with two 13A switched sockets and high-speed 45W USB-C PD ports.",
        "supported_room_types": ["master_bedroom", "bedroom", "guest_room", "study"],
        "dimensions": {"width": 0.15, "depth": 0.04, "height": 0.08},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "placement_preferences": {"mounted_height_m": 0.65, "adjacent_to": "bedside_table"},
        "required_services": [
            {"type": "power_general", "description": "Radial or ring final electrical circuit connection"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_socket_usb_01",
        "material_variants": ["screwless_matte_white", "brushed_brass", "matte_black"],
        "provenance": "BS 1363 Electrical Plugs and Sockets Standard",
        "enabled": True
    },
    {
        "id": "SERVICE_AC_INDOOR_UNIT_01",
        "category": "ac_unit",
        "subtype": "split_ac_unit",
        "name": "High-Efficiency Inverter Split AC Indoor Unit",
        "description": "Wall-mounted multi-split air conditioner indoor unit with auto-swing louver.",
        "supported_room_types": ["master_bedroom", "bedroom", "living_room", "family_living_area", "study"],
        "dimensions": {"width": 0.88, "depth": 0.22, "height": 0.30},
        "physical_footprint_type": "rectangle",
        "placement_mode": "wall_mounted",
        "wall_attachment_required": True,
        "placement_preferences": {"mounted_height_m": 2.30, "avoid_direct_draft_on_bed": True},
        "required_services": [
            {"type": "ac_power", "description": "Dedicated 20A rotary isolator switch"},
            {"type": "drainage", "description": "Condensate gravity drain line to exterior/hopper"}
        ],
        "mobility": "fixed",
        "rendering_model_id": "model_ac_unit_01",
        "material_variants": ["matte_white"],
        "provenance": "ASHRAE Standard 55 Thermal Environmental Conditions",
        "enabled": True
    }
]

# Merge into complete catalog, avoiding duplicates
combined_items = list(existing_items)
for item in new_items:
    if item["id"] not in existing_ids:
        combined_items.append(item)
        existing_ids.add(item["id"])

catalog_data = {
    "version": "2.0",
    "provenance": "Architectural Graphic Standards, Ernst Neufert Architects' Data & Verified Metric Specifications (Dimensions in meters)",
    "items": combined_items
}

with open(catalog_path, "w", encoding="utf-8") as f:
    json.dump(catalog_data, f, indent=2)
print(f"Catalog updated: {len(combined_items)} items saved to {catalog_path}")


# ─── 2. FINISHES CATALOG ───────────────────────────────────────────────────────
finishes_path = os.path.join(DATA_DIR, "finishes_catalog.json")
finishes_data = {
    "version": "1.0",
    "provenance": "Verified Architectural Finish Specifications & British Standards for Interior Surface Materials",
    "finishes": [
        # WALL FINISHES
        {
            "id": "FIN_WALL_PAINT_MATTE",
            "category": "wall_finish",
            "name": "Architectural Low-VOC Matte Emulsion Paint",
            "material_type": "acrylic_emulsion",
            "compatible_surfaces": ["drywall", "plaster", "concrete"],
            "style_tags": ["modern", "minimalist", "scandinavian", "japandi", "contemporary"],
            "color_variants": ["chalk_white", "warm_taupe", "pale_sage", "slate_grey", "bone"],
            "texture_mapping": "textures/walls/paint_matte_normal.png",
            "installation_notes": "Two coats over primer on skim-coated substrate",
            "provenance": "BS EN 13300 Paints and Varnishes for Interior Walls",
            "enabled": True
        },
        {
            "id": "FIN_WALL_WOOD_SLATS",
            "category": "wall_finish",
            "name": "Acoustic Natural Timber Slats on Felt Backing",
            "material_type": "wood_veneer_acoustic_felt",
            "compatible_surfaces": ["drywall", "masonry"],
            "style_tags": ["japandi", "scandinavian", "modern", "contemporary"],
            "color_variants": ["natural_oak", "smoked_walnut", "ebony_ash"],
            "texture_mapping": "textures/walls/wood_slat_diffuse.png",
            "installation_notes": "Direct screw or adhesive fixing over battens; provides NRC 0.85 sound absorption",
            "provenance": "ASTM C423 Sound Absorption Testing Specification",
            "enabled": True
        },
        {
            "id": "FIN_WALL_TILE_SUBWAY",
            "category": "wall_finish",
            "name": "Glazed Ceramic Beveled Subway Tile",
            "material_type": "glazed_ceramic",
            "compatible_surfaces": ["cement_board", "waterproof_render"],
            "style_tags": ["industrial", "traditional", "modern", "scandinavian"],
            "color_variants": ["gloss_white", "matte_sage", "deep_navy", "black"],
            "texture_mapping": "textures/walls/subway_tile_normal.png",
            "installation_notes": "Epoxy or polymer-modified waterproof grout required in wet areas",
            "provenance": "ANSI A137.1 Ceramic Tile Standards",
            "enabled": True
        },
        # FLOOR FINISHES
        {
            "id": "FIN_FLOOR_OAK_HARDWOOD",
            "category": "floor_finish",
            "name": "Engineered European White Oak Flooring",
            "material_type": "engineered_hardwood",
            "compatible_surfaces": ["concrete_screed", "plywood_subfloor"],
            "style_tags": ["scandinavian", "japandi", "modern", "traditional", "contemporary"],
            "color_variants": ["natural_clear_matte", "warm_honey", "whitewashed", "smoked_cognac"],
            "texture_mapping": "textures/floors/oak_hardwood_pbr.png",
            "installation_notes": "Tongue-and-groove floating or direct glue-down; compatible with underfloor radiant heating",
            "provenance": "NWFA (National Wood Flooring Association) Standards",
            "enabled": True
        },
        {
            "id": "FIN_FLOOR_PORCELAIN_TILE",
            "category": "floor_finish",
            "name": "Large Format Matte Porcelain Floor Tile (600x1200mm)",
            "material_type": "porcelain",
            "compatible_surfaces": ["concrete_screed", "cement_board"],
            "style_tags": ["modern", "minimalist", "luxury", "industrial"],
            "color_variants": ["calacatta_marble_look", "pulpis_grey", "limestone_cream", "charcoal_basalt"],
            "texture_mapping": "textures/floors/porcelain_pbr.png",
            "installation_notes": "R10 slip rating minimum for wet areas; 2mm grout joint",
            "provenance": "ISO 13006 Ceramic Tiles Classification & DIN 51130 Slip Resistance",
            "enabled": True
        },
        {
            "id": "FIN_FLOOR_TERRAZZO",
            "category": "floor_finish",
            "name": "Custom Cast-in-Place Resin Terrazzo",
            "material_type": "epoxy_terrazzo",
            "compatible_surfaces": ["concrete_slab"],
            "style_tags": ["contemporary", "modern", "industrial", "luxury"],
            "color_variants": ["white_marble_aggregate", "warm_terracotta", "sage_granite"],
            "texture_mapping": "textures/floors/terrazzo_diffuse.png",
            "installation_notes": "Grind and polish to 800 grit; sealed with penetrating sealer",
            "provenance": "NTMA (National Terrazzo & Mosaic Association) Specifications",
            "enabled": True
        },
        # CEILING FINISHES
        {
            "id": "FIN_CEILING_GYPSUM_COVE",
            "category": "ceiling_finish",
            "name": "Recessed Gypsum False Ceiling with LED Perimeter Cove",
            "material_type": "gypsum_board_metal_framework",
            "compatible_surfaces": ["concrete_soffit"],
            "style_tags": ["modern", "luxury", "contemporary"],
            "color_variants": ["matte_ceiling_white"],
            "texture_mapping": "textures/ceilings/gypsum_smooth.png",
            "installation_notes": "12.5mm plasterboard on galvanised steel studs; 150mm drop from structural slab",
            "provenance": "ASTM C1396 Standard Specification for Gypsum Board",
            "enabled": True
        },
        # WINDOW TREATMENTS
        {
            "id": "FIN_WINDOW_SHEER_CURTAIN",
            "category": "window_treatment",
            "name": "Wave-Pleat Sheer Linen Drapery",
            "material_type": "linen_polyester_blend",
            "compatible_surfaces": ["ceiling_recess_track", "wall_mounted_rod"],
            "style_tags": ["scandinavian", "japandi", "modern", "luxury"],
            "color_variants": ["pure_white", "natural_flax", "warm_ivory"],
            "installation_notes": "Ceiling-recessed motorized or manual track with 2.5x fabric fullness",
            "provenance": "Architectural Drapery Specification Standards",
            "enabled": True
        },
        {
            "id": "FIN_WINDOW_BLACKOUT_BLIND",
            "category": "window_treatment",
            "name": "Motorized Cassette Blackout Roller Blind",
            "material_type": "opaque_fiberglass_vinyl",
            "compatible_surfaces": ["window_frame_recess", "wall_lintel"],
            "style_tags": ["minimalist", "modern", "contemporary"],
            "color_variants": ["white", "soft_grey", "charcoal"],
            "installation_notes": "Side guide channels provide 99.8% light blockout for bedrooms",
            "provenance": "BS 5867 Fire Retardant Fabric Standards",
            "enabled": True
        }
    ]
}

with open(finishes_path, "w", encoding="utf-8") as f:
    json.dump(finishes_data, f, indent=2)
print(f"Finishes catalog created: {len(finishes_data['finishes'])} finishes saved to {finishes_path}")


# ─── 3. STYLES & AESTHETIC COMPATIBILITY MATRIX ─────────────────────────────────
styles_path = os.path.join(DATA_DIR, "styles_catalog.json")
styles_data = {
    "version": "1.0",
    "provenance": "Computational Interior Design & Aesthetic Harmony Rules (Deterministic Compatibility Model)",
    "styles": {
        "modern": {
            "name": "Modern",
            "description": "Clean horizontal and vertical lines, unadorned surfaces, functional clarity",
            "compatible_materials": ["wood_oak", "wood_walnut", "stainless_steel", "black_matte_steel", "matte_lacquer", "porcelain", "glass"],
            "recommended_palettes": ["neutral_warm", "cool_slate", "monochrome_high_contrast"],
            "lighting_character": "neutral_architectural",
            "symmetry_bias": 0.6,
            "visual_weight_balance": "distributed"
        },
        "minimalist": {
            "name": "Minimalist",
            "description": "Essential forms, hidden storage, negative space, monochromatic textures",
            "compatible_materials": ["matte_white", "matte_anthracite", "light_ash", "polished_concrete", "corian"],
            "recommended_palettes": ["monochrome_high_contrast", "cool_slate"],
            "lighting_character": "cove_indirect",
            "symmetry_bias": 0.8,
            "visual_weight_balance": "low_density_sparse"
        },
        "scandinavian": {
            "name": "Scandinavian",
            "description": "Light natural timbers, soft textured textiles, organic curves, airy daylight illumination",
            "compatible_materials": ["wood_oak", "wood_pine", "linen", "wool", "boucle", "light_ceramics"],
            "recommended_palettes": ["neutral_warm", "nordic_forest"],
            "lighting_character": "warm_diffuse",
            "symmetry_bias": 0.5,
            "visual_weight_balance": "comfortable_organic"
        },
        "japandi": {
            "name": "Japandi",
            "description": "Hybrid Japanese-Scandinavian aesthetic; wabi-sabi simplicity with warm refined joinery",
            "compatible_materials": ["wood_oak", "wood_walnut", "dark_ash", "acoustic_felt", "paper_shoji", "linen", "clay_plaster"],
            "recommended_palettes": ["neutral_warm", "earth_terracotta", "nordic_forest"],
            "lighting_character": "warm_diffuse",
            "symmetry_bias": 0.4,
            "visual_weight_balance": "grounded_low_center_of_gravity"
        },
        "industrial": {
            "name": "Industrial",
            "description": "Raw structural elements, exposed metals, weathered timber, concrete and brick",
            "compatible_materials": ["metal_black", "cast_iron", "weathered_oak", "brick", "polished_concrete", "leather_cognac"],
            "recommended_palettes": ["cool_slate", "earth_terracotta", "monochrome_high_contrast"],
            "lighting_character": "warm_diffuse",
            "symmetry_bias": 0.3,
            "visual_weight_balance": "asymmetric_robust"
        },
        "luxury": {
            "name": "Luxury & Glamour",
            "description": "Bookmatched marble, polished metallic trims, velvet, crystal accents, tailored joinery",
            "compatible_materials": ["marble_brass", "calacatta_marble", "brushed_brass", "smoked_glass", "velvet", "high_gloss_lacquer"],
            "recommended_palettes": ["luxury_gold_navy", "neutral_warm", "monochrome_high_contrast"],
            "lighting_character": "cove_indirect",
            "symmetry_bias": 0.85,
            "visual_weight_balance": "formal_axial"
        },
        "traditional": {
            "name": "Traditional Classic",
            "description": "Symmetrical architectural layouts, crown mouldings, rich stained hardwoods, formal upholstery",
            "compatible_materials": ["solid_walnut", "solid_mahogany", "brass", "linen", "silk_damask", "ceramic_tile"],
            "recommended_palettes": ["neutral_warm", "earth_terracotta"],
            "lighting_character": "warm_diffuse",
            "symmetry_bias": 0.9,
            "visual_weight_balance": "balanced_formal"
        },
        "contemporary": {
            "name": "Contemporary",
            "description": "Fluid curved furniture, high-tech architectural materials, bold sculpted focal points",
            "compatible_materials": ["engineered_wood", "terrazzo", "curved_metal", "boucle", "tinted_glass"],
            "recommended_palettes": ["neutral_warm", "nordic_forest", "cool_slate"],
            "lighting_character": "neutral_architectural",
            "symmetry_bias": 0.45,
            "visual_weight_balance": "dynamic_sculptural"
        }
    }
}

with open(styles_path, "w", encoding="utf-8") as f:
    json.dump(styles_data, f, indent=2)
print(f"Styles catalog saved to {styles_path}")


# ─── 4. AUDITED ERGONOMIC RULES ────────────────────────────────────────────────
rules_path = os.path.join(DATA_DIR, "ergonomic_rules.json")
rules_data = {
    "version": "2.0",
    "provenance": "Ernst Neufert Architects' Data (4th International English Edition, Wiley-Blackwell, 2012), Panero & Zelnik Human Dimension & Interior Space (1979), and ADA Standards for Accessible Design (2010)",
    "rules": [
        # BEDROOM ERGONOMIC RULES
        {
            "id": "BED_ACCESS_PRIMARY",
            "applicable_categories": ["bed"],
            "clearance_direction": "both_sides",
            "threshold_m": 0.70,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Bedrooms - Space requirements around beds (p. 254)",
            "verification_status": "verified",
            "notes": "Minimum 700 mm (0.7m) clearance required on primary access sides for bed making and uninhibited access."
        },
        {
            "id": "BED_ACCESS_SECONDARY",
            "applicable_categories": ["bed"],
            "clearance_direction": "left",
            "threshold_m": 0.55,
            "priority": "soft",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Bedrooms - Single beds / secondary side (p. 254)",
            "verification_status": "verified",
            "notes": "Secondary side of single bed or against-wall configuration minimum clearance 550 mm."
        },
        {
            "id": "BED_FOOT_CIRCULATION",
            "applicable_categories": ["bed"],
            "clearance_direction": "front",
            "threshold_m": 0.75,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Bedrooms (p. 254)",
            "verification_status": "verified",
            "notes": "Minimum 750 mm corridor width at the foot of the bed between bed frame and opposite wall/furniture."
        },
        {
            "id": "WARDROBE_HINGED_FRONT",
            "applicable_categories": ["wardrobe"],
            "clearance_direction": "front",
            "threshold_m": 0.90,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Wardrobes and built-in cupboards (p. 256)",
            "verification_status": "verified",
            "notes": "Requires minimum 900 mm front clearance to allow 500-600mm door swing plus person bending/kneeling."
        },
        {
            "id": "WARDROBE_SLIDING_FRONT",
            "applicable_categories": ["wardrobe"],
            "clearance_direction": "front",
            "threshold_m": 0.75,
            "priority": "hard",
            "source_title": "Human Dimension & Interior Space (Panero & Zelnik)",
            "source_edition": "1st Edition (Whitney Library of Design / Architectural Press, 1979)",
            "source_section": "Residential Spaces: Bedroom Storage Clearance (p. 152)",
            "verification_status": "verified",
            "notes": "Sliding door wardrobes eliminate swing, requiring 750 mm for human passage and standing access."
        },
        # LIVING ROOM ERGONOMIC RULES
        {
            "id": "LIVING_SOFA_FRONT",
            "applicable_categories": ["sofa", "armchair"],
            "clearance_direction": "front",
            "threshold_m": 0.40,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Living areas - Seating ergonomics (p. 252)",
            "verification_status": "verified",
            "notes": "Minimum 400 mm knee/legroom clearance between sofa seat edge and coffee table."
        },
        {
            "id": "SOFA_TO_COFFEE_TABLE",
            "applicable_categories": ["coffee_table"],
            "clearance_direction": "all_sides",
            "threshold_m": 0.40,
            "priority": "soft",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Living areas - Coffee table reach (p. 252)",
            "verification_status": "verified",
            "notes": "Maximum 450-500 mm reach distance from sofa edge to coffee table surface for comfortable use."
        },
        {
            "id": "TV_VIEWING_DISTANCE_MIN",
            "applicable_categories": ["tv_console", "media_wall"],
            "clearance_direction": "front",
            "threshold_m": 1.80,
            "priority": "soft",
            "source_title": "SMPTE (Society of Motion Picture and Television Engineers) & THX Viewing Guidelines",
            "source_edition": "SMPTE EG-18 / THX Home Theater Recommendations",
            "source_section": "Optimal Display Distance for 4K / UHD Resolution",
            "verification_status": "verified",
            "notes": "Minimum viewing distance of 1.8m for 55-inch displays (30-degree field of view); scale with display size."
        },
        # DINING ERGONOMIC RULES
        {
            "id": "DINING_CHAIR_PULLOUT",
            "applicable_categories": ["dining_table"],
            "clearance_direction": "all_sides",
            "threshold_m": 0.80,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Dining areas - Table and chair clearances (p. 260)",
            "verification_status": "verified",
            "notes": "Minimum 800 mm clearance from table perimeter to wall or obstacle to allow chair pull-out and seating ingress."
        },
        {
            "id": "DINING_CIRCULATION_BEHIND",
            "applicable_categories": ["dining_table"],
            "clearance_direction": "all_sides",
            "threshold_m": 1.10,
            "priority": "soft",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Buildings: Dining spaces - Service passage (p. 260)",
            "verification_status": "verified",
            "notes": "1100 mm clearance required where diners are seated and another person passes behind to serve food."
        },
        # WORK & DESK RULES
        {
            "id": "DESK_CHAIR_MOVEMENT",
            "applicable_categories": ["desk"],
            "clearance_direction": "front",
            "threshold_m": 0.90,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Offices: Workstation dimensions and chair push-back space (p. 364)",
            "verification_status": "verified",
            "notes": "Minimum 900 mm depth required behind work surface to permit task chair push-back and standing exit."
        },
        {
            "id": "SHELF_ACCESS_FRONT",
            "applicable_categories": ["bookshelf", "storage_cabinet"],
            "clearance_direction": "front",
            "threshold_m": 0.70,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Libraries and Domestic Storage: Shelf aisle widths (p. 182)",
            "verification_status": "verified",
            "notes": "Minimum 700 mm front clearance for squatting or reaching lower book/storage shelves."
        },
        # KITCHEN ERGONOMIC RULES
        {
            "id": "KITCHEN_WORK_CLEARANCE",
            "applicable_categories": ["kitchen_counter", "sink", "cooktop", "dishwasher", "refrigerator"],
            "clearance_direction": "front",
            "threshold_m": 1.05,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Kitchens: Activity zones and appliance door clearance (p. 258)",
            "verification_status": "verified",
            "notes": "Minimum 1050 mm clearance in front of kitchen counters to permit oven/dishwasher door drop and user standing."
        },
        {
            "id": "KITCHEN_AISLE_CLEARANCE",
            "applicable_categories": ["kitchen_island"],
            "clearance_direction": "all_sides",
            "threshold_m": 1.20,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Domestic Kitchens: Two-cook working aisles (p. 258)",
            "verification_status": "verified",
            "notes": "1200 mm width required for parallel counters or island-to-counter aisle to allow two people to pass freely."
        },
        # BATHROOM ERGONOMIC RULES
        {
            "id": "BATH_COMMODE_CLEARANCE",
            "applicable_categories": ["commode"],
            "clearance_direction": "front",
            "threshold_m": 0.60,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Sanitary Facilities: WC space requirements (p. 262)",
            "verification_status": "verified",
            "notes": "Minimum 600 mm front activity clearance and 200 mm side clearance on each side of WC bowl centreline."
        },
        {
            "id": "BATH_BASIN_FRONT",
            "applicable_categories": ["basin", "vanity_unit"],
            "clearance_direction": "front",
            "threshold_m": 0.70,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Sanitary Facilities: Washbasin space requirements (p. 264)",
            "verification_status": "verified",
            "notes": "Minimum 700 mm depth in front of washbasin for bending forward to wash face."
        },
        {
            "id": "BATH_SHOWER_ENTRY",
            "applicable_categories": ["shower_enclosure", "bathtub"],
            "clearance_direction": "front",
            "threshold_m": 0.70,
            "priority": "hard",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "Sanitary Facilities: Shower and bath access zones (p. 263)",
            "verification_status": "verified",
            "notes": "Minimum 700 mm unobstructed floor area outside shower door / bath entry point."
        },
        # GENERAL CIRCULATION & ACCESSIBILITY
        {
            "id": "GENERAL_CIRCULATION",
            "applicable_categories": ["all"],
            "clearance_direction": "circulation",
            "threshold_m": 0.75,
            "priority": "soft",
            "source_title": "Architects' Data (Ernst Neufert)",
            "source_edition": "4th International English Edition (Wiley-Blackwell, 2012)",
            "source_section": "General Principles: Circulation spaces and domestic corridors (p. 27)",
            "verification_status": "verified",
            "notes": "Minimum 750 mm clear walking passage across all primary domestic transit paths."
        },
        {
            "id": "ACCESSIBLE_CIRCULATION_WHEELCHAIR",
            "applicable_categories": ["all"],
            "clearance_direction": "circulation",
            "threshold_m": 0.90,
            "priority": "hard",
            "source_title": "ADA Accessibility Guidelines (ADAAG 2010 Section 403) & Neufert (p. 31)",
            "source_edition": "2010 ADA Standards for Accessible Design / Department of Justice",
            "source_section": "Section 403: Walking Surfaces - Clear Width (36 inches / 915 mm)",
            "verification_status": "verified",
            "notes": "Minimum 900 mm continuous clear width along accessible routes for wheelchair circulation."
        },
        # PROVISIONAL & HEURISTIC RULES (Audited & Distinctly Classified)
        {
            "id": "BEDSIDE_SOCKET_REACH_HEURISTIC",
            "applicable_categories": ["bed", "usb_charging_point"],
            "clearance_direction": "both_sides",
            "threshold_m": 0.45,
            "priority": "soft",
            "source_title": "Internal Heuristic Design Rule",
            "source_edition": "ESAI Research Heuristics v2.0",
            "source_section": "Convenience Charging Proximity",
            "verification_status": "provisional",
            "notes": "Provisional design recommendation: bedside charging outlet should be within 450mm lateral reach of mattress edge."
        },
        {
            "id": "CUSTOM_EXPERIMENTAL_CLEARANCE",
            "applicable_categories": ["all"],
            "clearance_direction": "front",
            "threshold_m": 0.50,
            "priority": "configurable",
            "source_title": "Draft Internal Research Guideline (Unverified)",
            "source_edition": "Experimental Prototype",
            "source_section": "Non-published test rule",
            "verification_status": "unverified",
            "notes": "Explicitly unverified rule retained for audit testing; must never be promoted to a mandatory standard."
        }
    ]
}

with open(rules_path, "w", encoding="utf-8") as f:
    json.dump(rules_data, f, indent=2)
print(f"Ergonomic rules updated: {len(rules_data['rules'])} rules saved to {rules_path}")


# ─── 5. COMPLETE ROOM PROFILES ────────────────────────────────────────────────
profiles_path = os.path.join(DATA_DIR, "room_profiles.json")
profiles_data = {
    "version": "2.0",
    "profiles": [
        {
            "room_type": "master_bedroom",
            "display_name": "Master Bedroom",
            "recommended_assets": ["bed", "bedside_table", "wardrobe", "dressing_table"],
            "optional_assets": ["armchair", "tv_console", "side_table", "bookshelf", "ceiling_fan"],
            "incompatible_assets": ["dining_table", "kitchen_counter", "shower_enclosure", "commode"],
            "default_min_area_sqm": 12.0,
            "typical_zones": ["sleeping_zone", "dressing_zone", "relaxation_zone"],
            "service_dependencies": ["power_general", "usb_charging", "ac_power", "lighting"],
            "functional_relationships": [
                {"from_category": "bedside_table", "to_category": "bed", "affinity": "adjacent", "max_distance_m": 0.3},
                {"from_category": "wardrobe", "to_category": "bed", "affinity": "clearance_separated", "min_distance_m": 0.9}
            ]
        },
        {
            "room_type": "bedroom",
            "display_name": "Standard Bedroom",
            "recommended_assets": ["bed", "bedside_table", "wardrobe", "desk", "office_chair"],
            "optional_assets": ["bookshelf", "ceiling_fan", "storage_cabinet"],
            "incompatible_assets": ["dining_table", "kitchen_counter", "commode"],
            "default_min_area_sqm": 9.0,
            "typical_zones": ["sleeping_zone", "study_zone", "storage_zone"],
            "service_dependencies": ["power_general", "usb_charging", "lighting"],
            "functional_relationships": [
                {"from_category": "bedside_table", "to_category": "bed", "affinity": "adjacent", "max_distance_m": 0.3},
                {"from_category": "desk", "to_category": "office_chair", "affinity": "paired", "max_distance_m": 0.1}
            ]
        },
        {
            "room_type": "guest_room",
            "display_name": "Guest Bedroom",
            "recommended_assets": ["bed", "bedside_table", "wardrobe"],
            "optional_assets": ["armchair", "desk", "office_chair", "ceiling_fan"],
            "incompatible_assets": ["kitchen_counter", "commode"],
            "default_min_area_sqm": 9.0,
            "typical_zones": ["sleeping_zone", "luggage_storage"],
            "service_dependencies": ["power_general", "lighting"],
            "functional_relationships": [
                {"from_category": "bedside_table", "to_category": "bed", "affinity": "adjacent", "max_distance_m": 0.3}
            ]
        },
        {
            "room_type": "living_room",
            "display_name": "Living Room",
            "recommended_assets": ["sofa", "coffee_table", "tv_console"],
            "optional_assets": ["armchair", "side_table", "bookshelf", "media_wall", "ceiling_fan"],
            "incompatible_assets": ["bed", "shower_enclosure", "commode"],
            "default_min_area_sqm": 16.0,
            "typical_zones": ["conversation_zone", "entertainment_zone", "transit_aisle"],
            "service_dependencies": ["power_general", "tv_power", "tv_data", "ac_power", "lighting"],
            "functional_relationships": [
                {"from_category": "coffee_table", "to_category": "sofa", "affinity": "front_facing", "distance_m": 0.45},
                {"from_category": "tv_console", "to_category": "sofa", "affinity": "opposite_viewing", "min_distance_m": 2.0, "max_distance_m": 4.0}
            ]
        },
        {
            "room_type": "family_living_area",
            "display_name": "Family Living Area",
            "recommended_assets": ["sofa", "coffee_table", "tv_console"],
            "optional_assets": ["armchair", "bookshelf", "storage_cabinet"],
            "incompatible_assets": ["bed", "shower_enclosure"],
            "default_min_area_sqm": 14.0,
            "typical_zones": ["lounge_zone", "media_zone"],
            "service_dependencies": ["power_general", "tv_power", "lighting"],
            "functional_relationships": [
                {"from_category": "coffee_table", "to_category": "sofa", "affinity": "front_facing", "distance_m": 0.45}
            ]
        },
        {
            "room_type": "tv_lobby",
            "display_name": "TV Lobby",
            "recommended_assets": ["sofa", "tv_console"],
            "optional_assets": ["coffee_table", "side_table"],
            "incompatible_assets": ["bed", "kitchen_counter"],
            "default_min_area_sqm": 10.0,
            "typical_zones": ["media_viewing"],
            "service_dependencies": ["power_general", "tv_power", "tv_data"],
            "functional_relationships": [
                {"from_category": "tv_console", "to_category": "sofa", "affinity": "opposite_viewing", "min_distance_m": 1.8, "max_distance_m": 3.5}
            ]
        },
        {
            "room_type": "tv_lounge",
            "display_name": "TV Lounge",
            "recommended_assets": ["sofa", "tv_console", "coffee_table"],
            "optional_assets": ["armchair", "media_wall"],
            "incompatible_assets": ["bed"],
            "default_min_area_sqm": 12.0,
            "typical_zones": ["home_cinema_lounge"],
            "service_dependencies": ["tv_power", "tv_data", "power_general"],
            "functional_relationships": [
                {"from_category": "tv_console", "to_category": "sofa", "affinity": "opposite_viewing", "min_distance_m": 2.0, "max_distance_m": 3.8}
            ]
        },
        {
            "room_type": "lounge",
            "display_name": "Formal Lounge",
            "recommended_assets": ["sofa", "coffee_table", "armchair"],
            "optional_assets": ["side_table", "bookshelf"],
            "incompatible_assets": ["bed", "commode"],
            "default_min_area_sqm": 14.0,
            "typical_zones": ["formal_conversation"],
            "service_dependencies": ["power_general", "lighting"],
            "functional_relationships": [
                {"from_category": "coffee_table", "to_category": "sofa", "affinity": "front_facing", "distance_m": 0.45}
            ]
        },
        {
            "room_type": "dining_room",
            "display_name": "Dining Room",
            "recommended_assets": ["dining_table", "dining_chair"],
            "optional_assets": ["storage_cabinet", "pendant_light"],
            "incompatible_assets": ["bed", "commode", "shower_enclosure"],
            "default_min_area_sqm": 10.0,
            "typical_zones": ["dining_table_zone", "buffet_serving"],
            "service_dependencies": ["power_general", "lighting"],
            "functional_relationships": [
                {"from_category": "dining_chair", "to_category": "dining_table", "affinity": "tucked_under", "max_distance_m": 0.2}
            ]
        },
        {
            "room_type": "dining_area",
            "display_name": "Dining Area",
            "recommended_assets": ["dining_table", "dining_chair"],
            "optional_assets": ["storage_cabinet"],
            "incompatible_assets": ["bed", "commode"],
            "default_min_area_sqm": 8.0,
            "typical_zones": ["dining_zone"],
            "service_dependencies": ["lighting"],
            "functional_relationships": [
                {"from_category": "dining_chair", "to_category": "dining_table", "affinity": "tucked_under", "max_distance_m": 0.2}
            ]
        },
        {
            "room_type": "kitchen",
            "display_name": "Kitchen",
            "recommended_assets": ["kitchen_counter", "sink", "cooktop", "refrigerator"],
            "optional_assets": ["kitchen_island", "dishwasher", "range_hood", "oven", "pantry_cabinet"],
            "incompatible_assets": ["bed", "sofa", "commode", "bathtub"],
            "default_min_area_sqm": 7.0,
            "typical_zones": ["prep_zone", "cooking_zone", "cleaning_zone", "cold_storage"],
            "service_dependencies": ["power_appliance", "water_cold", "water_hot", "drainage", "exhaust_duct"],
            "functional_relationships": [
                {"from_category": "kitchen_island", "to_category": "kitchen_counter", "affinity": "parallel_aisle", "min_distance_m": 1.2},
                {"from_category": "range_hood", "to_category": "cooktop", "affinity": "aligned_above", "distance_m": 0.65}
            ]
        },
        {
            "room_type": "pantry",
            "display_name": "Pantry",
            "recommended_assets": ["pantry_cabinet", "kitchen_counter"],
            "optional_assets": ["sink", "refrigerator"],
            "incompatible_assets": ["bed", "sofa", "commode"],
            "default_min_area_sqm": 4.0,
            "typical_zones": ["dry_storage", "prep"],
            "service_dependencies": ["power_general", "lighting"],
            "functional_relationships": []
        },
        {
            "room_type": "bathroom",
            "display_name": "Bathroom",
            "recommended_assets": ["basin", "commode", "shower_enclosure"],
            "optional_assets": ["bathtub", "towel_rail", "vanity_unit"],
            "incompatible_assets": ["bed", "sofa", "dining_table", "cooktop"],
            "default_min_area_sqm": 3.5,
            "typical_zones": ["grooming_zone", "sanitary_zone", "bathing_zone"],
            "service_dependencies": ["water_cold", "water_hot", "drainage", "exhaust_duct"],
            "functional_relationships": [
                {"from_category": "basin", "to_category": "commode", "affinity": "side_by_side", "min_distance_m": 0.3}
            ]
        },
        {
            "room_type": "attached_bathroom",
            "display_name": "Attached Bathroom (Ensuite)",
            "recommended_assets": ["basin", "commode", "shower_enclosure"],
            "optional_assets": ["bathtub", "towel_rail", "vanity_unit"],
            "incompatible_assets": ["bed", "sofa", "kitchen_counter"],
            "default_min_area_sqm": 4.0,
            "typical_zones": ["private_grooming", "shower_zone", "toilet_zone"],
            "service_dependencies": ["water_cold", "water_hot", "drainage"],
            "functional_relationships": [
                {"from_category": "basin", "to_category": "commode", "affinity": "side_by_side", "min_distance_m": 0.3}
            ]
        },
        {
            "room_type": "common_bathroom",
            "display_name": "Common Bathroom",
            "recommended_assets": ["basin", "commode", "shower_enclosure"],
            "optional_assets": ["towel_rail"],
            "incompatible_assets": ["bed", "kitchen_counter"],
            "default_min_area_sqm": 3.2,
            "typical_zones": ["guest_sanitary", "shower"],
            "service_dependencies": ["water_cold", "water_hot", "drainage"],
            "functional_relationships": []
        },
        {
            "room_type": "toilet",
            "display_name": "Powder Room / Toilet",
            "recommended_assets": ["commode", "basin"],
            "optional_assets": [],
            "incompatible_assets": ["bed", "bathtub", "kitchen_counter", "sofa"],
            "default_min_area_sqm": 1.8,
            "typical_zones": ["guest_wc"],
            "service_dependencies": ["water_cold", "drainage"],
            "functional_relationships": [
                {"from_category": "basin", "to_category": "commode", "affinity": "side_by_side", "min_distance_m": 0.25}
            ]
        },
        {
            "room_type": "study",
            "display_name": "Study",
            "recommended_assets": ["desk", "office_chair", "bookshelf"],
            "optional_assets": ["armchair", "side_table"],
            "incompatible_assets": ["bed", "commode", "cooktop"],
            "default_min_area_sqm": 7.5,
            "typical_zones": ["focus_workstation", "reference_library"],
            "service_dependencies": ["power_general", "network_data", "lighting"],
            "functional_relationships": [
                {"from_category": "office_chair", "to_category": "desk", "affinity": "paired", "max_distance_m": 0.1}
            ]
        },
        {
            "room_type": "study_office",
            "display_name": "Study / Office",
            "recommended_assets": ["desk", "office_chair", "bookshelf"],
            "optional_assets": ["workstation", "armchair", "storage_cabinet"],
            "incompatible_assets": ["bed", "commode"],
            "default_min_area_sqm": 8.0,
            "typical_zones": ["workstation", "client_consultation"],
            "service_dependencies": ["power_general", "network_data"],
            "functional_relationships": [
                {"from_category": "office_chair", "to_category": "desk", "affinity": "paired", "max_distance_m": 0.1}
            ]
        },
        {
            "room_type": "home_office",
            "display_name": "Home Office",
            "recommended_assets": ["desk", "office_chair", "bookshelf"],
            "optional_assets": ["storage_cabinet", "armchair"],
            "incompatible_assets": ["bed", "commode"],
            "default_min_area_sqm": 8.5,
            "typical_zones": ["primary_desk", "video_call_backdrop"],
            "service_dependencies": ["power_general", "network_data", "ac_power"],
            "functional_relationships": [
                {"from_category": "office_chair", "to_category": "desk", "affinity": "paired", "max_distance_m": 0.1}
            ]
        },
        {
            "room_type": "utility_room",
            "display_name": "Utility Room",
            "recommended_assets": ["washing_machine", "storage_cabinet"],
            "optional_assets": ["dryer", "sink"],
            "incompatible_assets": ["bed", "sofa", "dining_table"],
            "default_min_area_sqm": 4.0,
            "typical_zones": ["laundry_processing", "maintenance_storage"],
            "service_dependencies": ["power_appliance", "water_cold", "drainage"],
            "functional_relationships": [
                {"from_category": "dryer", "to_category": "washing_machine", "affinity": "side_by_side", "max_distance_m": 0.1}
            ]
        },
        {
            "room_type": "laundry_room",
            "display_name": "Laundry Room",
            "recommended_assets": ["washing_machine", "dryer", "storage_cabinet"],
            "optional_assets": ["sink"],
            "incompatible_assets": ["bed", "sofa"],
            "default_min_area_sqm": 4.5,
            "typical_zones": ["wash_dry_cycle", "sorting_folding"],
            "service_dependencies": ["power_appliance", "water_cold", "drainage", "exhaust_duct"],
            "functional_relationships": [
                {"from_category": "dryer", "to_category": "washing_machine", "affinity": "side_by_side", "max_distance_m": 0.1}
            ]
        },
        {
            "room_type": "foyer",
            "display_name": "Foyer / Entrance Hall",
            "recommended_assets": ["shoe_cabinet"],
            "optional_assets": ["side_table", "bookshelf"],
            "incompatible_assets": ["bed", "kitchen_counter", "commode"],
            "default_min_area_sqm": 3.0,
            "typical_zones": ["arrival_transition", "shoe_change"],
            "service_dependencies": ["lighting"],
            "functional_relationships": []
        },
        {
            "room_type": "hallway",
            "display_name": "Hallway / Circulation",
            "recommended_assets": [],
            "optional_assets": [],
            "incompatible_assets": ["bed", "dining_table", "kitchen_counter"],
            "default_min_area_sqm": 2.5,
            "typical_zones": ["transit_corridor"],
            "service_dependencies": ["lighting"],
            "functional_relationships": []
        }
    ]
}

with open(profiles_path, "w", encoding="utf-8") as f:
    json.dump(profiles_data, f, indent=2)
print(f"Room profiles updated: {len(profiles_data['profiles'])} profiles saved to {profiles_path}")


# ─── 6. EXPANDED FUNCTIONAL RELATIONS ──────────────────────────────────────────
relations_path = os.path.join(DATA_DIR, "functional_relations.json")
relations_data = {
    "version": "2.0",
    "rules": [
        {
            "primary_category": "sofa",
            "related_category": "coffee_table",
            "relation_type": "facing",
            "optimal_distance_m": 0.45,
            "min_distance_m": 0.35,
            "max_distance_m": 0.55,
            "is_hard_constraint": True
        },
        {
            "primary_category": "sofa",
            "related_category": "tv_console",
            "relation_type": "viewing",
            "optimal_distance_m": 2.50,
            "min_distance_m": 1.80,
            "max_distance_m": 4.00,
            "is_hard_constraint": False
        },
        {
            "primary_category": "bed",
            "related_category": "bedside_table",
            "relation_type": "flanking",
            "optimal_distance_m": 0.10,
            "min_distance_m": 0.05,
            "max_distance_m": 0.25,
            "is_hard_constraint": False
        },
        {
            "primary_category": "desk",
            "related_category": "office_chair",
            "relation_type": "paired",
            "optimal_distance_m": 0.20,
            "min_distance_m": 0.10,
            "max_distance_m": 0.40,
            "is_hard_constraint": True
        },
        {
            "primary_category": "dining_table",
            "related_category": "dining_chair",
            "relation_type": "surrounding",
            "optimal_distance_m": 0.15,
            "min_distance_m": 0.05,
            "max_distance_m": 0.30,
            "is_hard_constraint": True
        },
        {
            "primary_category": "kitchen_island",
            "related_category": "kitchen_counter",
            "relation_type": "parallel_aisle",
            "optimal_distance_m": 1.20,
            "min_distance_m": 1.05,
            "max_distance_m": 1.50,
            "is_hard_constraint": True
        },
        {
            "primary_category": "cooktop",
            "related_category": "range_hood",
            "relation_type": "aligned_above",
            "optimal_distance_m": 0.65,
            "min_distance_m": 0.60,
            "max_distance_m": 0.75,
            "is_hard_constraint": True
        },
        {
            "primary_category": "basin",
            "related_category": "bathroom_mirror",
            "relation_type": "aligned_above",
            "optimal_distance_m": 0.30,
            "min_distance_m": 0.20,
            "max_distance_m": 0.45,
            "is_hard_constraint": False
        },
        {
            "primary_category": "washing_machine",
            "related_category": "dryer",
            "relation_type": "side_by_side",
            "optimal_distance_m": 0.05,
            "min_distance_m": 0.02,
            "max_distance_m": 0.20,
            "is_hard_constraint": False
        }
    ]
}

with open(relations_path, "w", encoding="utf-8") as f:
    json.dump(relations_data, f, indent=2)
print(f"Functional relations updated: {len(relations_data['rules'])} rules saved to {relations_path}")
