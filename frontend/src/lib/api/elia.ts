import { apiClient } from './client';
import type {
  ELIARequestPayload,
  ELIAResponse,
  ELIAPreviewResponse,
  ELIAValidationResponse,
  ELIAContextResponse,
  ELIAResultResponse,
  CandidateValidationRequest,
  CandidateValidationResponse,
  CandidateSaveRequest,
  CandidateSaveResponse,
  ProjectFeasibilityResponse,
} from '@/types/elia';

export interface SriLankaLocation {
  id: number;
  name: string;
  display_name: string;
  admin1?: string;
  admin2?: string;
  country: string;
  country_code: string;
  latitude: number;
  longitude: number;
  timezone?: string | null;
  attribution: string;
}

export interface LiveSolarConditions {
  status: 'available';
  provider: string;
  data_type: string;
  timestamp: string;
  location: { requested_latitude: number; requested_longitude: number; timezone: string };
  solar_position: { azimuth_degrees: number; elevation_degrees: number; is_day: boolean };
  irradiance_w_m2: Record<string, number | null>;
  cloud_cover_percent: number | null;
  air_temperature_c: number | null;
  observation_note: string;
}

export const eliaApi = {
  searchLocations: async (
    name: string,
    options?: { signal?: AbortSignal }
  ): Promise<{ results: SriLankaLocation[]; attribution: string }> => {
    const response = await apiClient.get('/elia-engine/locations/search', {
      params: { name },
      signal: options?.signal,
    });
    return response.data;
  },

  currentSolar: async (
    projectId: string,
    location: { latitude: number; longitude: number; timezone?: string | null },
    options?: { signal?: AbortSignal }
  ): Promise<LiveSolarConditions> => {
    const response = await apiClient.get(`/projects/${projectId}/elia-engine/solar/current`, {
      params: { latitude: location.latitude, longitude: location.longitude, timezone: location.timezone },
      signal: options?.signal,
    });
    return response.data;
  },

  getContext: async (
    projectId: string,
    options?: { signal?: AbortSignal }
  ): Promise<ELIAContextResponse> => {
    const response = await apiClient.get(`/projects/${projectId}/elia-engine/context`, {
      signal: options?.signal,
    });
    return response.data;
  },

  validateInput: async (
    projectId: string,
    payload: ELIARequestPayload,
    options?: { signal?: AbortSignal }
  ): Promise<ELIAValidationResponse> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/validate-input`, payload, {
      signal: options?.signal,
    });
    return response.data;
  },

  preview: async (
    payload: ELIARequestPayload,
    options?: { signal?: AbortSignal }
  ): Promise<ELIAPreviewResponse> => {
    const response = await apiClient.post('/elia-engine/preview', payload, {
      signal: options?.signal,
    });
    return response.data;
  },

  run: async (
    projectId: string,
    payload: ELIARequestPayload,
    options?: { signal?: AbortSignal }
  ): Promise<ELIAResponse> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/run`, payload, {
      signal: options?.signal,
    });
    return response.data;
  },

  getResult: async (
    projectId: string,
    options?: { signal?: AbortSignal }
  ): Promise<ELIAResultResponse> => {
    const response = await apiClient.get(`/projects/${projectId}/elia-engine/result`, {
      signal: options?.signal,
    });
    return response.data;
  },

  validateCandidate: async (
    projectId: string,
    payload: CandidateValidationRequest,
    options?: { signal?: AbortSignal }
  ): Promise<CandidateValidationResponse> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/validate-candidate`, payload, {
      signal: options?.signal,
    });
    return response.data;
  },

  saveCandidate: async (
    projectId: string,
    payload: CandidateSaveRequest,
    options?: { signal?: AbortSignal }
  ): Promise<CandidateSaveResponse> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/save-candidate`, payload, {
      signal: options?.signal,
    });
    return response.data;
  },

  getVegetationCatalog: async (
    options?: { signal?: AbortSignal }
  ): Promise<Record<string, unknown>> => {
    const response = await apiClient.get('/elia-engine/vegetation-catalog', {
      signal: options?.signal,
    });
    return response.data;
  },

  assessFeasibility: async (
    projectId: string,
    payload: ELIARequestPayload,
    options?: { signal?: AbortSignal }
  ): Promise<ProjectFeasibilityResponse> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/feasibility`, payload, {
      signal: options?.signal,
    });
    return response.data;
  },
};

