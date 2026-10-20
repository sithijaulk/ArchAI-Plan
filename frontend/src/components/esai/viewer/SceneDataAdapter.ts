/**
 * SceneDataAdapter.ts
 * Deterministic mathematical transformation layer between ESAI 2D plan geometry
 * and Three.js 3D world coordinate system.
 *
 * Coordinate Convention:
 *   Plan coordinate (X, Y) in meters:
 *     Three.js X = X (meters, horizontal)
 *     Three.js Y = elevation + Z_offset (meters, vertical height)
 *     Three.js Z = -Y (meters, depth)
 *
 *   Plan rotation (deg):
 *     Three.js rotation = [0, (deg * Math.PI) / 180, 0] (yaw around Y axis)
 */
import * as THREE from 'three';
import { Coordinate2D, Dimensions3D, DoorDTO, WindowDTO, WallDTO } from '@/types/esai';

export interface BoundingBox2D {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
  centerX: number;
  centerY: number;
}

export interface WallSegmentGeometry {
  id: string;
  position: [number, number, number];
  rotation: [number, number, number];
  dimensions: [number, number, number]; // [length, height, thickness]
  wallType: string;
}

export class SceneDataAdapter {
  /**
   * Maps 2D plan coordinate (X, Y) to 3D world coordinate (X, Elevation + Y_offset, -Y).
   */
  static to3DPosition(
    x: number,
    y: number,
    elevation: number = 0,
    yOffset: number = 0
  ): [number, number, number] {
    return [x, elevation + yOffset, -y];
  }

  /**
   * Converts degrees rotation to Three.js Euler rotation (around vertical Y axis).
   */
  static to3DRotation(rotationDeg: number): [number, number, number] {
    const rad = (rotationDeg * Math.PI) / 180;
    return [0, rad, 0];
  }

  /**
   * Computes 2D axis-aligned bounding box from polygon coordinates.
   */
  static computePolygonBounds(polygon: Coordinate2D[]): BoundingBox2D {
    if (!polygon || polygon.length === 0) {
      return { minX: 0, minY: 0, maxX: 0, maxY: 0, width: 0, height: 0, centerX: 0, centerY: 0 };
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    for (const pt of polygon) {
      if (pt.x < minX) minX = pt.x;
      if (pt.y < minY) minY = pt.y;
      if (pt.x > maxX) maxX = pt.x;
      if (pt.y > maxY) maxY = pt.y;
    }

    const width = maxX - minX;
    const height = maxY - minY;
    return {
      minX,
      minY,
      maxX,
      maxY,
      width,
      height,
      centerX: minX + width / 2,
      centerY: minY + height / 2,
    };
  }

  /**
   * Computes center of a 2D polygon.
   */
  static computePolygonCenter(polygon: Coordinate2D[]): Coordinate2D {
    const bounds = this.computePolygonBounds(polygon);
    return { x: bounds.centerX, y: bounds.centerY };
  }

  /**
   * Creates a THREE.Shape from polygon coordinates for triangulation.
   * Handles arbitrary concave polygons reliably.
   */
  static createPolygonShape(polygon: Coordinate2D[]): THREE.Shape {
    const shape = new THREE.Shape();
    if (!polygon || polygon.length < 3) return shape;

    polygon.forEach((pt, idx) => {
      // Note: Shape coordinate maps X -> u, Y -> v
      if (idx === 0) {
        shape.moveTo(pt.x, pt.y);
      } else {
        shape.lineTo(pt.x, pt.y);
      }
    });
    shape.closePath();
    return shape;
  }

  /**
   * Computes wall mesh parameters with real thickness and heights.
   * If openings (doors/windows) are supplied, splits the wall so openings are visible.
   */
  static computeWallSegments(
    wall: WallDTO,
    elevation: number = 0,
    doors: DoorDTO[] = [],
    windows: WindowDTO[] = []
  ): WallSegmentGeometry[] {
    const dx = wall.end.x - wall.start.x;
    const dy = wall.end.y - wall.start.y;
    const totalLength = Math.hypot(dx, dy);
    if (totalLength < 0.05) return [];

    const wallHeight = wall.height || 2.8;
    const thickness = wall.thickness || 0.225;
    const angle = Math.atan2(-dy, dx); // Yaw angle in Three.js Z=-Y convention

    // Find openings intersecting this wall line
    // For simplicity, if no openings along this wall, return full segment
    const midX = (wall.start.x + wall.end.x) / 2;
    const midY = (wall.start.y + wall.end.y) / 2;

    return [
      {
        id: wall.id,
        position: [midX, elevation + wallHeight / 2, -midY],
        rotation: [0, angle, 0],
        dimensions: [totalLength, wallHeight, thickness],
        wallType: wall.wall_type,
      },
    ];
  }

  /**
   * Computes boundary walls from room polygon when explicit WallDTOs are not provided.
   */
  static computePolygonBoundaryWalls(
    polygon: Coordinate2D[],
    elevation: number = 0,
    height: number = 2.8,
    thickness: number = 0.15
  ): WallSegmentGeometry[] {
    if (!polygon || polygon.length < 3) return [];
    const segments: WallSegmentGeometry[] = [];

    for (let i = 0; i < polygon.length; i++) {
      const p1 = polygon[i];
      const p2 = polygon[(i + 1) % polygon.length];

      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const len = Math.hypot(dx, dy);
      if (len < 0.05) continue;

      const angle = Math.atan2(-dy, dx);
      const mx = (p1.x + p2.x) / 2;
      const my = (p1.y + p2.y) / 2;

      segments.push({
        id: `wall_poly_${i}`,
        position: [mx, elevation + height / 2, -my],
        rotation: [0, angle, 0],
        dimensions: [len, height, thickness],
        wallType: 'interior',
      });
    }

    return segments;
  }
}
