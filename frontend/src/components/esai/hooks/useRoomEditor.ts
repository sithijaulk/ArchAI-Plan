'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  PersistedRoomDesignDTO,
  PlacedAssetPersistedDTO,
  RoomEditValidateResponse,
  ValidationDiagnosticDTO,
} from '@/types/esai';
import { esaiApi } from '@/lib/api/esai';

export interface UseRoomEditorProps {
  projectId: string;
  roomId: string | null;
  floorId: string | null;
  initialDesign: PersistedRoomDesignDTO | null;
  onDesignUpdated?: (updatedDesign: PersistedRoomDesignDTO) => void;
}

export function useRoomEditor({
  projectId,
  roomId,
  floorId,
  initialDesign,
  onDesignUpdated,
}: UseRoomEditorProps) {
  const [draftDesign, setDraftDesign] = useState<PersistedRoomDesignDTO | null>(null);
  const [history, setHistory] = useState<PersistedRoomDesignDTO[]>([]);
  const [future, setFuture] = useState<PersistedRoomDesignDTO[]>([]);
  const [isDirty, setIsDirty] = useState<boolean>(false);

  const [validationResult, setValidationResult] = useState<RoomEditValidateResponse | null>(null);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Sync draft whenever initialDesign or roomId changes (and user hasn't dirtied this room)
  useEffect(() => {
    if (initialDesign) {
      setDraftDesign(JSON.parse(JSON.stringify(initialDesign)));
      setHistory([]);
      setFuture([]);
      setIsDirty(false);
      setValidationResult(null);
      setErrorMessage(null);
    } else {
      setDraftDesign(null);
      setHistory([]);
      setFuture([]);
      setIsDirty(false);
    }
  }, [initialDesign, roomId]);

  // Helper to commit state transition with history
  const commitEdit = useCallback(
    (newDesign: PersistedRoomDesignDTO) => {
      if (!draftDesign) return;
      setHistory((prev) => [...prev.slice(-29), JSON.parse(JSON.stringify(draftDesign))]);
      setFuture([]);
      setDraftDesign(newDesign);
      setIsDirty(true);
    },
    [draftDesign]
  );

  // Live validation debounced
  const validationTimer = useRef<NodeJS.Timeout | null>(null);

  const triggerValidation = useCallback(
    (designToValidate: PersistedRoomDesignDTO) => {
      if (!projectId || !roomId) return;
      if (validationTimer.current) clearTimeout(validationTimer.current);

      validationTimer.current = setTimeout(async () => {
        setIsValidating(true);
        try {
          const payload = {
            room_id: roomId,
            floor_id: floorId || undefined,
            furniture: designToValidate.furniture || [],
            cabinetry: designToValidate.cabinetry || [],
            appliances: designToValidate.appliances || [],
            sanitary_fixtures: designToValidate.sanitary_fixtures || [],
            lighting: designToValidate.lighting || [],
            electrical_points: designToValidate.electrical_points || [],
            plumbing_requirements: designToValidate.plumbing_requirements || [],
            wall_finish: designToValidate.wall_finish,
            floor_finish: designToValidate.floor_finish,
            ceiling_finish: designToValidate.ceiling_finish,
          };
          const res: RoomEditValidateResponse = await esaiApi.validateRoomEdit(
            projectId,
            roomId,
            payload
          );
          setValidationResult(res);
        } catch (err: any) {
          console.error('Validation error:', err);
        } finally {
          setIsValidating(false);
        }
      }, 350);
    },
    [projectId, roomId, floorId]
  );

  // Helper to update an asset in the current draft across all asset arrays
  const updateAssetInDraft = useCallback(
    (
      instanceId: string,
      updater: (asset: PlacedAssetPersistedDTO) => PlacedAssetPersistedDTO | null
    ) => {
      if (!draftDesign) return;
      const copy: PersistedRoomDesignDTO = JSON.parse(JSON.stringify(draftDesign));

      const categories: (keyof PersistedRoomDesignDTO)[] = [
        'furniture',
        'cabinetry',
        'appliances',
        'sanitary_fixtures',
        'decorations',
        'placed_assets',
      ];

      let found = false;
      for (const cat of categories) {
        const arr = (copy[cat] as PlacedAssetPersistedDTO[]) || [];
        const idx = arr.findIndex((a) => a.instance_id === instanceId);
        if (idx !== -1) {
          const updated = updater(arr[idx]);
          if (updated === null) {
            arr.splice(idx, 1);
          } else {
            arr[idx] = updated;
          }
          (copy as any)[cat] = arr;
          found = true;
          break;
        }
      }

      if (found) {
        commitEdit(copy);
        triggerValidation(copy);
      }
    },
    [draftDesign, commitEdit, triggerValidation]
  );

  // Move Asset
  const moveAsset = useCallback(
    (instanceId: string, x: number, y: number) => {
      updateAssetInDraft(instanceId, (asset) => {
        if (asset.is_locked || asset.is_user_locked) return asset; // Respect lock
        return {
          ...asset,
          position: { ...asset.position, x, y },
        };
      });
    },
    [updateAssetInDraft]
  );

  // Rotate Asset
  const rotateAsset = useCallback(
    (instanceId: string, deg: number) => {
      updateAssetInDraft(instanceId, (asset) => {
        if (asset.is_locked || asset.is_user_locked) return asset; // Respect lock
        const normalized = ((deg % 360) + 360) % 360;
        return {
          ...asset,
          rotation_deg: normalized,
        };
      });
    },
    [updateAssetInDraft]
  );

  // Resize Asset (Configurable assets)
  const resizeAsset = useCallback(
    (instanceId: string, width: number, depth: number, height: number) => {
      updateAssetInDraft(instanceId, (asset) => {
        if (asset.is_locked || asset.is_user_locked) return asset; // Respect lock
        return {
          ...asset,
          dimensions: {
            ...asset.dimensions,
            width: Math.max(0.1, width),
            depth: Math.max(0.1, depth),
            height: Math.max(0.1, height),
          },
        };
      });
    },
    [updateAssetInDraft]
  );

  // Replace Asset
  const replaceAsset = useCallback(
    (
      instanceId: string,
      newAsset: {
        asset_id: string;
        asset_name: string;
        category: string;
        dimensions: { width: number; depth: number; height: number };
        material?: string;
        color?: string;
      }
    ) => {
      updateAssetInDraft(instanceId, (asset) => {
        if (asset.is_locked || asset.is_user_locked) return asset; // Respect lock
        return {
          ...asset,
          asset_id: newAsset.asset_id,
          asset_name: newAsset.asset_name,
          category: newAsset.category,
          dimensions: newAsset.dimensions,
          material: newAsset.material || asset.material,
          color: newAsset.color || asset.color,
        };
      });
    },
    [updateAssetInDraft]
  );

  // Add Asset from Catalog
  const addAsset = useCallback(
    (catalogItem: {
      asset_id: string;
      asset_name: string;
      category: string;
      dimensions: { width: number; depth: number; height: number };
      material?: string;
      color?: string;
    }) => {
      if (!draftDesign) return;
      const copy: PersistedRoomDesignDTO = JSON.parse(JSON.stringify(draftDesign));

      // Calculate default placement near room center
      let px = 2.0;
      let py = 2.0;
      if (copy.polygon && copy.polygon.length > 0) {
        const xs = copy.polygon.map((p) => p.x);
        const ys = copy.polygon.map((p) => p.y);
        px = (Math.min(...xs) + Math.max(...xs)) / 2;
        py = (Math.min(...ys) + Math.max(...ys)) / 2;
      }

      const newInstance: PlacedAssetPersistedDTO = {
        instance_id: `inst_manual_${Date.now()}`,
        asset_id: catalogItem.asset_id,
        asset_name: catalogItem.asset_name,
        category: catalogItem.category,
        dimensions: catalogItem.dimensions,
        position: { x: px, y: py },
        rotation_deg: 0.0,
        placement_mode: 'floor_standing',
        is_locked: false,
        is_user_locked: false,
        is_mandatory: false,
        material: catalogItem.material || 'default',
        color: catalogItem.color || '#94a3b8',
      };

      const catKey = (
        catalogItem.category === 'cabinetry'
          ? 'cabinetry'
          : catalogItem.category === 'appliance'
          ? 'appliances'
          : catalogItem.category === 'sanitary'
          ? 'sanitary_fixtures'
          : 'furniture'
      ) as keyof PersistedRoomDesignDTO;

      const arr = (copy[catKey] as PlacedAssetPersistedDTO[]) || [];
      arr.push(newInstance);
      (copy as any)[catKey] = arr;

      commitEdit(copy);
      triggerValidation(copy);
    },
    [draftDesign, commitEdit, triggerValidation]
  );

  // Remove Asset
  const removeAsset = useCallback(
    (instanceId: string) => {
      updateAssetInDraft(instanceId, (asset) => {
        if (asset.is_locked || asset.is_user_locked) return asset; // Respect lock
        return null; // Return null to signal deletion
      });
    },
    [updateAssetInDraft]
  );

  // Persistent Toggle Lock
  const toggleLock = useCallback(
    async (instanceId: string) => {
      if (!draftDesign || !projectId || !roomId) return;
      const asset = [
        ...(draftDesign.furniture || []),
        ...(draftDesign.cabinetry || []),
        ...(draftDesign.appliances || []),
        ...(draftDesign.sanitary_fixtures || []),
        ...(draftDesign.decorations || []),
      ].find((a) => a.instance_id === instanceId);

      if (!asset) return;
      const targetState = !(asset.is_locked || asset.is_user_locked);

      // Optimistic update in draft
      updateAssetInDraft(instanceId, (a) => ({
        ...a,
        is_locked: targetState,
        is_user_locked: targetState,
      }));

      // Call backend lock/unlock endpoint
      try {
        if (targetState) {
          await esaiApi.lockRoomAsset(projectId, roomId, {
            instance_id: instanceId,
            is_locked: true,
          });
        } else {
          await esaiApi.unlockRoomAsset(projectId, roomId, {
            instance_id: instanceId,
            is_locked: false,
          });
        }
      } catch (err: any) {
        console.error('Failed to persist lock toggle on server:', err);
      }
    },
    [draftDesign, projectId, roomId, updateAssetInDraft]
  );

  // Update Material / Finish
  const updateMaterial = useCallback(
    (instanceId: string, material: string, color?: string) => {
      updateAssetInDraft(instanceId, (asset) => ({
        ...asset,
        material,
        color: color || asset.color,
      }));
    },
    [updateAssetInDraft]
  );

  // Undo
  const undo = useCallback(() => {
    if (history.length === 0 || !draftDesign) return;
    const previous = history[history.length - 1];
    setHistory((prev) => prev.slice(0, prev.length - 1));
    setFuture((prev) => [JSON.parse(JSON.stringify(draftDesign)), ...prev]);
    setDraftDesign(previous);
    setIsDirty(true);
    triggerValidation(previous);
  }, [history, draftDesign, triggerValidation]);

  // Redo
  const redo = useCallback(() => {
    if (future.length === 0 || !draftDesign) return;
    const next = future[0];
    setFuture((prev) => prev.slice(1));
    setHistory((prev) => [...prev, JSON.parse(JSON.stringify(draftDesign))]);
    setDraftDesign(next);
    setIsDirty(true);
    triggerValidation(next);
  }, [future, draftDesign, triggerValidation]);

  // Discard draft and revert to initial authoritative design
  const discardDraft = useCallback(() => {
    if (initialDesign) {
      setDraftDesign(JSON.parse(JSON.stringify(initialDesign)));
      setHistory([]);
      setFuture([]);
      setIsDirty(false);
      setValidationResult(null);
      setErrorMessage(null);
    }
  }, [initialDesign]);

  // Save draft transactionally with optimistic concurrency control
  const saveDraft = useCallback(async (): Promise<boolean> => {
    if (!draftDesign || !projectId || !roomId) return false;

    // Reject save if hard constraints failed
    if (validationResult && !validationResult.hard_constraints_passed) {
      setErrorMessage('Cannot save: Layout has unresolved geometric or ergonomic violations.');
      return false;
    }

    setIsSaving(true);
    setErrorMessage(null);

    try {
      const payload = {
        room_id: roomId,
        floor_id: floorId || undefined,
        expected_design_revision: draftDesign.design_revision,
        furniture: draftDesign.furniture || [],
        cabinetry: draftDesign.cabinetry || [],
        appliances: draftDesign.appliances || [],
        sanitary_fixtures: draftDesign.sanitary_fixtures || [],
        lighting: draftDesign.lighting || [],
        electrical_points: draftDesign.electrical_points || [],
        plumbing_requirements: draftDesign.plumbing_requirements || [],
        wall_finish: draftDesign.wall_finish,
        floor_finish: draftDesign.floor_finish,
        ceiling_finish: draftDesign.ceiling_finish,
      };

      const res = await esaiApi.saveRoomEdit(projectId, roomId, payload);
      if (res.success) {
        setIsDirty(false);
        setHistory([]);
        setFuture([]);
        const updated = res.saved_design as PersistedRoomDesignDTO;
        setDraftDesign(updated);
        if (onDesignUpdated) {
          onDesignUpdated(updated);
        }
        return true;
      }
      return false;
    } catch (err: any) {
      const status = err.response?.status;
      if (status === 409) {
        setErrorMessage(
          'Conflict: Design was modified elsewhere (stale revision). Please reload to obtain the latest version.'
        );
      } else if (status === 422) {
        const detail = err.response?.data?.detail;
        setErrorMessage(
          detail?.message || 'Validation failed: placement violates room constraints.'
        );
      } else {
        setErrorMessage(err.message || 'Failed to save changes.');
      }
      return false;
    } finally {
      setIsSaving(false);
    }
  }, [draftDesign, projectId, roomId, floorId, validationResult, onDesignUpdated]);

  // Selective Regeneration of unlocked items
  const regenerateUnlocked = useCallback(
    async (seed?: number) => {
      if (!draftDesign || !projectId || !roomId) return;
      setIsRegenerating(true);
      setErrorMessage(null);

      try {
        const res = await esaiApi.regenerateUnlocked(projectId, roomId, {
          expected_design_revision: draftDesign.design_revision,
          seed: seed || 42,
        });

        if (res.success && res.saved_design) {
          const updated = res.saved_design as PersistedRoomDesignDTO;
          setDraftDesign(updated);
          setIsDirty(false);
          setHistory([]);
          setFuture([]);
          if (onDesignUpdated) {
            onDesignUpdated(updated);
          }
        }
      } catch (err: any) {
        setErrorMessage(err.response?.data?.detail?.message || 'Failed to regenerate unlocked items.');
      } finally {
        setIsRegenerating(false);
      }
    },
    [draftDesign, projectId, roomId, onDesignUpdated]
  );

  return {
    draftDesign,
    isDirty,
    canUndo: history.length > 0,
    canRedo: future.length > 0,
    validationResult,
    isValidating,
    isSaving,
    isRegenerating,
    errorMessage,
    moveAsset,
    rotateAsset,
    resizeAsset,
    replaceAsset,
    addAsset,
    removeAsset,
    toggleLock,
    updateMaterial,
    undo,
    redo,
    saveDraft,
    discardDraft,
    regenerateUnlocked,
  };
}
