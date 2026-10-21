'use client';

/**
 * FurnitureRenderer.tsx
 * Renders accurately scaled 3D interior assets (furniture, cabinetry, appliances, sanitary fixtures).
 * Integrates procedural architectural geometry matching exact dimensions [W, D, H]
 * and supports glTF/GLB models when available.
 */
import React, { useMemo } from 'react';
import * as THREE from 'three';
import { PlacedAssetPersistedDTO } from '@/types/esai';
import { SceneDataAdapter } from './SceneDataAdapter';
import { MaterialResolver } from './MaterialResolver';

interface FurnitureRendererProps {
  asset: PlacedAssetPersistedDTO;
  elevation?: number;
  isSelected?: boolean;
  wireframe?: boolean;
  onClick?: (asset: PlacedAssetPersistedDTO, event: any) => void;
}

export const FurnitureRenderer: React.FC<FurnitureRendererProps> = ({
  asset,
  elevation = 0,
  isSelected = false,
  wireframe = false,
  onClick,
}) => {
  const { width, depth, height } = asset.dimensions;

  // Compute Three.js position: Center [X, Elevation + Height/2, -Y]
  const position3D = useMemo<[number, number, number]>(() => {
    return SceneDataAdapter.to3DPosition(asset.position.x, asset.position.y, elevation, height / 2);
  }, [asset.position.x, asset.position.y, elevation, height]);

  // Compute rotation around Y axis
  const rotation3D = useMemo<[number, number, number]>(() => {
    return SceneDataAdapter.to3DRotation(asset.rotation_deg);
  }, [asset.rotation_deg]);

  // Resolve PBR Material
  const material = useMemo(() => {
    return MaterialResolver.resolveAssetMaterial(asset.category, asset.asset_name, isSelected, wireframe);
  }, [asset.category, asset.asset_name, isSelected, wireframe]);

  // Category-specific procedural geometry for physical realism
  const renderGeometry = () => {
    const cat = (asset.category || '').toLowerCase();
    const name = (asset.asset_name || '').toLowerCase();

    if (cat === 'bed') {
      // Bed base + mattress + headboard
      const baseH = height * 0.4;
      const mattressH = height * 0.35;
      const headboardH = height * 0.9;
      const headboardD = depth * 0.08;

      return (
        <group>
          {/* Bed Frame / Base */}
          <mesh position={[0, -height / 2 + baseH / 2, 0]} material={material} castShadow receiveShadow>
            <boxGeometry args={[width, baseH, depth]} />
          </mesh>
          {/* Mattress */}
          <mesh
            position={[0, -height / 2 + baseH + mattressH / 2, headboardD / 2]}
            material={MaterialResolver.getStandardMaterial('mattress_white', { color: '#f1f5f9', roughness: 0.9 })}
            castShadow
          >
            <boxGeometry args={[width * 0.96, mattressH, depth * 0.92]} />
          </mesh>
          {/* Headboard */}
          <mesh
            position={[0, -height / 2 + headboardH / 2, -depth / 2 + headboardD / 2]}
            material={material}
            castShadow
          >
            <boxGeometry args={[width, headboardH, headboardD]} />
          </mesh>
        </group>
      );
    }

    if (cat === 'sofa' || cat === 'armchair') {
      // Seat cushion + backrest + armrests
      const seatH = height * 0.45;
      const backH = height * 0.55;
      const backD = depth * 0.22;
      const armW = width * 0.12;

      return (
        <group>
          {/* Main Seat */}
          <mesh position={[0, -height / 2 + seatH / 2, backD / 2]} material={material} castShadow receiveShadow>
            <boxGeometry args={[width - armW * 2, seatH, depth - backD]} />
          </mesh>
          {/* Backrest */}
          <mesh position={[0, -height / 2 + seatH + backH / 2, -depth / 2 + backD / 2]} material={material} castShadow>
            <boxGeometry args={[width, backH, backD]} />
          </mesh>
          {/* Left Armrest */}
          <mesh position={[-width / 2 + armW / 2, -height / 2 + (height * 0.7) / 2, backD / 2]} material={material} castShadow>
            <boxGeometry args={[armW, height * 0.7, depth]} />
          </mesh>
          {/* Right Armrest */}
          <mesh position={[width / 2 - armW / 2, -height / 2 + (height * 0.7) / 2, backD / 2]} material={material} castShadow>
            <boxGeometry args={[armW, height * 0.7, depth]} />
          </mesh>
        </group>
      );
    }

    if (cat === 'coffee_table' || cat === 'table' || cat === 'desk') {
      const topH = height * 0.08;
      const legW = Math.min(0.06, width * 0.06);

      return (
        <group>
          {/* Table Top */}
          <mesh position={[0, height / 2 - topH / 2, 0]} material={material} castShadow receiveShadow>
            <boxGeometry args={[width, topH, depth]} />
          </mesh>
          {/* 4 Legs */}
          {[-1, 1].map((xSign) =>
            [-1, 1].map((zSign) => (
              <mesh
                key={`leg_${xSign}_${zSign}`}
                position={[
                  xSign * (width / 2 - legW),
                  -topH / 2,
                  zSign * (depth / 2 - legW),
                ]}
                material={material}
                castShadow
              >
                <boxGeometry args={[legW, height - topH, legW]} />
              </mesh>
            ))
          )}
        </group>
      );
    }

    if (name.includes('tv') || cat === 'tv_unit') {
      const standH = height * 0.45;
      const tvH = height * 0.55;
      const tvW = width * 0.85;

      return (
        <group>
          {/* Media Console Base */}
          <mesh position={[0, -height / 2 + standH / 2, 0]} material={material} castShadow receiveShadow>
            <boxGeometry args={[width, standH, depth]} />
          </mesh>
          {/* TV Screen */}
          <mesh
            position={[0, -height / 2 + standH + tvH / 2, 0]}
            material={MaterialResolver.getStandardMaterial('screen_glass', { color: '#090d16', roughness: 0.1, metalness: 0.8 })}
            castShadow
          >
            <boxGeometry args={[tvW, tvH, depth * 0.1]} />
          </mesh>
        </group>
      );
    }

    if (cat === 'sanitary_fixtures' && (name.includes('basin') || name.includes('vanity'))) {
      const basinH = height * 0.15;
      return (
        <group>
          <mesh position={[0, -height / 2 + (height - basinH) / 2, 0]} material={material} castShadow receiveShadow>
            <boxGeometry args={[width, height - basinH, depth]} />
          </mesh>
          {/* Basin Top */}
          <mesh
            position={[0, height / 2 - basinH / 2, 0]}
            material={MaterialResolver.getStandardMaterial('ceramic_basin', { color: '#ffffff', roughness: 0.1 })}
            castShadow
          >
            <boxGeometry args={[width * 0.9, basinH, depth * 0.85]} />
          </mesh>
        </group>
      );
    }

    // Default accurately scaled architectural bounding volume
    return (
      <mesh material={material} castShadow receiveShadow>
        <boxGeometry args={[width, height, depth]} />
      </mesh>
    );
  };

  return (
    <group
      position={position3D}
      rotation={rotation3D}
      onClick={(e) => {
        e.stopPropagation();
        if (onClick) onClick(asset, e);
      }}
    >
      {renderGeometry()}

      {/* Selection bounding box indicator */}
      {isSelected && (
        <lineSegments>
          <edgesGeometry args={[new THREE.BoxGeometry(width * 1.04, height * 1.04, depth * 1.04)]} />
          <lineBasicMaterial color="#06b6d4" linewidth={2} />
        </lineSegments>
      )}
    </group>
  );
};
