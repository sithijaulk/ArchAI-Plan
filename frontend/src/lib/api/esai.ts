import { apiClient } from './client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface FloorRoom {
  room_id: string;
  name: string;
  room_type: string;
  area_sqm: number;
  preference_saved: boolean;
  preference_revision: number | null;
  is_orphaned: boolean;
}

export interface FloorSummary {
  floor_id: string;
  floor_name: string;
  level_index: number;
  rooms: FloorRoom[];
}

export interface InteriorContext {
  project_id: string;
  project_name: string;
  floors: FloorSummary[];
  total_floors: number;
  total_rooms: number;
  configured_rooms: number;
  geometry_staleness: {
    is_stale: boolean;
    status: string;
    geometry_fingerprint: string;
    stored_fingerprint: string | null;
    message: string;
  };
}

export interface RoomPreferences {
  id?: string;
  project_id?: string;
  floor_id: string;
  room_id: string;
  room_type: string;
  preferences: Record<string, unknown>;
  preference_revision?: number;
  is_orphaned?: boolean;
  geometry_fingerprint?: string;
  created_at?: string;
  updated_at?: string;
}

export interface EffectivePreferences {
  room_id: string;
  floor_id: string;
  room_type?: string;
  effective_preferences: Record<string, unknown>;
  effective?: Record<string, unknown>;
  sources: Record<string, string> | {
    building: string[];
    floor: string[];
    room: string[];
  };
  overridden_keys?: string[];
  inherited_keys?: string[];
  specific_assets?: Array<Record<string, unknown>>;
  custom_constraints?: Array<Record<string, unknown>>;
  is_orphaned: boolean;
  preference_revision: number | null;
}

export interface PreferenceSchema {
  room_type: string;
  schema_key: string;
  specific_section: string | null;
  fields: Record<string, unknown>;
  common_fields: Record<string, unknown>;
}

// ─── API Client ───────────────────────────────────────────────────────────────

const base = (projectId: string) =>
  `/projects/${projectId}/esai-engine`;

export const esaiApi = {
  // Preserved Phase 1 run stub (501 Not Implemented)
  run: async (projectId: string, payload?: unknown): Promise<unknown> => {
    const response = await apiClient.post(`${base(projectId)}/run`, payload ?? {});
    return response.data;
  },

  // ── Context ────────────────────────────────────────────────────────────────

  getContext: async (projectId: string) => {
    const r = await apiClient.get(`${base(projectId)}/context`);
    return r.data;
  },

  /** Returns floors + rooms + per-room preference completion status */
  getInteriorContext: async (projectId: string): Promise<InteriorContext> => {
    const r = await apiClient.get(`${base(projectId)}/interior-context`);
    return r.data;
  },

  getFloors: async (projectId: string) => {
    const r = await apiClient.get(`${base(projectId)}/floors`);
    return r.data;
  },

  getRooms: async (projectId: string, floorId?: string) => {
    const params = floorId ? { floor_id: floorId } : {};
    const r = await apiClient.get(`${base(projectId)}/rooms`, { params });
    return r.data;
  },

  getRoom: async (projectId: string, roomId: string) => {
    const r = await apiClient.get(`${base(projectId)}/rooms/${roomId}`);
    return r.data;
  },

  checkStaleness: async (projectId: string) => {
    const r = await apiClient.get(`${base(projectId)}/staleness`);
    return r.data;
  },

  // ── Building Preferences ───────────────────────────────────────────────────

  getBuildingPreferences: async (projectId: string) => {
    const r = await apiClient.get(`${base(projectId)}/preferences/building`);
    return r.data;
  },

  saveBuildingPreferences: async (
    projectId: string,
    prefs: Record<string, unknown>,
    expectedRevision?: number
  ) => {
    const params = expectedRevision !== undefined ? { expected_revision: expectedRevision } : {};
    const r = await apiClient.put(`${base(projectId)}/preferences/building`, prefs, { params });
    return r.data;
  },

  patchBuildingPreferences: async (
    projectId: string,
    patch: Record<string, unknown>,
    expectedRevision?: number
  ) => {
    const params = expectedRevision !== undefined ? { expected_revision: expectedRevision } : {};
    const r = await apiClient.patch(`${base(projectId)}/preferences/building`, patch, { params });
    return r.data;
  },

  // ── Floor Preferences ──────────────────────────────────────────────────────

  getFloorPreferences: async (projectId: string, floorId: string) => {
    const r = await apiClient.get(`${base(projectId)}/preferences/floors/${floorId}`);
    return r.data;
  },

  saveFloorPreferences: async (
    projectId: string,
    floorId: string,
    prefs: Record<string, unknown>,
    expectedRevision?: number
  ) => {
    const params = expectedRevision !== undefined ? { expected_revision: expectedRevision } : {};
    const r = await apiClient.put(`${base(projectId)}/preferences/floors/${floorId}`, prefs, { params });
    return r.data;
  },

  patchFloorPreferences: async (
    projectId: string,
    floorId: string,
    patch: Record<string, unknown>,
    expectedRevision?: number
  ) => {
    const params = expectedRevision !== undefined ? { expected_revision: expectedRevision } : {};
    const r = await apiClient.patch(`${base(projectId)}/preferences/floors/${floorId}`, patch, { params });
    return r.data;
  },

  resetFloorPreferences: async (projectId: string, floorId: string) => {
    await apiClient.delete(`${base(projectId)}/preferences/floors/${floorId}`);
  },

  // ── Room Preferences ───────────────────────────────────────────────────────

  listRoomPreferences: async (projectId: string, floorId?: string) => {
    const params = floorId ? { floor_id: floorId } : {};
    const r = await apiClient.get(`${base(projectId)}/preferences/rooms`, { params });
    return r.data;
  },

  getRoomPreferences: async (projectId: string, roomId: string): Promise<RoomPreferences | null> => {
    const r = await apiClient.get(`${base(projectId)}/preferences/rooms/${roomId}`);
    if (r.data?.preferences === null) return null;
    return r.data;
  },

  saveRoomPreferences: async (
    projectId: string,
    roomId: string,
    prefs: Record<string, unknown>,
    expectedRevision?: number
  ): Promise<RoomPreferences> => {
    const params = expectedRevision !== undefined ? { expected_revision: expectedRevision } : {};
    const r = await apiClient.put(`${base(projectId)}/preferences/rooms/${roomId}`, prefs, { params });
    return r.data;
  },

  patchRoomPreferences: async (
    projectId: string,
    roomId: string,
    patch: Record<string, unknown>,
    expectedRevision?: number
  ): Promise<RoomPreferences> => {
    const params = expectedRevision !== undefined ? { expected_revision: expectedRevision } : {};
    const r = await apiClient.patch(`${base(projectId)}/preferences/rooms/${roomId}`, patch, { params });
    return r.data;
  },

  resetRoomPreferences: async (projectId: string, roomId: string): Promise<void> => {
    await apiClient.delete(`${base(projectId)}/preferences/rooms/${roomId}`);
  },

  getEffectivePreferences: async (
    projectId: string,
    roomId: string,
    floorId: string
  ): Promise<EffectivePreferences> => {
    const r = await apiClient.get(
      `${base(projectId)}/preferences/rooms/${roomId}/effective`,
      { params: { floor_id: floorId } }
    );
    return r.data;
  },

  // ── Schema & Orphan Detection ─────────────────────────────────────────────

  getPreferenceSchema: async (projectId: string, roomType: string): Promise<PreferenceSchema> => {
    const r = await apiClient.get(`${base(projectId)}/preferences/schema/${roomType}`);
    return r.data;
  },

  detectOrphans: async (projectId: string) => {
    const r = await apiClient.post(`${base(projectId)}/preferences/detect-orphans`);
    return r.data;
  },

  validateInput: async (projectId: string) => {
    const r = await apiClient.post(`${base(projectId)}/validate-input`);
    return r.data;
  },

  // ── Phase 3: Catalog & Knowledge Base ─────────────────────────────────────

  getCatalogCategories: async (): Promise<string[]> => {
    const r = await apiClient.get('/esai/catalog/categories');
    return r.data.categories;
  },

  getCatalogItems: async (params?: {
    category?: string;
    room_type?: string;
    subtype?: string;
    style?: string;
  }): Promise<any[]> => {
    const r = await apiClient.get('/esai/catalog/items', { params });
    return r.data.items;
  },

  getFinishes: async (params?: { category?: string; style?: string }): Promise<any[]> => {
    const r = await apiClient.get('/esai/catalog/finishes', { params });
    return r.data.finishes;
  },

  getStyles: async (): Promise<Record<string, any>> => {
    const r = await apiClient.get('/esai/knowledge/styles');
    return r.data.styles;
  },

  getErgonomicRules: async (params?: {
    category?: string;
    enforceable_only?: boolean;
    mandatory_only?: boolean;
  }): Promise<any[]> => {
    const r = await apiClient.get('/esai/knowledge/rules', { params });
    return r.data.rules;
  },

  getRoomProfiles: async (): Promise<any[]> => {
    const r = await apiClient.get('/esai/knowledge/room-profiles');
    return r.data.profiles;
  },

  getFunctionalRelations: async (params?: {
    primary_category?: string;
    related_category?: string;
  }): Promise<any[]> => {
    const r = await apiClient.get('/esai/knowledge/functional-relations', { params });
    return r.data.relations;
  },

  validateCatalogSelections: async (payload: {
    items: Array<Record<string, any>>;
    room_type?: string;
  }): Promise<any> => {
    const r = await apiClient.post('/esai/catalog/validate-selections', payload);
    return r.data;
  },

  resolveRoomDesignInput: async (
    projectId: string,
    roomId: string,
    floorId?: string
  ): Promise<any> => {
    const params = floorId ? { floor_id: floorId } : {};
    const r = await apiClient.post(
      `${base(projectId)}/preferences/rooms/${roomId}/resolve-design-input`,
      {},
      { params }
    );
    return r.data.resolved;
  },

  // ── Phase 5 & 6 Persistence, Regeneration & 3D Scene Visualization ────────

  runOptimization: async (
    projectId: string,
    payload: {
      scope?: string;
      room_id?: string;
      floor_id?: string;
      auto_save?: boolean;
      generations?: number;
      population_size?: number;
      seed?: number;
      alternatives_count?: number;
    }
  ): Promise<any> => {
    const r = await apiClient.post(`${base(projectId)}/run`, payload);
    return r.data;
  },

  getSavedDesigns: async (projectId: string): Promise<any> => {
    const r = await apiClient.get(`${base(projectId)}/designs`);
    return r.data;
  },

  getFloorDesigns: async (projectId: string, floorId: string): Promise<any> => {
    const r = await apiClient.get(`${base(projectId)}/designs/floors/${floorId}`);
    return r.data;
  },

  getRoomDesign: async (projectId: string, roomId: string): Promise<any> => {
    const r = await apiClient.get(`${base(projectId)}/designs/rooms/${roomId}`);
    return r.data;
  },

  getRoomAlternatives: async (projectId: string, roomId: string): Promise<any> => {
    const r = await apiClient.get(`${base(projectId)}/designs/rooms/${roomId}/alternatives`);
    return r.data;
  },

  selectAlternative: async (
    projectId: string,
    roomId: string,
    alternativeId: string
  ): Promise<any> => {
    const r = await apiClient.post(
      `${base(projectId)}/designs/rooms/${roomId}/select-alternative`,
      { alternative_id: alternativeId }
    );
    return r.data;
  },

  saveDesign: async (
    projectId: string,
    payload: {
      building_design?: any;
      room_design?: any;
      scope?: string;
      target_room_id?: string;
      target_floor_id?: string;
      expected_design_revision?: number;
    }
  ): Promise<any> => {
    const r = await apiClient.post(`${base(projectId)}/designs/save`, payload);
    return r.data;
  },

  regenerateScope: async (
    projectId: string,
    payload: {
      scope: string;
      room_id?: string;
      floor_id?: string;
      auto_save?: boolean;
      generations?: number;
      population_size?: number;
      seed?: number;
    }
  ): Promise<any> => {
    const r = await apiClient.post(`${base(projectId)}/regenerate`, payload);
    return r.data;
  },

  getSceneData: async (
    projectId: string,
    floorId?: string,
    roomId?: string
  ): Promise<any> => {
    const params: Record<string, string> = {};
    if (floorId) params.floor_id = floorId;
    if (roomId) params.room_id = roomId;
    const r = await apiClient.get(`${base(projectId)}/scene`, { params });
    return r.data;
  },

  getDesignStaleness: async (projectId: string): Promise<any> => {
    const r = await apiClient.get(`${base(projectId)}/designs/staleness`);
    return r.data;
  },

  // ── Phase 7: Interactive Customization, Locking & Selective Regeneration ─

  validateRoomEdit: async (
    projectId: string,
    roomId: string,
    payload: any
  ): Promise<any> => {
    const r = await apiClient.post(
      `${base(projectId)}/designs/rooms/${roomId}/validate-edit`,
      payload
    );
    return r.data;
  },

  saveRoomEdit: async (
    projectId: string,
    roomId: string,
    payload: any
  ): Promise<any> => {
    const r = await apiClient.patch(
      `${base(projectId)}/designs/rooms/${roomId}`,
      payload
    );
    return r.data;
  },

  lockRoomAsset: async (
    projectId: string,
    roomId: string,
    payload: { instance_id: string; is_locked?: boolean; lock_type?: string; expected_design_revision?: number }
  ): Promise<any> => {
    const r = await apiClient.post(
      `${base(projectId)}/designs/rooms/${roomId}/lock`,
      payload
    );
    return r.data;
  },

  unlockRoomAsset: async (
    projectId: string,
    roomId: string,
    payload: { instance_id: string; is_locked?: boolean; lock_type?: string; expected_design_revision?: number }
  ): Promise<any> => {
    const r = await apiClient.post(
      `${base(projectId)}/designs/rooms/${roomId}/unlock`,
      payload
    );
    return r.data;
  },

  regenerateUnlocked: async (
    projectId: string,
    roomId: string,
    payload?: { expected_design_revision?: number; seed?: number; population_size?: number; generations?: number; auto_save?: boolean }
  ): Promise<any> => {
    const r = await apiClient.post(
      `${base(projectId)}/designs/rooms/${roomId}/regenerate-unlocked`,
      payload || {}
    );
    return r.data;
  },
};

