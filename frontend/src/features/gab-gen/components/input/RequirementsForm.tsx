"use client";

import React from 'react';
import { Plus, Trash2, Home, Layers, Sparkles, Building2, MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ClientRequirements, RoomRequirement, RegulatoryContext } from '../../types';

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
  { type: 'study_office', label: 'Study / Home Office', defaultArea: 10 },
  { type: 'utility_room', label: 'Utility Room', defaultArea: 6 },
  { type: 'store_room', label: 'Store Room', defaultArea: 4 },
  { type: 'laundry', label: 'Laundry', defaultArea: 4 },
  { type: 'garage_parking', label: 'Garage / Parking', defaultArea: 18 },
  { type: 'balcony', label: 'Balcony', defaultArea: 6 },
  { type: 'other', label: 'Custom / Other Space', defaultArea: 10 },
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

  const updateRegulatory = (field: keyof RegulatoryContext, value: any) => {
    const reg = requirements.regulatory_context || { jurisdiction_id: 'sri_lanka_uda_standard' };
    onChange({
      ...requirements,
      regulatory_context: { ...reg, [field]: value }
    });
  };

  const addRoom = (type: string = 'bedroom') => {
    const option = COMMON_ROOM_OPTIONS.find(o => o.type === type);
    const newRoom: RoomRequirement = {
      id: `rm_${Date.now()}`,
      type: type,
      quantity: 1,
      required: true,
      preferred_min_area: option ? option.defaultArea : 12,
      floor_preference: 'auto',
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

  const storeyOptions = [1, 2, 3, 4];
  const floorLabels = ["Ground Floor", "1st Floor", "2nd Floor", "3rd Floor"];

  return (
    <div className="space-y-6">
      {/* 1. Project & Regulatory Context */}
      <div className="space-y-3 p-4 rounded-xl bg-card border border-border">
        <div className="flex items-center gap-2 pb-2 border-b border-border/50">
          <MapPin className="w-4 h-4 text-primary" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
            Project & Regulatory Jurisdiction
          </h4>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div>
            <Label className="text-[11px] font-medium mb-1 block">Project Name</Label>
            <Input
              type="text"
              value={requirements.project_name || ''}
              onChange={(e) => updateField('project_name', e.target.value)}
              placeholder="e.g. Modern Residential Villa"
              className="text-xs"
            />
          </div>

          <div>
            <Label className="text-[11px] font-medium mb-1 block">Regulatory Authority / By-Laws</Label>
            <select
              value={requirements.regulatory_context?.jurisdiction_id || 'sri_lanka_uda_standard'}
              onChange={(e) => updateRegulatory('jurisdiction_id', e.target.value)}
              className="w-full px-2.5 py-2 text-xs bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="sri_lanka_uda_standard">Urban Development Authority (UDA) Sri Lanka - Gazette 2235/54 (Verified)</option>
              <option value="colombo_municipal_council">Colombo Municipal Council (CMC) Building By-laws (Verified)</option>
              <option value="research_test_relaxed">ArchAI Research Benchmark (Relaxed Test Rules)</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 text-xs pt-1">
          <div>
            <Label className="text-[10px] text-muted-foreground block mb-1">Province (Optional)</Label>
            <Input
              type="text"
              value={requirements.regulatory_context?.province || ''}
              onChange={(e) => updateRegulatory('province', e.target.value)}
              placeholder="e.g. Western"
              className="text-xs h-8"
            />
          </div>
          <div>
            <Label className="text-[10px] text-muted-foreground block mb-1">District (Optional)</Label>
            <Input
              type="text"
              value={requirements.regulatory_context?.district || ''}
              onChange={(e) => updateRegulatory('district', e.target.value)}
              placeholder="e.g. Colombo"
              className="text-xs h-8"
            />
          </div>
          <div>
            <Label className="text-[10px] text-muted-foreground block mb-1">Road Width (m)</Label>
            <Input
              type="number"
              step="0.5"
              value={requirements.regulatory_context?.road_width || ''}
              onChange={(e) => updateRegulatory('road_width', parseFloat(e.target.value) || 0)}
              placeholder="e.g. 6.0"
              className="text-xs h-8"
            />
          </div>
        </div>
      </div>

      {/* 2. Land Extent & Building Profile */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 rounded-xl bg-card border border-border">
        <div>
          <Label className="text-xs font-semibold mb-1 block">Declared Land Extent</Label>
          <div className="flex gap-2">
            <Input
              type="number"
              min="0.1"
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
          <Label className="text-xs font-semibold mb-1 block">Number of Storeys (1 - 4 Floors)</Label>
          <div className="grid grid-cols-4 gap-1.5">
            {storeyOptions.map((num) => (
              <button
                key={num}
                type="button"
                onClick={() => updateField('storey_count', num)}
                className={`py-2 text-xs font-medium rounded-lg border transition-all ${
                  requirements.storey_count === num
                    ? "bg-primary text-primary-foreground border-primary shadow-sm"
                    : "bg-background text-foreground border-border hover:bg-muted"
                }`}
              >
                {num === 1 ? '1 Floor' : `${num} Fl`}
              </button>
            ))}
          </div>
        </div>

        <div>
          <Label className="text-xs font-semibold mb-1 block">Drawing Scale Ratio</Label>
          <Input
            type="text"
            value={requirements.drawing_scale || '1:100'}
            onChange={(e) => updateField('drawing_scale', e.target.value)}
            className="text-xs"
            placeholder="1:100"
          />
        </div>

        <div>
          <Label className="text-xs font-semibold mb-1 block">Preferred Total Building Area (m², Optional)</Label>
          <Input
            type="number"
            step="5"
            value={requirements.preferred_total_building_area || ''}
            onChange={(e) => updateField('preferred_total_building_area', parseFloat(e.target.value) || undefined)}
            className="text-xs"
            placeholder="e.g. 220"
          />
        </div>
      </div>

      {/* 3. Convenience Amenities & Spatial Preferences */}
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
          Amenities & Spatial Constraints
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
          <div>
            <Label className="text-[11px] text-muted-foreground block mb-1">Occupant Count</Label>
            <Input
              type="number"
              min="1"
              value={requirements.occupant_count || 4}
              onChange={(e) => updateField('occupant_count', parseInt(e.target.value) || 1)}
              className="text-xs h-8"
            />
          </div>

          <div>
            <Label className="text-[11px] text-muted-foreground block mb-1">Parking Bay Capacity</Label>
            <Input
              type="number"
              min="0"
              max="4"
              value={requirements.parking_capacity ?? 0}
              onChange={(e) => updateField('parking_capacity', parseInt(e.target.value) || 0)}
              className="text-xs h-8"
            />
          </div>

          <div>
            <Label className="text-[11px] text-muted-foreground block mb-1">Attached Bathrooms</Label>
            <Input
              type="number"
              min="0"
              max="6"
              value={requirements.attached_bathroom_count ?? 0}
              onChange={(e) => updateField('attached_bathroom_count', parseInt(e.target.value) || 0)}
              className="text-xs h-8"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-border/40 text-xs">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={requirements.open_plan_living_dining || false}
              onChange={(e) => updateField('open_plan_living_dining', e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            <span className="text-[11px]">Open-Plan Living</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={requirements.separate_kitchen ?? true}
              onChange={(e) => updateField('separate_kitchen', e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            <span className="text-[11px]">Separate Kitchen</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={requirements.study_office_requirement || false}
              onChange={(e) => updateField('study_office_requirement', e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            <span className="text-[11px]">Study / Office</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={requirements.balcony_requirement || false}
              onChange={(e) => updateField('balcony_requirement', e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            <span className="text-[11px]">Balcony Space</span>
          </label>
        </div>
      </div>

      {/* 4. Dynamic Room Programme */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-sm font-bold text-foreground">Room Programme</h4>
            <p className="text-[11px] text-muted-foreground">
              Add client requested rooms. Target minimum areas are strictly preserved as non-negotiable constraints.
            </p>
          </div>
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
                  className="bg-background border border-border rounded px-2 py-1 text-foreground max-w-[130px]"
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
                  <span className="text-[10px] text-muted-foreground">Min:</span>
                  <input
                    type="number"
                    min="2"
                    step="0.5"
                    value={room.preferred_min_area || ''}
                    onChange={(e) => updateRoom(room.id, { preferred_min_area: parseFloat(e.target.value) || 0 })}
                    className="w-14 px-1.5 py-1 text-xs bg-background border border-border rounded text-center"
                  />
                  <span className="text-[10px] text-muted-foreground">m²</span>
                </div>

                {requirements.storey_count > 1 && (
                  <select
                    value={String(room.floor_preference)}
                    onChange={(e) => updateRoom(room.id, { floor_preference: e.target.value })}
                    className="bg-background border border-border rounded px-2 py-1 text-foreground text-[11px]"
                  >
                    <option value="auto">Auto Floor</option>
                    {Array.from({ length: requirements.storey_count }).map((_, fIdx) => (
                      <option key={fIdx} value={String(fIdx)}>
                        {floorLabels[fIdx] || `Floor ${fIdx}`}
                      </option>
                    ))}
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
        {isSaving ? "Saving..." : "Save Requirements & Regulatory Context"}
      </Button>
    </div>
  );
};
