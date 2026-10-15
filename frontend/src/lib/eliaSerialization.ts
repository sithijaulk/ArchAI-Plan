import type { ELIARequirements } from '@/types/elia';

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

  // Access & Parking
  garageRequired: boolean;
  garageCapacity: number | string;
  vehicleCount: number | string;
  drivewayRequired: boolean;
  drivewayStyle: string;
  turningSpaceRequired: boolean;
  gateType: string;
  gateWidthM: number | string;

  // Landscape & Garden
  gardenRequired: boolean;
  lawnRequired: boolean;
  gardenSeatingRequired: boolean;
  gardenTableSetRequired: boolean;
  pedestrianPathRequired: boolean;
  gardenPathRequired: boolean;
  boundaryWallRequired: boolean;
  boundaryWallType: string;
  boundaryWallHeightM: number | string;

  // Lighting & Vertical Greenery
  lightingRequired: boolean;
  lightingStyle: string;
  lightingSpacingM?: number | string;
  verticalGreeneryMode: 'automatic' | 'preferred' | 'disabled';

  // Location & Solar
  selectedLocation: EliaSelectedLocation | null;
  includeLiveSolar: boolean;
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

  if (form.garageRequired) {
    const maxCapacity = form.generationMode === 'baseline' ? 3 : 10;
    const capRes = parseStrictInteger(form.garageCapacity, 'Garage capacity', {
      required: true,
      min: 1,
      max: maxCapacity,
    });
    if (!capRes.valid) {
      errors.garageCapacity = capRes.error!;
    }

    const vehRes = parseStrictInteger(form.vehicleCount, 'Vehicle count', {
      required: true,
      min: 1,
    });
    if (!vehRes.valid) {
      errors.vehicleCount = vehRes.error!;
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
  const req: ELIARequirements = {
    units: 'm',
    design_style: form.designStyle || 'contemporary',
    greenery_level: form.greeneryDensity || 'medium',
    landscape_priority: 'balanced',
    vertical_greenery_enabled: form.verticalGreeneryMode !== 'disabled',
    include_live_solar: Boolean(form.includeLiveSolar),
    access: {
      gate_type: form.gateType || 'unspecified',
      garage_required: Boolean(form.garageRequired),
      driveway_required: Boolean(form.drivewayRequired),
      turning_space_required: Boolean(form.turningSpaceRequired),
    },
    landscape: {
      garden_required: Boolean(form.gardenRequired),
      lawn_required: Boolean(form.lawnRequired),
      greenery_density: form.greeneryDensity || 'medium',
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
    },
    lighting: {
      required: Boolean(form.lightingRequired),
    },
  };

  // Gate width: only attach if strictly valid
  const parsedWidth = parseStrictFloat(form.gateWidthM, 'Gate width');
  if (parsedWidth.valid && parsedWidth.value !== undefined) {
    req.access!.gate_width_m = parsedWidth.value;
  }

  // Dependent Access: Garage
  if (form.garageRequired) {
    const parsedCap = parseStrictInteger(form.garageCapacity, 'Garage capacity');
    if (parsedCap.valid && parsedCap.value !== undefined) {
      req.access!.garage_capacity = parsedCap.value;
    }
    const parsedVeh = parseStrictInteger(form.vehicleCount, 'Vehicle count');
    if (parsedVeh.valid && parsedVeh.value !== undefined) {
      req.access!.vehicle_count = parsedVeh.value;
    }
  }

  // Dependent Access: Driveway
  if (form.drivewayRequired) {
    if (form.drivewayStyle) {
      req.access!.driveway_style = form.drivewayStyle;
    }
  }

  // Open space ratio: preserve 0 if provided!
  const parsedRatio = parseStrictFloat(form.openSpaceRatio, 'Open space ratio');
  if (parsedRatio.valid && parsedRatio.value !== undefined) {
    req.landscape!.preferred_open_space_ratio = parsedRatio.value;
  }

  // Dependent Landscape: Boundary Wall
  if (form.boundaryWallRequired) {
    if (form.boundaryWallType) {
      req.landscape!.boundary_wall_type = form.boundaryWallType;
    }
    const parsedHeight = parseStrictFloat(form.boundaryWallHeightM, 'Boundary wall height');
    if (parsedHeight.valid && parsedHeight.value !== undefined) {
      req.landscape!.boundary_wall_height_m = parsedHeight.value;
    }
  }

  // Dependent Lighting: Style & Spacing
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

  return req;
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
