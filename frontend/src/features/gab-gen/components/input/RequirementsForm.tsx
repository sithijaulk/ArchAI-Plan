"use client";

import React from 'react';
import { Plus, Trash2, Home, Layers, Sparkles, Building2, MapPin, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ClientRequirements, RoomRequirement, RegulatoryContext } from '../../types';
import { SRI_LANKA_ADMIN_DATA } from '../../data/sriLankaLocations';

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

        {/* Location & Local Authority (Dependent Selections) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs pt-1">
          <div>
            <Label className="text-[10px] text-muted-foreground block mb-1">Province</Label>
            <select
              value={requirements.regulatory_context?.province || ''}
              onChange={(e) => {
                updateRegulatory('province', e.target.value);
                updateRegulatory('district', '');
                updateRegulatory('local_authority_name', '');
                updateRegulatory('local_authority_type', '');
              }}
              className="w-full px-2 py-1.5 text-xs bg-background border border-border rounded text-foreground"
            >
              <option value="">Select Province</option>
              <option value="Western">Western (47 Verified Councils)</option>
              <option value="Central">Central (Provisional)</option>
              <option value="Southern">Southern (Provisional)</option>
            </select>
          </div>

          <div>
            <Label className="text-[10px] text-muted-foreground block mb-1">District</Label>
            <select
              value={requirements.regulatory_context?.district || ''}
              onChange={(e) => {
                updateRegulatory('district', e.target.value);
                updateRegulatory('local_authority_name', '');
                updateRegulatory('local_authority_type', '');
              }}
              className="w-full px-2 py-1.5 text-xs bg-background border border-border rounded text-foreground"
            >
              <option value="">Select District</option>
              {requirements.regulatory_context?.province && SRI_LANKA_ADMIN_DATA[requirements.regulatory_context.province] &&
                Object.keys(SRI_LANKA_ADMIN_DATA[requirements.regulatory_context.province].districts).map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))
              }
            </select>
          </div>

          <div>
            <Label className="text-[10px] text-muted-foreground block mb-1">Local Authority</Label>
            <select
              value={requirements.regulatory_context?.local_authority_name || ''}
              onChange={(e) => {
                const selectedName = e.target.value;
                const prov = requirements.regulatory_context?.province || 'Western';
                const dist = requirements.regulatory_context?.district || '';
                const authObj = SRI_LANKA_ADMIN_DATA[prov]?.districts[dist]?.authorities.find(a => a.name === selectedName);
                updateRegulatory('local_authority_name', selectedName);
                if (authObj) {
                  updateRegulatory('local_authority_type', authObj.type);
                }
              }}
              className="w-full px-2 py-1.5 text-xs bg-background border border-border rounded text-foreground"
            >
              <option value="">Select Authority</option>
              {requirements.regulatory_context?.province && requirements.regulatory_context?.district &&
                SRI_LANKA_ADMIN_DATA[requirements.regulatory_context.province]?.districts[requirements.regulatory_context.district]?.authorities.map((a) => (
                  <option key={a.name} value={a.name}>
                    {a.name} ({a.type})
                  </option>
                ))
              }
            </select>
          </div>
        </div>

        {/* Development Zone & Street Line Verification */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs pt-1 border-t border-border/40">
          <div>
            <Label className="text-[10px] text-muted-foreground block mb-1">Development Zone (Optional)</Label>
            <Input
              type="text"
              value={requirements.regulatory_context?.development_zone || ''}
              onChange={(e) => updateRegulatory('development_zone', e.target.value)}
              placeholder="e.g. Primary Residential Zone / Commercial"
              className="text-xs h-8"
            />
          </div>

          <div className="flex items-center gap-2 pt-4">
            <input
              type="checkbox"
              id="zone_confirmed"
              checked={requirements.regulatory_context?.zone_confirmed || false}
              onChange={(e) => updateRegulatory('zone_confirmed', e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary w-4 h-4"
            />
            <label htmlFor="zone_confirmed" className="text-[11px] text-muted-foreground cursor-pointer select-none">
              Confirmed against official UDA Gazetted Zoning Schedule
            </label>
          </div>
        </div>

        {/* Regulatory Transparency Notice Banner */}
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-2.5 flex items-start gap-2">
          <Info className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-[11px] leading-relaxed text-muted-foreground">
            <span className="font-semibold text-foreground block mb-0.5">Statutory Planning Transparency</span>
            GAB-Gen resolves regulations against Gazette Extraordinary No. 2235/54 & City of Colombo Development Plan.
            Unknown authorities, unconfirmed zoning, or missing access road widths strictly require statutory verification prior to construction.
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
              <option value="acres">Acres</option>
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
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <Label className="text-[11px] text-muted-foreground block mb-1">Total Bedrooms</Label>
            <Input
              type="number"
              min="0"
              max="10"
              value={requirements.bedroom_count ?? ''}
              onChange={(e) => updateField('bedroom_count', parseInt(e.target.value) || 0)}
              className="text-xs h-8"
              placeholder="e.g. 3"
            />
          </div>

          <div>
            <Label className="text-[11px] text-muted-foreground block mb-1">Master Bedrooms</Label>
            <Input
              type="number"
              min="0"
              max="4"
              value={requirements.master_bedroom_count ?? ''}
              onChange={(e) => updateField('master_bedroom_count', parseInt(e.target.value) || 0)}
              className="text-xs h-8"
              placeholder="e.g. 1"
            />
          </div>

          <div>
            <Label className="text-[11px] text-muted-foreground block mb-1">Total Bathrooms</Label>
            <Input
              type="number"
              min="0"
              max="8"
              value={requirements.bathroom_count ?? ''}
              onChange={(e) => updateField('bathroom_count', parseInt(e.target.value) || 0)}
              className="text-xs h-8"
              placeholder="e.g. 2"
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

        {/* Consistency Check Alerts */}
        {requirements.bedroom_count !== undefined && requirements.master_bedroom_count !== undefined &&
          requirements.master_bedroom_count > requirements.bedroom_count && (
            <div className="p-2 bg-destructive/10 text-destructive text-[11px] rounded border border-destructive/20">
              Master bedrooms ({requirements.master_bedroom_count}) cannot exceed total bedrooms ({requirements.bedroom_count}).
            </div>
        )}
        {requirements.bathroom_count !== undefined && requirements.attached_bathroom_count !== undefined &&
          requirements.attached_bathroom_count > requirements.bathroom_count && (
            <div className="p-2 bg-destructive/10 text-destructive text-[11px] rounded border border-destructive/20">
              Attached bathrooms ({requirements.attached_bathroom_count}) cannot exceed total bathrooms ({requirements.bathroom_count}).
            </div>
        )}


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

      {/* 4. Roof Configuration & Material Preferences */}
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-border/50">
          <div className="flex items-center gap-2">
            <Home className="w-4 h-4 text-primary" />
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
              Roof Style & Architectural Preferences
            </h4>
          </div>
          <span className="text-[11px] text-muted-foreground font-mono">
            {requirements.roof_preference?.roof_type || 'flat_slab'}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div>
            <Label className="text-[11px] font-medium mb-1 block">Roof Profile</Label>
            <select
              value={requirements.roof_preference?.roof_type || 'flat_slab'}
              onChange={(e) => {
                const rType = e.target.value as any;
                const currentPref = requirements.roof_preference || {
                  roof_type: 'flat_slab',
                  pitch_angle_deg: 15,
                  overhang_m: 0.6,
                  rooftop_access: false,
                  drainage_preference: 'concealed_gutters'
                };
                updateField('roof_preference', {
                  ...currentPref,
                  roof_type: rType,
                  pitch_angle_deg: rType === 'flat_slab' || rType === 'accessible_rooftop' ? 0 : 18.0
                });
              }}
              className="w-full px-2.5 py-2 text-xs bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="flat_slab">Flat Concrete Slab (Minimalist / Modern)</option>
              <option value="accessible_rooftop">Accessible Rooftop Terrace (With Parapet)</option>
              <option value="gable">Gable Roof (Dual Pitch / High Ceiling)</option>
              <option value="hip">Hip Roof (Quad Slope / Wind-Resistant)</option>
              <option value="mono_pitch">Mono-Pitch / Shed Roof (Contemporary)</option>
            </select>
          </div>

          <div>
            <Label className="text-[11px] font-medium mb-1 block">Roofing Material</Label>
            <select
              value={requirements.roof_preference?.material || 'concrete_tile'}
              onChange={(e) => {
                const currentPref = requirements.roof_preference || {
                  roof_type: 'flat_slab',
                  pitch_angle_deg: 0,
                  overhang_m: 0.6,
                  rooftop_access: false,
                  drainage_preference: 'concealed_gutters'
                };
                updateField('roof_preference', { ...currentPref, material: e.target.value });
              }}
              className="w-full px-2.5 py-2 text-xs bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="concrete_tile">Concrete Roof Tiles</option>
              <option value="clay_tile">Sinhala / Clay Tiles (Traditional)</option>
              <option value="metal_deck">Zinc-Alum / Standing Seam Metal Deck</option>
              <option value="concrete_slab">Waterproof Reinforced Concrete Slab</option>
              <option value="asphalt_shingle">Asphalt Shingles</option>
            </select>
          </div>

          <div>
            <Label className="text-[11px] font-medium mb-1 block">Stormwater Drainage</Label>
            <select
              value={requirements.roof_preference?.drainage_preference || 'concealed_gutters'}
              onChange={(e) => {
                const currentPref = requirements.roof_preference || {
                  roof_type: 'flat_slab',
                  pitch_angle_deg: 0,
                  overhang_m: 0.6,
                  rooftop_access: false,
                  drainage_preference: 'concealed_gutters'
                };
                updateField('roof_preference', { ...currentPref, drainage_preference: e.target.value });
              }}
              className="w-full px-2.5 py-2 text-xs bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="concealed_gutters">Concealed Box Gutters</option>
              <option value="external_downpipes">External UPVC Downpipes</option>
              <option value="slope_to_rear">Slope towards Rear Garden</option>
            </select>
          </div>
        </div>

        {/* Conditional Roof Parameters */}
        {requirements.roof_preference?.roof_type !== 'flat_slab' && requirements.roof_preference?.roof_type !== 'accessible_rooftop' && (
          <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/40 text-xs">
            <div>
              <Label className="text-[11px] text-muted-foreground block mb-1">
                Pitch Angle: <strong className="text-foreground">{requirements.roof_preference?.pitch_angle_deg ?? 18}°</strong>
              </Label>
              <input
                type="range"
                min="10"
                max="40"
                step="1"
                value={requirements.roof_preference?.pitch_angle_deg ?? 18}
                onChange={(e) => {
                  const currentPref = requirements.roof_preference || {
                    roof_type: 'gable',
                    pitch_angle_deg: 18,
                    overhang_m: 0.6,
                    rooftop_access: false,
                    drainage_preference: 'concealed_gutters'
                  };
                  updateField('roof_preference', { ...currentPref, pitch_angle_deg: parseFloat(e.target.value) });
                }}
                className="w-full accent-primary cursor-pointer"
              />
            </div>

            <div>
              <Label className="text-[11px] text-muted-foreground block mb-1">
                Eaves Overhang: <strong className="text-foreground">{requirements.roof_preference?.overhang_m ?? 0.6} m</strong>
              </Label>
              <input
                type="range"
                min="0.2"
                max="1.2"
                step="0.1"
                value={requirements.roof_preference?.overhang_m ?? 0.6}
                onChange={(e) => {
                  const currentPref = requirements.roof_preference || {
                    roof_type: 'gable',
                    pitch_angle_deg: 18,
                    overhang_m: 0.6,
                    rooftop_access: false,
                    drainage_preference: 'concealed_gutters'
                  };
                  updateField('roof_preference', { ...currentPref, overhang_m: parseFloat(e.target.value) });
                }}
                className="w-full accent-primary cursor-pointer"
              />
            </div>
          </div>
        )}

        {requirements.roof_preference?.roof_type === 'accessible_rooftop' && (
          <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border/40 text-xs">
            <div>
              <Label className="text-[11px] text-muted-foreground block mb-1">Parapet Safety Wall Height (m)</Label>
              <Input
                type="number"
                min="0.9"
                max="1.5"
                step="0.05"
                value={requirements.roof_preference?.parapet_height_m ?? 1.0}
                onChange={(e) => {
                  const currentPref = requirements.roof_preference || {
                    roof_type: 'accessible_rooftop',
                    pitch_angle_deg: 0,
                    overhang_m: 0.0,
                    rooftop_access: true,
                    drainage_preference: 'concealed_gutters'
                  };
                  updateField('roof_preference', { ...currentPref, parapet_height_m: parseFloat(e.target.value) || 1.0 });
                }}
                className="text-xs h-8"
              />
            </div>

            <div className="flex items-center pt-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={requirements.roof_preference?.rooftop_access ?? true}
                  onChange={(e) => {
                    const currentPref = requirements.roof_preference || {
                      roof_type: 'accessible_rooftop',
                      pitch_angle_deg: 0,
                      overhang_m: 0.0,
                      rooftop_access: true,
                      drainage_preference: 'concealed_gutters'
                    };
                    updateField('roof_preference', { ...currentPref, rooftop_access: e.target.checked });
                  }}
                  className="rounded border-border text-primary focus:ring-primary"
                />
                <span className="text-[11px] font-medium">Staircase Access to Terrace</span>
              </label>
            </div>
          </div>
        )}
      </div>

      {/* 5. Dynamic Room Programme */}
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
