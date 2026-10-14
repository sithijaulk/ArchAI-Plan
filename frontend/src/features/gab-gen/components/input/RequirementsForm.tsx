"use client";

import React from 'react';
import { Plus, Trash2, Home, Bed, Bath, Layers } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ClientRequirements, RoomRequirement } from '../../types';

interface RequirementsFormProps {
  requirements: ClientRequirements;
  onChange: (req: ClientRequirements) => void;
  onSave: () => Promise<void>;
  isSaving: boolean;
}

const COMMON_ROOM_OPTIONS = [
  { type: 'living_room', label: 'Living Room', defaultArea: 22 },
  { type: 'dining_area', label: 'Dining Area', defaultArea: 14 },
  { type: 'kitchen', label: 'Kitchen', defaultArea: 12 },
  { type: 'pantry', label: 'Pantry', defaultArea: 8 },
  { type: 'master_bedroom', label: 'Master Bedroom', defaultArea: 16 },
  { type: 'bedroom', label: 'Bedroom', defaultArea: 12 },
  { type: 'attached_bathroom', label: 'Attached Bathroom', defaultArea: 4.5 },
  { type: 'common_bathroom', label: 'Common Bathroom', defaultArea: 4.0 },
  { type: 'study_office', label: 'Study / Office', defaultArea: 10 },
  { type: 'utility_room', label: 'Utility Room', defaultArea: 6 },
  { type: 'store_room', label: 'Store Room', defaultArea: 4 },
  { type: 'laundry', label: 'Laundry', defaultArea: 4 },
  { type: 'garage_parking', label: 'Garage / Parking', defaultArea: 18 },
  { type: 'balcony', label: 'Balcony', defaultArea: 6 },
];

export const RequirementsForm: React.FC<RequirementsFormProps> = ({
  requirements,
  onChange,
  onSave,
  isSaving,
}) => {
  const updateField = (field: keyof ClientRequirements, value: any) => {
    onChange({ ...requirements, [field]: value });
  };

  const addRoom = (type: string = 'bedroom') => {
    const option = COMMON_ROOM_OPTIONS.find(o => o.type === type);
    const newRoom: RoomRequirement = {
      id: `rm_${Date.now()}`,
      type: type,
      quantity: 1,
      required: true,
      preferred_min_area: option ? option.defaultArea : 12,
      floor_preference: 'any',
      priority: 'high',
      custom_name: option ? option.label : 'Custom Room'
    };
    onChange({
      ...requirements,
      rooms: [...requirements.rooms, newRoom]
    });
  };

  const removeRoom = (id: string) => {
    onChange({
      ...requirements,
      rooms: requirements.rooms.filter(r => r.id !== id)
    });
  };

  const updateRoom = (id: string, updates: Partial<RoomRequirement>) => {
    onChange({
      ...requirements,
      rooms: requirements.rooms.map(r => (r.id === id ? { ...r, ...updates } : r))
    });
  };

  return (
    <div className="space-y-6">
      {/* Land & Building General Parameters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 rounded-xl bg-card border border-border">
        <div>
          <Label className="text-xs font-semibold mb-1 block">Declared Land Extent</Label>
          <div className="flex gap-2">
            <Input
              type="number"
              min="1"
              step="0.1"
              value={requirements.declared_land_extent || ''}
              onChange={(e) => updateField('declared_land_extent', parseFloat(e.target.value) || 0)}
              className="text-sm"
              placeholder="e.g. 10"
            />
            <select
              value={requirements.declared_land_unit}
              onChange={(e) => updateField('declared_land_unit', e.target.value as any)}
              className="px-3 py-1.5 text-xs bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="perches">Perches</option>
              <option value="sqft">Sq. Ft</option>
              <option value="sqm">Sq. Meters</option>
            </select>
          </div>
        </div>

        <div>
          <Label className="text-xs font-semibold mb-1 block">Number of Storeys</Label>
          <div className="flex gap-2">
            {[1, 2, 3].map((num) => (
              <button
                key={num}
                type="button"
                onClick={() => updateField('storey_count', num)}
                className={`flex-1 py-2 text-xs font-medium rounded-lg border transition-all ${
                  requirements.storey_count === num
                    ? "bg-primary text-primary-foreground border-primary shadow-sm"
                    : "bg-background text-foreground border-border hover:bg-muted"
                }`}
              >
                {num === 1 ? 'Single Floor (1)' : num === 2 ? 'Two Storey (2)' : 'Three Storey (3)'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Room Programme */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-sm font-bold text-foreground">Room Programme</h4>
            <p className="text-[11px] text-muted-foreground">
              Define required spaces, minimum area preferences, and floor allocations.
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => addRoom('bedroom')}
              className="text-xs h-8 gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Add Room
            </Button>
          </div>
        </div>

        {requirements.rooms.length === 0 ? (
          <div className="text-center py-8 border border-dashed rounded-xl border-border bg-card/20">
            <p className="text-xs text-muted-foreground mb-3">No rooms added to programme yet.</p>
            <div className="flex flex-wrap justify-center gap-2 max-w-md mx-auto">
              <Button size="sm" variant="secondary" onClick={() => addRoom('living_room')} className="text-xs">
                + Living Room
              </Button>
              <Button size="sm" variant="secondary" onClick={() => addRoom('kitchen')} className="text-xs">
                + Kitchen
              </Button>
              <Button size="sm" variant="secondary" onClick={() => addRoom('master_bedroom')} className="text-xs">
                + Master Bed
              </Button>
              <Button size="sm" variant="secondary" onClick={() => addRoom('bedroom')} className="text-xs">
                + Bedroom
              </Button>
              <Button size="sm" variant="secondary" onClick={() => addRoom('bathroom')} className="text-xs">
                + Bathroom
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
            {requirements.rooms.map((room) => (
              <div
                key={room.id}
                className="flex items-center gap-2 p-2.5 rounded-lg bg-card border border-border text-xs"
              >
                <select
                  value={room.type}
                  onChange={(e) => {
                    const opt = COMMON_ROOM_OPTIONS.find(o => o.type === e.target.value);
                    updateRoom(room.id, {
                      type: e.target.value,
                      custom_name: opt?.label || e.target.value,
                      preferred_min_area: opt?.defaultArea || 10
                    });
                  }}
                  className="bg-background border border-border rounded px-2 py-1 text-foreground max-w-[140px]"
                >
                  {COMMON_ROOM_OPTIONS.map((opt) => (
                    <option key={opt.type} value={opt.type}>
                      {opt.label}
                    </option>
                  ))}
                </select>

                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-muted-foreground">Qty:</span>
                  <input
                    type="number"
                    min="1"
                    max="6"
                    value={room.quantity}
                    onChange={(e) => updateRoom(room.id, { quantity: parseInt(e.target.value) || 1 })}
                    className="w-12 px-1.5 py-1 text-xs bg-background border border-border rounded text-center"
                  />
                </div>

                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-muted-foreground">Min Area:</span>
                  <input
                    type="number"
                    min="3"
                    step="0.5"
                    value={room.preferred_min_area || ''}
                    onChange={(e) => updateRoom(room.id, { preferred_min_area: parseFloat(e.target.value) || 0 })}
                    className="w-16 px-1.5 py-1 text-xs bg-background border border-border rounded text-center"
                  />
                  <span className="text-[10px] text-muted-foreground">m²</span>
                </div>

                {requirements.storey_count > 1 && (
                  <select
                    value={room.floor_preference}
                    onChange={(e) => updateRoom(room.id, { floor_preference: e.target.value as any })}
                    className="bg-background border border-border rounded px-2 py-1 text-foreground text-[11px]"
                  >
                    <option value="any">Auto Floor</option>
                    <option value="ground">Ground Floor</option>
                    <option value="first">1st Floor</option>
                    {requirements.storey_count > 2 && <option value="second">2nd Floor</option>}
                  </select>
                )}

                <div className="ml-auto flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => updateRoom(room.id, { required: !room.required })}
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                      room.required ? "bg-primary/20 text-primary border border-primary/30" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {room.required ? 'Required' : 'Optional'}
                  </button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeRoom(room.id)}
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Button
        type="button"
        onClick={onSave}
        disabled={isSaving}
        className="w-full electric-glow text-xs"
      >
        {isSaving ? "Saving..." : "Save Requirements"}
      </Button>
    </div>
  );
};
