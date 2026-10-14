export type EliaErrorType =
  | 'STALE_REVISION'
  | 'MODEL_UNAVAILABLE'
  | 'SERVICE_UNAVAILABLE'
  | 'AUTH_REQUIRED'
  | 'VALIDATION_ERROR'
  | 'NOT_FOUND'
  | 'NETWORK_ERROR'
  | 'SERVER_ERROR'
  | 'GENERIC_ERROR';

export interface EliaParsedError {
  type: EliaErrorType;
  code: string;
  message: string;
  status?: number;
  currentRevision?: number;
  expectedRevision?: number;
  validationViolations?: string[];
  is404?: boolean;
  isStaleRevision?: boolean;
}

/**
 * Robust, production-grade error parser for ELIA API operations.
 * Accurately parses:
 *  - 409 Stale Source Revision conflicts with current_revision.
 *  - 503 ELIA_MODEL_UNAVAILABLE vs generic 503 Service Unavailable (does not mislabel generic 503s).
 *  - 401 / 403 Authentication / Authorization failures.
 *  - 422 Validation error arrays from FastAPI and structured validation responses.
 *  - 404 Not Found (distinguishing expected missing run from system error).
 *  - 500 Server/Database processing failures.
 *  - Network errors, timeouts, and string error details.
 */
export function parseEliaError(err: any, fallbackMessage = 'An unexpected error occurred.'): EliaParsedError {
  if (!err) {
    return {
      type: 'GENERIC_ERROR',
      code: 'UNKNOWN',
      message: fallbackMessage,
    };
  }

  // Network or connection errors
  if (err.isAxiosError && !err.response) {
    return {
      type: 'NETWORK_ERROR',
      code: 'NETWORK_ERROR',
      message: err.message || 'Network connection failed. Please check backend server availability.',
    };
  }

  const status = err.response?.status ?? (typeof err.status === 'number' ? err.status : undefined);
  const detail = err.response?.data?.detail ?? err.detail ?? err.data?.detail;

  // 1. Revision Conflict (HTTP 409)
  if (status === 409) {
    const currentRev = typeof detail === 'object' && detail ? detail.current_revision : undefined;
    const expectedRev = typeof detail === 'object' && detail ? detail.expected_revision : undefined;
    const revInfo = currentRev !== undefined ? ` (current revision is ${currentRev})` : '';
    const msg =
      typeof detail === 'object' && detail?.message
        ? detail.message
        : `The project was modified concurrently${revInfo}. Your requirements form has been preserved. Please refresh context and regenerate.`;

    return {
      type: 'STALE_REVISION',
      code: (typeof detail === 'object' && detail?.code) || 'ELIA_STALE_SOURCE_REVISION',
      message: msg,
      status: 409,
      currentRevision: currentRev,
      expectedRevision: expectedRev,
      isStaleRevision: true,
    };
  }

  // 2. HTTP 503: Model Unavailable vs Generic Service Unavailable
  if (status === 503) {
    const code = typeof detail === 'object' && detail ? detail.code : '';
    const isModelSpecific = code === 'ELIA_MODEL_UNAVAILABLE' || (typeof detail === 'string' && detail.includes('ELIA_MODEL_UNAVAILABLE'));

    if (isModelSpecific) {
      const msg =
        (typeof detail === 'object' && detail?.message) ||
        (typeof detail === 'string' ? detail : 'The trained exterior AI model is not registered on this backend. Use the Baseline Heuristic Planner.');
      return {
        type: 'MODEL_UNAVAILABLE',
        code: 'ELIA_MODEL_UNAVAILABLE',
        message: msg,
        status: 503,
      };
    }

    return {
      type: 'SERVICE_UNAVAILABLE',
      code: (typeof detail === 'object' && detail?.code) || 'SERVICE_UNAVAILABLE',
      message: (typeof detail === 'object' && detail?.message) || (typeof detail === 'string' ? detail : 'Upstream service temporarily unavailable.'),
      status: 503,
    };
  }

  // 3. HTTP 401 / 403: Authentication / Authorization
  if (status === 401 || status === 403) {
    return {
      type: 'AUTH_REQUIRED',
      code: status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN',
      message:
        (typeof detail === 'object' && detail?.message) ||
        (typeof detail === 'string' ? detail : 'Authentication required: Admin credentials or valid session needed for ELIA engine.'),
      status,
    };
  }

  // 4. HTTP 404: Not Found
  if (status === 404) {
    const msg =
      typeof detail === 'string'
        ? detail
        : (typeof detail === 'object' && detail?.message) || 'Resource not found.';
    return {
      type: 'NOT_FOUND',
      code: (typeof detail === 'object' && detail?.code) || 'NOT_FOUND',
      message: msg,
      status: 404,
      is404: true,
    };
  }

  // 5. HTTP 422: Validation Errors
  if (status === 422) {
    if (Array.isArray(detail)) {
      // FastAPI ValidationError array of { loc, msg, type }
      const violations = detail.map((v) => {
        const field = Array.isArray(v.loc) ? v.loc.join('.') : '';
        return field ? `${field}: ${v.msg}` : v.msg;
      });
      return {
        type: 'VALIDATION_ERROR',
        code: 'VALIDATION_ERROR',
        message: `Validation failed: ${violations.join('; ')}`,
        status: 422,
        validationViolations: violations,
      };
    }
    if (typeof detail === 'object' && detail) {
      return {
        type: 'VALIDATION_ERROR',
        code: detail.code || 'VALIDATION_ERROR',
        message: detail.message || 'Validation failed for supplied inputs.',
        status: 422,
      };
    }
    return {
      type: 'VALIDATION_ERROR',
      code: 'VALIDATION_ERROR',
      message: typeof detail === 'string' ? detail : 'Invalid request inputs.',
      status: 422,
    };
  }

  // 6. HTTP 500: Server / Backend Error
  if (status === 500) {
    const code = (typeof detail === 'object' && detail?.code) || 'ELIA_PROCESSING_FAILED';
    const msg =
      (typeof detail === 'object' && detail?.message) ||
      (typeof detail === 'string' ? detail : fallbackMessage);
    return {
      type: 'SERVER_ERROR',
      code,
      message: `${code}: ${msg}`,
      status: 500,
    };
  }

  // Generic / other errors
  if (typeof detail === 'object' && detail) {
    return {
      type: 'GENERIC_ERROR',
      code: detail.code || 'ERROR',
      message: detail.message || fallbackMessage,
      status,
    };
  }

  if (typeof detail === 'string' && detail.trim()) {
    return {
      type: 'GENERIC_ERROR',
      code: 'ERROR',
      message: detail,
      status,
    };
  }

  return {
    type: 'GENERIC_ERROR',
    code: 'ERROR',
    message: err.message || fallbackMessage,
    status,
  };
}
