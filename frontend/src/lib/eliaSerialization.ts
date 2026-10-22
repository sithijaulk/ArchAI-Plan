import type { ELIARequirements, AcceptedPlantAlternative } from '@/types/elia';

// Location & Solar
export type EliaSelectedLocation = {
  id?: number;
  name?: string;
  display_name?: string;
  latitude: number;
  longitude: number;
  timezone?: string | null;
  city?: string;
  country?: string;
  country_code?: string;
  attribution?: string;
  [key: string]: any;
};

export interface EliaFormState {
  generationMode: 'baseline' | 'trained_model';
  designStyle: string;
  greeneryDensity: 'low' | 'medium' | 'high';
  openSpaceRatio: number | string;
  shadeTreePreference: boolean;

  // Group B: Parking & Garage
  parkingRequired: boolean;
  parkingType: 'garage' | 'covered' | 'open' | 'no_preference';
  garageRequired: boolean;
  garageCapacity: number | string;
  vehicleCount: number | string;
  vehicleType?: string;
  turningSpaceRequired: boolean;

  // Group C: Driveway, Walkways, Gate
  drivewayRequired: boolean;
  drivewayStyle: string;
  drivewaySurface: string;
  pedestrianPathRequired: boolean;
  gardenPathRequired: boolean;
  walkingPathSurface: string;
  gateRequired: boolean;
  gateType: string;
  gateWidthM: number | string;
  gateOpeningMechanism: string;
  gateStyle: string;

  // Group D: Ground Finishes
  gardenGroundFinish: 'grass' | 'interlock' | 'paving_stones' | 'mixed';

  // Group E: Garden & Ground Planting
  gardenRequired: boolean;
  lawnRequired: boolean;
  treesRequired: boolean;
  treeQuantity?: number | string;
  compactTreesPreference: boolean;
  shrubsRequired: boolean;
  shrubsQuantity?: number | string;
  flowerBedsRequired: boolean;
  groundPlantersRequired: boolean;
  groundPlantersCount?: number | string;
  gardenSeatingRequired: boolean;
  gardenSeatingCount?: number | string;
  gardenTableSetRequired: boolean;
  gardenTableSetCount?: number | string;

  // Group F: Walls & Vertical Greenery
  boundaryWallRequired: boolean;
  boundaryWallType: string;
  boundaryWallHeightM: number | string;
  verticalGreeneryMode: 'automatic' | 'preferred' | 'disabled';
  wallClimbingPlants: boolean;
  wallMountedGreenery: boolean;
  hangingTrailingGreenery: boolean;
  acceptVerticalAlternatives: boolean;

  // Group G: Balconies
  balconyPlantingRequired: boolean;
  balconyPottedPlants: boolean;
  balconyHangingPlants: boolean;
  balconySeatingRequired: boolean;
  balconyPlantIds: string[];
  targetBalconyIds: string[];

  // Group H: Rooftop / Terrace
  rooftopPlantingRequired: boolean;
  rooftopPlantersRequired: boolean;
  rooftopSeatingRequired: boolean;
  rooftopTablesRequired: boolean;
  targetTerraceIds: string[];

  // Group I: Outdoor Lighting
  lightingRequired: boolean;
  lightingStyle: string;
  lightingSpacingM?: number | string;
  lightingFixtureCount?: number | string;
  gardenLighting: boolean;
  pathwayLighting: boolean;
  seatingLighting: boolean;
  wallLighting: boolean;

  // Group J: Water Features & Utilities
  wellRequired: boolean;
  gardenTapsRequired: boolean;
  gardenTapsCount?: number | string;
  pondRequired: boolean;
  poolRequired: boolean;
  septicTankRequired: boolean;

  // Group K: Solar
  solarRequired: boolean;
  preferredRoofSurface: 'flat_roof' | 'south_facing' | 'north_facing' | 'auto' | 'any';
  placementPriority: 'maximum_yield' | 'concealed_from_street' | 'balanced';
  includeLiveSolar: boolean;

  // Environmental & Botanical Preferences
  maintenancePreference: 'low' | 'medium' | 'high' | 'no_preference';
  waterAvailability: 'limited' | 'regular' | 'irrigation_available' | 'unknown';
  climateZone?: 'wet_zone' | 'intermediate_zone' | 'dry_zone' | 'arid_zone' | 'unknown';
  siteExposure?: 'sheltered' | 'moderate' | 'exposed' | 'coastal_wind' | 'unknown';
  preferredPlantIds?: string[];
  plantIdsToAvoid?: string[];
  acceptedPlantAlternatives?: AcceptedPlantAlternative[];
  rejectedPlantAlternatives?: string[];
  lockedFeatures?: any[];

  // Location & Solar
  selectedLocation: EliaSelectedLocation | null;
}

export interface ValidationFieldErrors {
  [field: string]: string;
}

/**
 * Strictly parses a finite integer.
 * Rejects floats, non-finite values (NaN, Infinity), and strings with trailing text.
 */
export function parseStrictInteger(
  value: unknown,
  fieldName = 'Value',
  options?: { min?: number; max?: number; required?: boolean }
): { valid: boolean; value?: number; error?: string } {
  if (value === null || value === undefined || value === '') {
    if (options?.required) {
      return { valid: false, error: `${fieldName} is required.` };
    }
    return { valid: true };
  }

  let num: number;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return { valid: false, error: `${fieldName} must be a finite number.` };
    }
    if (!Number.isInteger(value)) {
      return { valid: false, error: `${fieldName} must be an integer (whole number).` };
    }
    num = value;
  } else if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!/^-?\d+$/.test(trimmed)) {
      return { valid: false, error: `${fieldName} must be an integer without trailing characters or decimals.` };
    }
    num = Number(trimmed);
    if (!Number.isFinite(num)) {
      return { valid: false, error: `${fieldName} must be a finite number.` };
    }
  } else {
    return { valid: false, error: `${fieldName} must be a number.` };
  }

  if (options?.min !== undefined && num < options.min) {
    return { valid: false, error: `${fieldName} must be at least ${options.min}.` };
  }
  if (options?.max !== undefined && num > options.max) {
    return { valid: false, error: `${fieldName} must be at most ${options.max}.` };
  }

  return { valid: true, value: num };
}

/**
 * Strictly parses a finite floating-point number.
 * Rejects non-finite values (NaN, Infinity) and strings with trailing text.
 */
export function parseStrictFloat(
  value: unknown,
  fieldName = 'Value',
  options?: { min?: number; max?: number; gt?: number; required?: boolean }
): { valid: boolean; value?: number; error?: string } {
  if (value === null || value === undefined || value === '') {
    if (options?.required) {
      return { valid: false, error: `${fieldName} is required.` };
    }
    return { valid: true };
  }

  let num: number;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return { valid: false, error: `${fieldName} must be a finite number.` };
    }
    num = value;
  } else if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!/^-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(trimmed)) {
      return { valid: false, error: `${fieldName} must be a valid number without trailing characters.` };
    }
    num = Number(trimmed);
    if (!Number.isFinite(num)) {
      return { valid: false, error: `${fieldName} must be a finite number.` };
    }
  } else {
    return { valid: false, error: `${fieldName} must be a number.` };
  }

  if (options?.gt !== undefined && num <= options.gt) {
    return { valid: false, error: `${fieldName} must be greater than ${options.gt}.` };
  }
  if (options?.min !== undefined && num < options.min) {
    return { valid: false, error: `${fieldName} must be at least ${options.min}.` };
  }
  if (options?.max !== undefined && num > options.max) {
    return { valid: false, error: `${fieldName} must be at most ${options.max}.` };
  }

  return { valid: true, value: num };
}

/**
 * Validates requirements form inputs against authoritative backend schema constraints.
 */
export function validateRequirementsForm(form: Partial<EliaFormState>): {
  valid: boolean;
  errors: ValidationFieldErrors;
} {
  const errors: ValidationFieldErrors = {};

  // Parking & Garage contradictions
  if (form.parkingRequired === false && form.garageRequired) {
    errors.garageRequired = 'Cannot request a garage when parking is explicitly disabled.';
  }

  const vehRes = parseStrictInteger(form.vehicleCount, 'Vehicle count', {
    min: 0,
  });
  if (!vehRes.valid) {
    errors.vehicleCount = vehRes.error!;
  } else if (vehRes.value === 0 && form.garageRequired) {
    errors.vehicleCount = 'Cannot request a garage when vehicle count is 0.';
  }

  if (form.parkingRequired !== false && form.garageRequired) {
    const maxCapacity = form.generationMode === 'baseline' ? 3 : 10;
    const capRes = parseStrictInteger(form.garageCapacity, 'Garage capacity', {
      required: true,
      min: 1,
      max: maxCapacity,
    });
    if (!capRes.valid) {
      errors.garageCapacity = capRes.error!;
    }
  }

  if (form.gateWidthM !== undefined && form.gateWidthM !== '') {
    const widthRes = parseStrictFloat(form.gateWidthM, 'Gate width', {
      gt: 0,
      min: 1.0,
      max: 10.0,
    });
    if (!widthRes.valid) {
      errors.gateWidthM = widthRes.error!;
    }
  }

  if (form.boundaryWallRequired) {
    const heightRes = parseStrictFloat(form.boundaryWallHeightM, 'Boundary wall height', {
      required: true,
      gt: 0,
      min: 0.5,
      max: 6.0,
    });
    if (!heightRes.valid) {
      errors.boundaryWallHeightM = heightRes.error!;
    }
  }

  if (form.lightingRequired && form.lightingSpacingM !== undefined && form.lightingSpacingM !== '') {
    const spacingRes = parseStrictFloat(form.lightingSpacingM, 'Lighting fixture spacing', {
      gt: 0,
    });
    if (!spacingRes.valid) {
      errors.lightingSpacingM = spacingRes.error!;
    }
  }

  if (form.treesRequired && form.treeQuantity !== undefined && form.treeQuantity !== '') {
    const treeRes = parseStrictInteger(form.treeQuantity, 'Tree quantity', { min: 0 });
    if (!treeRes.valid) errors.treeQuantity = treeRes.error!;
  }

  if (form.shrubsRequired && form.shrubsQuantity !== undefined && form.shrubsQuantity !== '') {
    const shrubRes = parseStrictInteger(form.shrubsQuantity, 'Shrubs quantity', { min: 0 });
    if (!shrubRes.valid) errors.shrubsQuantity = shrubRes.error!;
  }

  if (form.groundPlantersRequired && form.groundPlantersCount !== undefined && form.groundPlantersCount !== '') {
    const planterRes = parseStrictInteger(form.groundPlantersCount, 'Planters count', { min: 0 });
    if (!planterRes.valid) errors.groundPlantersCount = planterRes.error!;
  }

  if (form.gardenTapsRequired && form.gardenTapsCount !== undefined && form.gardenTapsCount !== '') {
    const tapRes = parseStrictInteger(form.gardenTapsCount, 'Garden taps count', { min: 1 });
    if (!tapRes.valid) errors.gardenTapsCount = tapRes.error!;
  }

  if (form.openSpaceRatio !== undefined && form.openSpaceRatio !== '') {
    const ratioRes = parseStrictFloat(form.openSpaceRatio, 'Open space ratio', {
      min: 0.0,
      max: 1.0,
    });
    if (!ratioRes.valid) {
      errors.openSpaceRatio = ratioRes.error!;
    }
  }

  if (form.selectedLocation) {
    const latRes = parseStrictFloat(form.selectedLocation.latitude, 'Latitude', { min: -90, max: 90, required: true });
    if (!latRes.valid) errors.latitude = latRes.error!;
    const lonRes = parseStrictFloat(form.selectedLocation.longitude, 'Longitude', { min: -180, max: 180, required: true });
    if (!lonRes.valid) errors.longitude = lonRes.error!;
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  };
}

/**
 * Serializes the form state into the canonical ELIARequirements payload.
 * Strictly omits dependent fields when their parent option is disabled.
 * Preserves false and zero values when explicitly valid.
 */
export function serializeRequirements(form: Partial<EliaFormState>): ELIARequirements {
  const isParkingActive = form.parkingRequired !== false;

  const req: ELIARequirements = {
    units: 'm',
    design_style: form.designStyle || 'modern',
    ...(form.greeneryDensity ? { greenery_level: form.greeneryDensity } : {}),
    landscape_priority: 'balanced',
    vertical_greenery_enabled: form.verticalGreeneryMode !== 'disabled',
    include_live_solar: Boolean(form.includeLiveSolar),
    access: {
      parking_required: isParkingActive,
      parking_type: form.parkingType || 'no_preference',
      garage_required: isParkingActive && Boolean(form.garageRequired),
      driveway_required: Boolean(form.drivewayRequired),
      gate_required: form.gateRequired !== false,
      turning_space_required: isParkingActive && Boolean(form.turningSpaceRequired),
    },
    landscape: {
      garden_required: form.gardenRequired !== false,
      lawn_required: Boolean(form.lawnRequired || form.gardenGroundFinish === 'grass'),
      ...(form.gardenGroundFinish ? { garden_ground_finish: form.gardenGroundFinish } : {}),
      ...(form.greeneryDensity ? { greenery_density: form.greeneryDensity } : {}),
      trees_required: form.treesRequired !== false,
      compact_trees_preference: Boolean(form.compactTreesPreference),
      shrubs_required: Boolean(form.shrubsRequired),
      flower_beds_required: Boolean(form.flowerBedsRequired),
      ground_planters_required: Boolean(form.groundPlantersRequired),
      shade_tree_preference: Boolean(form.shadeTreePreference),
      garden_seating_required: Boolean(form.gardenSeatingRequired),
      garden_table_set_required: Boolean(form.gardenTableSetRequired),
      pedestrian_path_required: Boolean(form.pedestrianPathRequired),
      garden_path_required: Boolean(form.gardenPathRequired),
      boundary_wall_required: Boolean(form.boundaryWallRequired),
    },
    vertical_greenery: {
      mode: form.verticalGreeneryMode || 'automatic',
      enabled: form.verticalGreeneryMode !== 'disabled',
      wall_climbing_plants: Boolean(form.wallClimbingPlants),
      wall_mounted_greenery: Boolean(form.wallMountedGreenery),
      hanging_trailing_greenery: Boolean(form.hangingTrailingGreenery),
      accept_vertical_alternatives: Boolean(form.acceptVerticalAlternatives),
    },
    balconies: {
      planting_required: Boolean(form.balconyPlantingRequired),
      potted_plants: Boolean(form.balconyPottedPlants),
      hanging_plants: Boolean(form.balconyHangingPlants),
      seating_required: Boolean(form.balconySeatingRequired),
      preferred_plant_ids: form.balconyPlantIds || [],
      target_balcony_ids: form.targetBalconyIds || [],
    },
    terrace: {
      planting_required: Boolean(form.rooftopPlantingRequired),
      planters_required: Boolean(form.rooftopPlantersRequired),
      seating_required: Boolean(form.rooftopSeatingRequired),
      tables_required: Boolean(form.rooftopTablesRequired),
      target_terrace_ids: form.targetTerraceIds || [],
    },
    lighting: {
      required: Boolean(form.lightingRequired),
      garden_lighting: Boolean(form.gardenLighting),
      pathway_lighting: Boolean(form.pathwayLighting),
      seating_lighting: Boolean(form.seatingLighting),
      wall_lighting: Boolean(form.wallLighting),
    },
    water_features: {
      well_required: Boolean(form.wellRequired),
      garden_taps_required: Boolean(form.gardenTapsRequired),
      pond_required: Boolean(form.pondRequired),
      swimming_pool_required: Boolean(form.poolRequired),
      septic_tank_required: Boolean(form.septicTankRequired),
    },
    solar: {
      panels_required: Boolean(form.solarRequired),
      preferred_roof_surface: form.preferredRoofSurface || 'auto',
      placement_priority: form.placementPriority || 'balanced',
      include_live_solar: Boolean(form.includeLiveSolar),
    },
  };

  // Group B: Dependent Parking & Garage
  if (isParkingActive) {
    const parsedVeh = parseStrictInteger(form.vehicleCount, 'Vehicle count');
    if (parsedVeh.valid && parsedVeh.value !== undefined) {
      req.access!.vehicle_count = parsedVeh.value;
    }
    if (form.garageRequired) {
      const parsedCap = parseStrictInteger(form.garageCapacity, 'Garage capacity');
      if (parsedCap.valid && parsedCap.value !== undefined) {
        req.access!.garage_capacity = parsedCap.value;
      }
    }
  } else {
    req.access!.vehicle_count = 0;
  }

  // Group C: Dependent Driveway & Walkway
  if (form.drivewayRequired) {
    if (form.drivewayStyle) req.access!.driveway_style = form.drivewayStyle;
    if (form.drivewaySurface) req.access!.driveway_surface = form.drivewaySurface;
  }
  if (form.pedestrianPathRequired || form.gardenPathRequired) {
    if (form.walkingPathSurface) req.access!.walking_path_surface = form.walkingPathSurface;
  }

  // Gate details
  if (form.gateRequired !== false) {
    if (form.gateType) req.access!.gate_type = form.gateType;
    if (form.gateOpeningMechanism) req.access!.gate_opening_mechanism = form.gateOpeningMechanism;
    if (form.gateStyle) req.access!.gate_style = form.gateStyle;
    const parsedWidth = parseStrictFloat(form.gateWidthM, 'Gate width');
    if (parsedWidth.valid && parsedWidth.value !== undefined) {
      req.access!.gate_width_m = parsedWidth.value;
    }
  }

  // Open space ratio
  const parsedRatio = parseStrictFloat(form.openSpaceRatio, 'Open space ratio');
  if (parsedRatio.valid && parsedRatio.value !== undefined) {
    req.landscape!.preferred_open_space_ratio = parsedRatio.value;
  }

  // Dependent Planting counts
  if (form.treesRequired !== false) {
    const parsedTrees = parseStrictInteger(form.treeQuantity, 'Tree quantity');
    if (parsedTrees.valid && parsedTrees.value !== undefined) {
      req.landscape!.tree_quantity = parsedTrees.value;
    }
  }
  if (form.shrubsRequired) {
    const parsedShrubs = parseStrictInteger(form.shrubsQuantity, 'Shrubs quantity');
    if (parsedShrubs.valid && parsedShrubs.value !== undefined) {
      req.landscape!.shrubs_quantity = parsedShrubs.value;
    }
  }
  if (form.groundPlantersRequired) {
    const parsedPlanters = parseStrictInteger(form.groundPlantersCount, 'Planters count');
    if (parsedPlanters.valid && parsedPlanters.value !== undefined) {
      req.landscape!.ground_planters_count = parsedPlanters.value;
    }
  }
  if (form.gardenSeatingRequired) {
    const parsedSeating = parseStrictInteger(form.gardenSeatingCount, 'Garden seating count');
    if (parsedSeating.valid && parsedSeating.value !== undefined) {
      req.landscape!.garden_seating_count = parsedSeating.value;
    }
  }
  if (form.gardenTableSetRequired) {
    const parsedTables = parseStrictInteger(form.gardenTableSetCount, 'Garden table set count');
    if (parsedTables.valid && parsedTables.value !== undefined) {
      req.landscape!.garden_table_set_count = parsedTables.value;
    }
  }

  // Dependent Boundary Wall
  if (form.boundaryWallRequired) {
    if (form.boundaryWallType) {
      req.landscape!.boundary_wall_type = form.boundaryWallType;
    }
    const parsedHeight = parseStrictFloat(form.boundaryWallHeightM, 'Boundary wall height');
    if (parsedHeight.valid && parsedHeight.value !== undefined) {
      req.landscape!.boundary_wall_height_m = parsedHeight.value;
    }
  }

  // Dependent Lighting: Style, Spacing, Fixture Count
  if (form.lightingRequired) {
    if (form.lightingStyle) {
      req.lighting!.style = form.lightingStyle;
    }
    const parsedSpacing = parseStrictFloat(form.lightingSpacingM, 'Lighting spacing');
    if (parsedSpacing.valid && parsedSpacing.value !== undefined) {
      req.lighting!.preferred_spacing_m = parsedSpacing.value;
    } else {
      req.lighting!.preferred_spacing_m = 8.0;
    }
    const parsedCount = parseStrictInteger(form.lightingFixtureCount, 'Lighting fixture count');
    if (parsedCount.valid && parsedCount.value !== undefined) {
      req.lighting!.desired_fixture_count = parsedCount.value;
    }
  }

  // Dependent Water Features: Garden Taps
  if (form.gardenTapsRequired) {
    const parsedTaps = parseStrictInteger(form.gardenTapsCount, 'Garden taps count');
    if (parsedTaps.valid && parsedTaps.value !== undefined) {
      req.water_features!.garden_taps_count = parsedTaps.value;
    }
  }

  // Location details
  if (form.selectedLocation) {
    const lat = typeof form.selectedLocation.latitude === 'number' ? form.selectedLocation.latitude : undefined;
    const lon = typeof form.selectedLocation.longitude === 'number' ? form.selectedLocation.longitude : undefined;
    if (lat !== undefined && lon !== undefined) {
      req.location = {
        latitude: lat,
        longitude: lon,
        timezone: form.selectedLocation.timezone || null,
        city: form.selectedLocation.city || form.selectedLocation.name || null,
      };
      req.latitude = lat;
      req.longitude = lon;
      req.timezone = form.selectedLocation.timezone || null;
    }
  }

  // Environmental & Customer Factors
  if (form.maintenancePreference) {
    req.maintenance_preference = form.maintenancePreference;
    req.low_maintenance_preference = form.maintenancePreference === 'low';
  }
  if (form.waterAvailability) {
    req.water_availability = form.waterAvailability;
  }

  if (form.climateZone && form.climateZone !== 'unknown') {
    req.climate_zone = form.climateZone;
  }
  if (form.siteExposure && form.siteExposure !== 'unknown') {
    req.site_exposure = form.siteExposure;
  }
  if (form.preferredPlantIds && form.preferredPlantIds.length > 0) {
    req.preferred_plant_ids = form.preferredPlantIds;
  }
  if (form.plantIdsToAvoid && form.plantIdsToAvoid.length > 0) {
    req.plant_ids_to_avoid = form.plantIdsToAvoid;
  }
  if (form.acceptedPlantAlternatives && form.acceptedPlantAlternatives.length > 0) {
    req.accepted_plant_alternatives = form.acceptedPlantAlternatives;
    if (!req.landscape) req.landscape = {};
    req.landscape.accepted_plant_alternatives = form.acceptedPlantAlternatives;
  }
  if (form.rejectedPlantAlternatives && form.rejectedPlantAlternatives.length > 0) {
    req.rejected_plant_alternatives = form.rejectedPlantAlternatives;
    if (!req.landscape) req.landscape = {};
    req.landscape.rejected_plant_alternatives = form.rejectedPlantAlternatives;
  }
  if (form.lockedFeatures && form.lockedFeatures.length > 0) {
    req.locked_features = form.lockedFeatures;
  }

  return req;
}

/**
 * Deserializes an ELIARequirements payload into the frontend EliaFormState,
 * normalizing legacy aliases and restoring complete user intent.
 */
export function deserializeRequirements(req: Partial<ELIARequirements>): Partial<EliaFormState> {
  const form: Partial<EliaFormState> = {};

  // Design Concept & legacy alias normalization
  if (req.design_style) {
    const style = String(req.design_style).trim().toLowerCase();
    if (style === 'minimalist' || style === 'minimalistic') {
      form.designStyle = 'minimalistic';
    } else if (style === 'greeny' || style === 'green' || style === 'lush') {
      form.designStyle = 'greeny';
    } else {
      form.designStyle = 'modern';
    }
  }

  // Group B: Access & Parking
  const acc = req.access || {};
  if (acc.parking_required !== undefined) form.parkingRequired = Boolean(acc.parking_required);
  if (acc.parking_type) form.parkingType = acc.parking_type;
  if (acc.garage_required !== undefined) form.garageRequired = Boolean(acc.garage_required);
  if (acc.garage_capacity !== undefined) form.garageCapacity = acc.garage_capacity;
  if (acc.vehicle_count !== undefined) form.vehicleCount = acc.vehicle_count;
  if (acc.turning_space_required !== undefined) form.turningSpaceRequired = Boolean(acc.turning_space_required);

  // Group C: Driveway, Walkways, Gate
  if (acc.driveway_required !== undefined) form.drivewayRequired = Boolean(acc.driveway_required);
  if (acc.driveway_style) form.drivewayStyle = acc.driveway_style;
  if (acc.driveway_surface) form.drivewaySurface = acc.driveway_surface;
  if (acc.walking_path_surface) form.walkingPathSurface = acc.walking_path_surface;
  if (acc.gate_required !== undefined) form.gateRequired = Boolean(acc.gate_required);
  if (acc.gate_type) form.gateType = acc.gate_type;
  if (acc.gate_width_m != null) form.gateWidthM = acc.gate_width_m;
  if (acc.gate_opening_mechanism) form.gateOpeningMechanism = acc.gate_opening_mechanism;
  if (acc.gate_style) form.gateStyle = acc.gate_style;

  // Group D & E: Landscape
  const lnd = req.landscape || {};
  if (lnd.garden_required !== undefined) form.gardenRequired = Boolean(lnd.garden_required);
  if (lnd.lawn_required !== undefined) form.lawnRequired = Boolean(lnd.lawn_required);
  if (lnd.garden_ground_finish) form.gardenGroundFinish = lnd.garden_ground_finish;
  if (lnd.greenery_density) form.greeneryDensity = lnd.greenery_density;
  if (lnd.trees_required !== undefined) form.treesRequired = Boolean(lnd.trees_required);
  if (lnd.tree_quantity != null) form.treeQuantity = lnd.tree_quantity;
  if (lnd.compact_trees_preference !== undefined) form.compactTreesPreference = Boolean(lnd.compact_trees_preference);
  if (lnd.shrubs_required !== undefined) form.shrubsRequired = Boolean(lnd.shrubs_required);
  if (lnd.shrubs_quantity != null) form.shrubsQuantity = lnd.shrubs_quantity;
  if (lnd.flower_beds_required !== undefined) form.flowerBedsRequired = Boolean(lnd.flower_beds_required);
  if (lnd.ground_planters_required !== undefined) form.groundPlantersRequired = Boolean(lnd.ground_planters_required);
  if (lnd.ground_planters_count != null) form.groundPlantersCount = lnd.ground_planters_count;
  if (lnd.shade_tree_preference !== undefined) form.shadeTreePreference = Boolean(lnd.shade_tree_preference);
  if (lnd.garden_seating_required !== undefined) form.gardenSeatingRequired = Boolean(lnd.garden_seating_required);
  if (lnd.garden_seating_count != null) form.gardenSeatingCount = lnd.garden_seating_count;
  if (lnd.garden_table_set_required !== undefined) form.gardenTableSetRequired = Boolean(lnd.garden_table_set_required);
  if (lnd.garden_table_set_count != null) form.gardenTableSetCount = lnd.garden_table_set_count;
  if (lnd.pedestrian_path_required !== undefined) form.pedestrianPathRequired = Boolean(lnd.pedestrian_path_required);
  if (lnd.garden_path_required !== undefined) form.gardenPathRequired = Boolean(lnd.garden_path_required);
  if (lnd.boundary_wall_required !== undefined) form.boundaryWallRequired = Boolean(lnd.boundary_wall_required);
  if (lnd.boundary_wall_type) form.boundaryWallType = lnd.boundary_wall_type;
  if (lnd.boundary_wall_height_m != null) form.boundaryWallHeightM = lnd.boundary_wall_height_m;
  if (lnd.preferred_open_space_ratio != null) form.openSpaceRatio = lnd.preferred_open_space_ratio;

  // Group F: Vertical Greenery
  const vg = req.vertical_greenery || {};
  if (vg.mode) form.verticalGreeneryMode = vg.mode;
  if (vg.wall_climbing_plants !== undefined) form.wallClimbingPlants = Boolean(vg.wall_climbing_plants);
  if (vg.wall_mounted_greenery !== undefined) form.wallMountedGreenery = Boolean(vg.wall_mounted_greenery);
  if (vg.hanging_trailing_greenery !== undefined) form.hangingTrailingGreenery = Boolean(vg.hanging_trailing_greenery);
  if (vg.accept_vertical_alternatives !== undefined) form.acceptVerticalAlternatives = Boolean(vg.accept_vertical_alternatives);

  // Group G: Balconies
  const balc = req.balconies || {};
  if (balc.planting_required !== undefined) form.balconyPlantingRequired = Boolean(balc.planting_required);
  if (balc.potted_plants !== undefined) form.balconyPottedPlants = Boolean(balc.potted_plants);
  if (balc.hanging_plants !== undefined) form.balconyHangingPlants = Boolean(balc.hanging_plants);
  if (balc.seating_required !== undefined) form.balconySeatingRequired = Boolean(balc.seating_required);
  if (balc.preferred_plant_ids) form.balconyPlantIds = balc.preferred_plant_ids;
  if (balc.target_balcony_ids) form.targetBalconyIds = balc.target_balcony_ids;

  // Group H: Rooftop / Terrace
  const terr = req.terrace || {};
  if (terr.planting_required !== undefined) form.rooftopPlantingRequired = Boolean(terr.planting_required);
  if (terr.planters_required !== undefined) form.rooftopPlantersRequired = Boolean(terr.planters_required);
  if (terr.seating_required !== undefined) form.rooftopSeatingRequired = Boolean(terr.seating_required);
  if (terr.tables_required !== undefined) form.rooftopTablesRequired = Boolean(terr.tables_required);
  if (terr.target_terrace_ids) form.targetTerraceIds = terr.target_terrace_ids;

  // Group I: Lighting
  const lgt = req.lighting || {};
  if (lgt.required !== undefined) form.lightingRequired = Boolean(lgt.required);
  if (lgt.style) form.lightingStyle = lgt.style;
  if (lgt.preferred_spacing_m != null) form.lightingSpacingM = lgt.preferred_spacing_m;
  if (lgt.desired_fixture_count != null) form.lightingFixtureCount = lgt.desired_fixture_count;
  if (lgt.garden_lighting !== undefined) form.gardenLighting = Boolean(lgt.garden_lighting);
  if (lgt.pathway_lighting !== undefined) form.pathwayLighting = Boolean(lgt.pathway_lighting);
  if (lgt.seating_lighting !== undefined) form.seatingLighting = Boolean(lgt.seating_lighting);
  if (lgt.wall_lighting !== undefined) form.wallLighting = Boolean(lgt.wall_lighting);

  // Group J: Water Features
  const wf = req.water_features || {};
  if (wf.well_required !== undefined) form.wellRequired = Boolean(wf.well_required);
  if (wf.garden_taps_required !== undefined) form.gardenTapsRequired = Boolean(wf.garden_taps_required);
  if (wf.garden_taps_count != null) form.gardenTapsCount = wf.garden_taps_count;
  if (wf.pond_required !== undefined) form.pondRequired = Boolean(wf.pond_required);
  if (wf.swimming_pool_required !== undefined) form.poolRequired = Boolean(wf.swimming_pool_required);
  if (wf.septic_tank_required !== undefined) form.septicTankRequired = Boolean(wf.septic_tank_required);

  // Group K: Solar
  const sol = req.solar || {};
  if (sol.panels_required !== undefined) form.solarRequired = Boolean(sol.panels_required);
  if (sol.preferred_roof_surface) form.preferredRoofSurface = sol.preferred_roof_surface;
  if (sol.placement_priority) form.placementPriority = sol.placement_priority;
  if (sol.include_live_solar !== undefined) form.includeLiveSolar = Boolean(sol.include_live_solar);
  else if (req.include_live_solar !== undefined) form.includeLiveSolar = Boolean(req.include_live_solar);

  // Environmental & Botanical Preferences
  if (req.maintenance_preference) form.maintenancePreference = req.maintenance_preference;
  if (req.water_availability) form.waterAvailability = req.water_availability;
  if (req.climate_zone) form.climateZone = req.climate_zone as any;
  if (req.site_exposure) form.siteExposure = req.site_exposure as any;
  if (req.preferred_plant_ids) form.preferredPlantIds = req.preferred_plant_ids;
  if (req.plant_ids_to_avoid) form.plantIdsToAvoid = req.plant_ids_to_avoid;
  const acceptedAlts = req.accepted_plant_alternatives || (req.landscape && req.landscape.accepted_plant_alternatives);
  if (acceptedAlts) form.acceptedPlantAlternatives = acceptedAlts;
  const rejectedAlts = req.rejected_plant_alternatives || (req.landscape && req.landscape.rejected_plant_alternatives);
  if (rejectedAlts) form.rejectedPlantAlternatives = rejectedAlts;
  if (req.locked_features) form.lockedFeatures = req.locked_features;

  return form;
}

/**
 * Computes a deterministic identity fingerprint of the form state
 * including location and generation mode.
 */
export function computeRequirementsFingerprint(form: Partial<EliaFormState>): string {
  const serialized = serializeRequirements(form);
  const composite = {
    requirements: serialized,
    generationMode: form.generationMode || 'baseline',
    hasLocation: Boolean(form.selectedLocation),
    locationCoords: form.selectedLocation ? `${form.selectedLocation.latitude},${form.selectedLocation.longitude}` : null,
  };
  return JSON.stringify(composite);
}
