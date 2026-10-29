/**
 * MaterialResolver.ts
 * PBR (Physically Based Rendering) Material generator for Three.js.
 * Resolves surface finishes, architectural walls, flooring, joinery, and furniture fabrics.
 */
import * as THREE from 'three';

export interface PBRMaterialProps {
  color?: string | number;
  roughness?: number;
  metalness?: number;
  transparent?: boolean;
  opacity?: number;
  wireframe?: boolean;
}

export class MaterialResolver {
  // Pre-compiled PBR material cache for GPU performance
  private static materialCache: Map<string, THREE.MeshStandardMaterial> = new Map();

  /**
   * Retrieves or creates a MeshStandardMaterial from parameters.
   */
  static getStandardMaterial(key: string, props: PBRMaterialProps): THREE.MeshStandardMaterial {
    if (this.materialCache.has(key)) {
      const mat = this.materialCache.get(key)!;
      if (props.wireframe !== undefined && mat.wireframe !== props.wireframe) {
        mat.wireframe = props.wireframe;
      }
      return mat;
    }

    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(props.color ?? '#cccccc'),
      roughness: props.roughness ?? 0.6,
      metalness: props.metalness ?? 0.1,
      transparent: props.transparent ?? false,
      opacity: props.opacity ?? 1.0,
      wireframe: props.wireframe ?? false,
    });

    this.materialCache.set(key, mat);
    return mat;
  }

  /**
   * Resolves floor surface material from client preferences or room type.
   */
  static resolveFloorMaterial(finishType?: string, roomType?: string, wireframe: boolean = false): THREE.MeshStandardMaterial {
    const f = (finishType || '').toLowerCase();
    const rt = (roomType || '').toLowerCase();

    let color = '#d4b996'; // warm oak default
    let roughness = 0.5;
    let metalness = 0.05;

    if (f.includes('marble') || rt === 'bathroom') {
      color = '#e8ecf1';
      roughness = 0.15;
      metalness = 0.1;
    } else if (f.includes('tile') || f.includes('ceramic') || rt === 'kitchen') {
      color = '#c8ced6';
      roughness = 0.3;
      metalness = 0.05;
    } else if (f.includes('walnut') || f.includes('dark_wood')) {
      color = '#5a3d28';
      roughness = 0.55;
    } else if (f.includes('concrete')) {
      color = '#8a929a';
      roughness = 0.8;
      metalness = 0.0;
    } else if (f.includes('carpet')) {
      color = '#b5afa6';
      roughness = 0.95;
    }

    return this.getStandardMaterial(`floor_${color}_${roughness}_${wireframe}`, {
      color,
      roughness,
      metalness,
      wireframe,
    });
  }

  /**
   * Resolves wall paint / surface finish material.
   */
  static resolveWallMaterial(wallType?: string, finishColor?: string, wireframe: boolean = false): THREE.MeshStandardMaterial {
    const color = finishColor || (wallType === 'exterior' ? '#d9d5ce' : '#f0ede6');
    const roughness = 0.75;
    const metalness = 0.02;

    return this.getStandardMaterial(`wall_${color}_${wireframe}`, {
      color,
      roughness,
      metalness,
      wireframe,
    });
  }

  /**
   * Resolves ceiling material with semi-transparency support for cutaway inspection.
   */
  static resolveCeilingMaterial(transparent: boolean = true, wireframe: boolean = false): THREE.MeshStandardMaterial {
    return this.getStandardMaterial(`ceiling_${transparent}_${wireframe}`, {
      color: '#f8f9fa',
      roughness: 0.9,
      metalness: 0.0,
      transparent,
      opacity: transparent ? 0.35 : 1.0,
      wireframe,
    });
  }

  /**
   * Resolves furniture and appliance PBR materials.
   */
  static resolveAssetMaterial(category: string, assetName?: string, isSelected: boolean = false, wireframe: boolean = false): THREE.MeshStandardMaterial {
    if (isSelected) {
      return this.getStandardMaterial('selected_highlight', {
        color: '#06b6d4', // cyan highlight
        roughness: 0.2,
        metalness: 0.4,
        wireframe,
      });
    }

    const cat = (category || '').toLowerCase();
    const name = (assetName || '').toLowerCase();

    let color = '#a1a8b3';
    let roughness = 0.6;
    let metalness = 0.1;

    if (cat === 'bed') {
      color = '#475569'; // fabric slate
      roughness = 0.85;
    } else if (cat === 'wardrobe' || cat === 'cabinetry' || name.includes('cabinet')) {
      color = '#334155'; // dark wood / laminate
      roughness = 0.45;
    } else if (cat === 'sofa' || cat === 'armchair') {
      color = '#3b82f6'; // navy fabric
      roughness = 0.8;
    } else if (cat === 'coffee_table' || cat === 'table' || cat === 'desk') {
      color = '#78350f'; // rich timber
      roughness = 0.5;
    } else if (cat === 'appliances' || name.includes('refrigerator') || name.includes('oven')) {
      color = '#cbd5e1'; // stainless steel
      roughness = 0.25;
      metalness = 0.75;
    } else if (cat === 'sanitary_fixtures' || name.includes('wc') || name.includes('basin')) {
      color = '#f8fafc'; // porcelain white
      roughness = 0.15;
      metalness = 0.05;
    } else if (name.includes('tv') || cat === 'tv_unit') {
      color = '#1e293b'; // obsidian black
      roughness = 0.3;
      metalness = 0.2;
    }

    return this.getStandardMaterial(`asset_${cat}_${color}_${wireframe}`, {
      color,
      roughness,
      metalness,
      wireframe,
    });
  }

  /**
   * Glass material for windows and shower screens.
   */
  static getGlassMaterial(): THREE.MeshPhysicalMaterial {
    return new THREE.MeshPhysicalMaterial({
      color: new THREE.Color('#e0f2fe'),
      transmission: 0.9,
      opacity: 0.4,
      transparent: true,
      roughness: 0.05,
      ior: 1.5,
    });
  }
}
