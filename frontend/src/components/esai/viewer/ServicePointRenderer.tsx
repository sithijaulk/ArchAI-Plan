'use client';

import React, { useState } from 'react';
import * as THREE from 'three';
import { Html } from '@react-three/drei';
import { PlacedFixturePointDTO } from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';

interface ServicePointRendererProps {
  fixtures: PlacedFixturePointDTO[];
  floorElevation?: number;
  selectedFixtureId?: string | null;
  onSelectFixture?: (fixture: PlacedFixturePointDTO) => void;
  visible?: boolean;
}

const TYPE_COLORS: Record<string, { base: string; emissive: string; label: string }> = {
  power_socket: { base: '#f59e0b', emissive: '#b45309', label: 'Power Socket' },
  usb_charging: { base: '#3b82f6', emissive: '#1d4ed8', label: 'USB Charging' },
  tv_power: { base: '#ef4444', emissive: '#b91c1c', label: 'TV Power' },
  tv_data: { base: '#06b6d4', emissive: '#0e7490', label: 'TV Data' },
  light_switch: { base: '#10b981', emissive: '#047857', label: 'Switch' },
  ac_provision: { base: '#8b5cf6', emissive: '#6d28d9', label: 'AC Power' },
  water_heater_provision: { base: '#f97316', emissive: '#c2410c', label: 'Heater' },
  plumbing_point: { base: '#0284c7', emissive: '#0369a1', label: 'Plumbing' },
  ventilation: { base: '#64748b', emissive: '#475569', label: 'Vent' },
  default: { base: '#94a3b8', emissive: '#475569', label: 'Service Point' },
};

export const ServicePointRenderer: React.FC<ServicePointRendererProps> = ({
  fixtures,
  floorElevation = 0,
  selectedFixtureId,
  onSelectFixture,
  visible = true,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  if (!visible || !fixtures || fixtures.length === 0) return null;

  return (
    <group name="service-points-layer">
      {fixtures.map((fixture) => {
        const fixId = fixture.fixture_id || fixture.point_id || `fix_${Math.random()}`;
        const fixType = fixture.fixture_type || fixture.point_type || 'default';
        const heightM = fixture.height_from_floor_m ?? fixture.installation_height_m ?? 0.3;
        const pos = SceneDataAdapter.to3DPosition(
          fixture.position.x,
          fixture.position.y,
          floorElevation,
          heightM
        );

        const config = TYPE_COLORS[fixType] || TYPE_COLORS.default;
        const isSelected = selectedFixtureId === fixId;
        const isHovered = hoveredId === fixId;
        const isProposed = fixture.is_proposed ?? (fixture.status === 'proposed');
        const purpose = fixture.purpose || fixture.description || '';

        return (
          <group
            key={fixId}
            position={pos}
            onClick={(e) => {
              e.stopPropagation();
              onSelectFixture?.(fixture);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHoveredId(fixId);
            }}
            onPointerOut={() => setHoveredId(null)}
          >
            {/* Wall mounting plate */}
            <mesh castShadow receiveShadow>
              <boxGeometry args={[0.08, 0.08, 0.02]} />
              <meshStandardMaterial
                color={isSelected ? '#6366f1' : config.base}
                emissive={isSelected ? '#4338ca' : isHovered ? config.emissive : '#000000'}
                emissiveIntensity={isSelected || isHovered ? 0.6 : 0.1}
                roughness={0.4}
                metalness={0.2}
              />
            </mesh>

            {/* Glowing ring/indicator for proposed vs existing */}
            {isProposed && (
              <mesh position={[0, 0, 0.015]}>
                <ringGeometry args={[0.045, 0.055, 16]} />
                <meshBasicMaterial
                  color="#fbbf24"
                  side={THREE.DoubleSide}
                  transparent
                  opacity={0.8}
                />
              </mesh>
            )}

            {/* Hover tooltip */}
            {(isHovered || isSelected) && (
              <Html distanceFactor={10} position={[0, 0.12, 0]} center>
                <div className="bg-slate-900/90 text-white text-[10px] px-2 py-1 rounded shadow-lg border border-slate-700 whitespace-nowrap pointer-events-none select-none">
                  <div className="font-semibold text-amber-400">
                    {config.label} {isProposed ? '(Proposed)' : '(Existing)'}
                  </div>
                  <div className="text-slate-300">
                    Pos: ({fixture.position.x.toFixed(2)}, {fixture.position.y.toFixed(2)})m | H: {heightM.toFixed(2)}m
                  </div>
                  {purpose && <div className="text-slate-400 text-[9px]">{purpose}</div>}
                </div>
              </Html>
            )}
          </group>
        );
      })}
    </group>
  );
};
