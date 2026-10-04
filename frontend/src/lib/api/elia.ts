import { apiClient } from './client';

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
  searchLocations: async (name: string): Promise<{ results: SriLankaLocation[]; attribution: string }> => {
    const response = await apiClient.get('/elia-engine/locations/search', { params: { name } });
    return response.data;
  },
  currentSolar: async (projectId: string, location: SriLankaLocation): Promise<LiveSolarConditions> => {
    const response = await apiClient.get(`/projects/${projectId}/elia-engine/solar/current`, {
      params: { latitude: location.latitude, longitude: location.longitude, timezone: location.timezone },
    });
    return response.data;
  },
  run: async (projectId: string, payload?: unknown): Promise<any> => {
    const response = await apiClient.post(`/projects/${projectId}/elia-engine/run`, payload ?? {});
    return response.data;
  },
};
