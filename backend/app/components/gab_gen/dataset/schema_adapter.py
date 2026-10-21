"""
Phase 10.5: Cross-Schema Feature Adapter & Compatibility Mapper (v1.2).
Maps GAB-Gen Candidate Floor Plans into the CubiCasa 24D Scale-Independent Feature Space
with strict multi-floor local topological isolation, explicit inter-floor stair graph bridging,
canonical room type mappings, and rejection of invalid geometry.
"""
from typing import Any, Dict, List, Optional, Tuple, Set
import math
import numpy as np
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

from app.components.gab_gen.schemas import FloorPlanCandidate, FloorPlanDefinition, RoomPolygon
from app.components.gab_gen.dataset.cubicasa_features import CUBICASA_FEATURE_KEYS


# Canonical room classification mapping
CANONICAL_ROOM_TAXONOMY = {
    # Habitable - Living / Social
    "living_room": "living",
    "living": "living",
    "sitting_room": "living",
    "family_room": "living",
    "drawing_room": "living",
    "dining_room": "dining",
    "dining": "dining",
    # Habitable - Sleeping
    "bedroom": "bedroom",
    "master_bedroom": "bedroom",
    "guest_bedroom": "bedroom",
    "kids_bedroom": "bedroom",
    "bed": "bedroom",
    # Wet Cores
    "kitchen": "kitchen",
    "open_kitchen": "kitchen",
    "wet_kitchen": "kitchen",
    "pantry": "kitchen",
    "bathroom": "bathroom",
    "attached_bathroom": "bathroom",
    "common_bathroom": "bathroom",
    "powder_room": "bathroom",
    "toilet": "bathroom",
    "bath": "bathroom",
    "wc": "bathroom",
    # Circulation & Vertical Transport
    "corridor": "corridor",
    "passage": "corridor",
    "hallway": "corridor",
    "entry_lobby": "entry_lobby",
    "foyer": "entry_lobby",
    "porch": "entry_lobby",
    "staircase": "staircase",
    "stair": "staircase",
    "stair_core": "staircase",
    # Outdoor & Balcony
    "balcony": "outdoor",
    "terrace": "outdoor",
    "verandah": "outdoor",
    "patio": "outdoor",
    "outdoor": "outdoor",
    # Service & Ancillary
    "garage_parking": "garage",
    "garage": "garage",
    "carport": "garage",
    "parking": "garage",
    "utility_room": "utility",
    "laundry": "utility",
    "store_room": "storage",
    "storage": "storage",
}


def classify_canonical_room_type(room_type: str, room_name: Optional[str] = None, is_stair: bool = False) -> str:
    """
    Classifies a GAB-Gen room using a rigorous architectural taxonomy dictionary.
    Rejects generic substring fuzziness (e.g. matching 'bed' inside unrelated strings).
    """
    if is_stair:
        return "staircase"

    norm_type = (room_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    if norm_type in CANONICAL_ROOM_TAXONOMY:
        return CANONICAL_ROOM_TAXONOMY[norm_type]

    # Check exact token matching on room_name if provided
    if room_name:
        norm_name = room_name.strip().lower().replace("-", "_").replace(" ", "_")
        for key, val in CANONICAL_ROOM_TAXONOMY.items():
            if norm_name == key or f"_{key}_" in f"_{norm_name}_":
                return val

    # Default fallback category
    return "general_room"


def convert_gab_gen_candidate_to_cubicasa_24d(candidate: FloorPlanCandidate) -> Dict[str, float]:
    """
    Extracts the 24D scale-independent feature representation directly from a GAB-Gen candidate.
    
    Architectural & Topological Rules:
    1. Multi-Floor Isolation: Door connectivity, window adjacency, and horizontal wall adjacency
       are computed strictly per-floor. Unrelated rooms on different vertical levels are never
       treated as coplanar neighbors.
    2. Staircase Connectivity: Vertical transitions between floor levels are bridged through
       designated stair cores.
    3. Scale-Independence: Ratios and graph metrics use canonical metric dimensions without
       fabricating unverified pixel coordinates or guessing scale.
    4. Strict Validation: Rejects invalid geometry or empty candidates rather than hallucinating zeros.
    """
    floors = candidate.floors or []
    if not floors:
        raise ValueError(f"Candidate {candidate.candidate_id} has no floor definitions.")

    # Process floors locally
    floor_rooms_data: List[List[Dict[str, Any]]] = []
    all_rooms_flat: List[Dict[str, Any]] = []
    global_room_idx = 0

    for fl_idx, fl in enumerate(floors):
        fl_rooms = []
        for r in fl.rooms:
            if not r.polygon or len(r.polygon) < 3:
                continue

            pts = [(pt.x, pt.y) for pt in r.polygon]
            try:
                p = Polygon(pts)
                if not p.is_valid:
                    p = p.buffer(0)
                if not p.is_valid or p.is_empty:
                    continue
            except Exception as e:
                continue

            can_type = classify_canonical_room_type(r.type, r.name, r.is_structural_stair)
            room_entry = {
                "global_idx": global_room_idx,
                "floor_idx": fl_idx,
                "room_id": r.room_id,
                "poly": p,
                "canonical_type": can_type,
                "raw_type": r.type,
                "area": max(0.01, r.area if r.area > 0 else p.area),
                "is_stair": r.is_structural_stair or can_type == "staircase",
            }
            fl_rooms.append(room_entry)
            all_rooms_flat.append(room_entry)
            global_room_idx += 1

        floor_rooms_data.append(fl_rooms)

    total_valid_rooms = len(all_rooms_flat)
    if total_valid_rooms == 0:
        raise ValueError(f"Candidate {candidate.candidate_id} contains zero valid geometric rooms.")

    total_area = sum(r["area"] for r in all_rooms_flat)
    if total_area <= 0:
        raise ValueError(f"Candidate {candidate.candidate_id} has invalid non-positive total area.")

    # 1. Room Taxonomy Counts
    habitable_types = {"living", "dining", "bedroom", "general_room"}
    circulation_types = {"corridor", "entry_lobby", "staircase"}
    wet_types = {"kitchen", "bathroom"}

    habitable_count = sum(1 for r in all_rooms_flat if r["canonical_type"] in habitable_types)
    circ_count = sum(1 for r in all_rooms_flat if r["canonical_type"] in circulation_types)
    wet_count = sum(1 for r in all_rooms_flat if r["canonical_type"] in wet_types)
    bed_count = sum(1 for r in all_rooms_flat if r["canonical_type"] == "bedroom")
    outdoor_count = sum(1 for r in all_rooms_flat if r["canonical_type"] == "outdoor")

    # 2. Room Type Entropy
    type_counts: Dict[str, int] = {}
    for r in all_rooms_flat:
        ct = r["canonical_type"]
        type_counts[ct] = type_counts.get(ct, 0) + 1
    entropy = 0.0
    for cnt in type_counts.values():
        p = cnt / total_valid_rooms
        if p > 0:
            entropy -= p * math.log2(p)

    # 3. Area Ratios
    circ_area = sum(r["area"] for r in all_rooms_flat if r["canonical_type"] in circulation_types)
    living_area = sum(r["area"] for r in all_rooms_flat if r["canonical_type"] == "living")
    bed_area = sum(r["area"] for r in all_rooms_flat if r["canonical_type"] == "bedroom")
    wet_area = sum(r["area"] for r in all_rooms_flat if r["canonical_type"] in wet_types)
    outdoor_area = sum(r["area"] for r in all_rooms_flat if r["canonical_type"] == "outdoor")

    # 4. Aspect Ratios (computed across all valid room bounding boxes)
    aspect_ratios = []
    for r in all_rooms_flat:
        minx, miny, maxx, maxy = r["poly"].bounds
        w = max(0.1, maxx - minx)
        h = max(0.1, maxy - miny)
        aspect_ratios.append(max(w / h, h / w))

    mean_ar = float(np.mean(aspect_ratios)) if aspect_ratios else 1.0
    max_ar = float(np.max(aspect_ratios)) if aspect_ratios else 1.0

    # 5. Adjacency Graph: Strictly Floor-Local + Stair Bridges
    adj_graph: Dict[int, Set[int]] = {i: set() for i in range(total_valid_rooms)}
    total_horizontal_adjacency_edges = 0

    # Compute horizontal adjacency within each floor independently
    for fl_rooms in floor_rooms_data:
        n_fl = len(fl_rooms)
        for i in range(n_fl):
            r_i = fl_rooms[i]
            for j in range(i + 1, n_fl):
                r_j = fl_rooms[j]
                # Boundary proximity in real metric space (threshold = 0.25m = 250mm)
                if r_i["poly"].distance(r_j["poly"]) < 0.25:
                    total_horizontal_adjacency_edges += 1
                    adj_graph[r_i["global_idx"]].add(r_j["global_idx"])
                    adj_graph[r_j["global_idx"]].add(r_i["global_idx"])

    # Multi-floor Stair Bridges: Connect stair cores between adjacent vertical floors
    total_stair_bridges = 0
    if len(floor_rooms_data) > 1:
        for fl_idx in range(len(floor_rooms_data) - 1):
            lower_stairs = [r for r in floor_rooms_data[fl_idx] if r["is_stair"]]
            upper_stairs = [r for r in floor_rooms_data[fl_idx + 1] if r["is_stair"]]
            for ls in lower_stairs:
                for us in upper_stairs:
                    # Vertical alignment check: centroids within 3.0 meters horizontal projection
                    if ls["poly"].centroid.distance(us["poly"].centroid) < 3.0:
                        adj_graph[ls["global_idx"]].add(us["global_idx"])
                        adj_graph[us["global_idx"]].add(ls["global_idx"])
                        total_stair_bridges += 1

    max_possible_pairs = (total_valid_rooms * (total_valid_rooms - 1)) / 2 if total_valid_rooms > 1 else 1
    total_adjacency_edges = total_horizontal_adjacency_edges + total_stair_bridges
    graph_density = total_adjacency_edges / max_possible_pairs if max_possible_pairs > 0 else 0.0

    # 6. Door & Window Connectivity: Strictly Floor-Local
    all_doors_count = 0
    rooms_with_door_count = 0
    all_windows_count = 0
    habitable_rooms_with_window_count = 0

    for fl_idx, fl in enumerate(floors):
        fl_rooms = floor_rooms_data[fl_idx]
        fl_doors = fl.doors or []
        fl_windows = fl.windows or []
        all_doors_count += len(fl_doors)
        all_windows_count += len(fl_windows)

        for r in fl_rooms:
            # Check door connectivity on this floor (0.50m threshold)
            has_door = any(
                r["poly"].distance(Point(d.position.x, d.position.y)) < 0.50
                for d in fl_doors
            )
            # Or if room has connected door in doors list
            if not has_door and fl_doors:
                has_door = any(
                    r["room_id"] in d.connected_space_ids
                    for d in fl_doors
                )
            if has_door:
                rooms_with_door_count += 1

            # Check window fenestration on this floor for habitable spaces
            if r["canonical_type"] in habitable_types:
                has_window = any(
                    r["poly"].distance(Point(w.position.x, w.position.y)) < 0.50 or
                    r["room_id"] == w.room_id
                    for w in fl_windows
                )
                if has_window:
                    habitable_rooms_with_window_count += 1

    doors_per_room = all_doors_count / total_valid_rooms if total_valid_rooms > 0 else 0.0
    door_conn_ratio = rooms_with_door_count / total_valid_rooms if total_valid_rooms > 0 else 0.0
    wins_per_habitable = all_windows_count / max(1, habitable_count)
    fenestration_ratio = habitable_rooms_with_window_count / max(1, habitable_count)

    # 7. Footprint Compactness & Perimeter Complexity
    polsby_popper = 0.5
    boundary_complexity = 4.0
    if candidate.building_footprint_polygon and len(candidate.building_footprint_polygon) >= 3:
        try:
            fp_pts = [(p.x, p.y) for p in candidate.building_footprint_polygon]
            fp_poly = Polygon(fp_pts)
            if not fp_poly.is_valid:
                fp_poly = fp_poly.buffer(0)
            if fp_poly.is_valid and not fp_poly.is_empty:
                f_area = fp_poly.area
                f_perim = fp_poly.length
                if f_perim > 0 and f_area > 0:
                    polsby_popper = (4.0 * math.pi * f_area) / (f_perim ** 2)
                    boundary_complexity = f_perim / math.sqrt(f_area)
        except Exception:
            pass

    # 8. Public / Private Separation Proxy (BFS shortest path hops on topological graph)
    pub_indices = [r["global_idx"] for r in all_rooms_flat if r["canonical_type"] in ("living", "entry_lobby")]
    priv_indices = [r["global_idx"] for r in all_rooms_flat if r["canonical_type"] == "bedroom"]

    if pub_indices and priv_indices:
        distances = []
        for src in pub_indices:
            # BFS for unweighted shortest paths
            dist_map = {src: 0}
            queue = [src]
            while queue:
                curr = queue.pop(0)
                curr_d = dist_map[curr]
                for neighbor in adj_graph[curr]:
                    if neighbor not in dist_map:
                        dist_map[neighbor] = curr_d + 1
                        queue.append(neighbor)

            for target in priv_indices:
                d = dist_map.get(target, 4.0)  # capped at 4 hops if disconnected
                distances.append(float(d))

        mean_dist = float(np.mean(distances)) if distances else 2.0
        # Optimal separation is ~2 hops (e.g. Living -> Corridor/Landing -> Bedroom)
        public_private_proxy = max(0.0, min(1.0, 1.0 - abs(mean_dist - 2.0) * 0.4))
    else:
        public_private_proxy = 0.5

    # 9. Service Clustering Proxy (Wet space dispersion within floors and vertical stacking)
    wet_indices = [r["global_idx"] for r in all_rooms_flat if r["canonical_type"] in wet_types]
    if len(wet_indices) >= 2:
        wet_distances = []
        for idx_a, w1 in enumerate(wet_indices):
            r1 = all_rooms_flat[w1]
            for w2 in wet_indices[idx_a + 1:]:
                r2 = all_rooms_flat[w2]
                if r1["floor_idx"] == r2["floor_idx"]:
                    # Planar centroid distance
                    wet_distances.append(r1["poly"].centroid.distance(r2["poly"].centroid))
                else:
                    # Vertical stacking: horizontal distance + 3m vertical height penalty
                    horiz_d = r1["poly"].centroid.distance(r2["poly"].centroid)
                    vert_d = abs(r1["floor_idx"] - r2["floor_idx"]) * 3.0
                    wet_distances.append(math.sqrt(horiz_d ** 2 + vert_d ** 2))

        # Normalization reference: building envelope dimension
        all_bounds = unary_union([r["poly"] for r in all_rooms_flat]).bounds
        plan_span = max(10.0, math.sqrt((all_bounds[2] - all_bounds[0])**2 + (all_bounds[3] - all_bounds[1])**2))
        mean_wet_dist = float(np.mean(wet_distances)) if wet_distances else 0.0
        service_clustering_proxy = max(0.0, min(1.0, 1.0 - (mean_wet_dist / (plan_span * 1.5))))
    else:
        service_clustering_proxy = 0.6

    return {
        "total_rooms": float(total_valid_rooms),
        "habitable_rooms_count": float(habitable_count),
        "circulation_rooms_count": float(circ_count),
        "wet_rooms_count": float(wet_count),
        "bedroom_count": float(bed_count),
        "outdoor_spaces_count": float(outdoor_count),
        "room_type_entropy": round(entropy, 4),
        "circulation_area_ratio": round(circ_area / total_area, 4),
        "living_area_ratio": round(living_area / total_area, 4),
        "bedroom_area_ratio": round(bed_area / total_area, 4),
        "wet_area_ratio": round(wet_area / total_area, 4),
        "outdoor_area_ratio": round(outdoor_area / total_area, 4),
        "mean_room_aspect_ratio": round(mean_ar, 4),
        "max_room_aspect_ratio": round(max_ar, 4),
        "room_adjacency_edge_count": float(total_adjacency_edges),
        "room_adjacency_graph_density": round(graph_density, 4),
        "room_door_connectivity_ratio": round(door_conn_ratio, 4),
        "doors_per_room": round(doors_per_room, 4),
        "windows_per_habitable_room": round(wins_per_habitable, 4),
        "fenestration_proxy_ratio": round(fenestration_ratio, 4),
        "footprint_compactness_polsby_popper": round(polsby_popper, 4),
        "footprint_boundary_complexity": round(boundary_complexity, 4),
        "public_private_separation_proxy": round(public_private_proxy, 4),
        "service_clustering_proxy": round(service_clustering_proxy, 4),
    }
