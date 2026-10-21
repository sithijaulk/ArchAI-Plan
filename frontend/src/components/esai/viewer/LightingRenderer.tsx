'use client';

/**
 * LightingRenderer.tsx
 * Renders physical lighting fixtures and simulates realistic illumination
 * for downlights, pendants, wall sconces, and task lighting.
 */
import React from 'react';
import * as THREE from 'three';
import { PlacedFixturePointDTO } from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';

interface LightingRendererProps {
  fixtures: PlacedFixturePointDTO[];
  elevation?: number;
  ceilingHeight?: number;
  enabled?: boolean;
}

export const LightingRenderer: React.FC<LightingRendererProps> = ({
  fixtures,
  elevation = 0,
  ceilingHeight = 2.8,
  enabled = true,
}) => {
  if (!enabled || !fixtures || fixtures.length === 0) return null;

  return (
    <group name="lighting_layer">
      {fixtures.map((fixture) => {
        const heightM = fixture.installation_height_m ?? ceilingHeight - 0.1;
        const pos3D = SceneDataAdapter.to3DPosition(
          fixture.position.x,
          fixture.position.y,
          elevation,
          heightM
        );

        // Derive color from fixture spec or default to warm ambient
        const lightColor = fixture.spec?.color_temp === 'cool_white' ? '#e0f2fe' : '#fef08a';
        const intensity = (fixture.spec?.intensity as number) ?? 1.2;

        return (
          <group key={fixture.point_id} position={pos3D}>
            {/* Fixture Physical Mesh */}
            <mesh castShadow={false}>
              <cylinderGeometry args={[0.08, 0.08, 0.04, 16]} />
              <meshStandardMaterial
                color="#f8fafc"
                emissive={new THREE.Color(lightColor)}
                emissiveIntensity={0.8}
                roughness={0.2}
              />
            </mesh>

            {/* Downward Illumination PointLight */}
            <pointLight
              color={lightColor}
              intensity={intensity}
              distance={4.5}
              decay={2}
              castShadow={false}
              position={[0, -0.1, 0]}
            />
          </group>
        );
      })}
    </group>
  );
};
