"""
Phase 10.3: CubiCasa5K Architectural Feature Extraction & Deterministic AI Proxy Quality Rubric.

Features Extracted (Pixel/Topology Safe - Strictly Scale-Free):
1. total_rooms (count)
2. habitable_rooms_count (count)
3. circulation_rooms_count (count)
4. wet_rooms_count (bath + kitchen)
5. bedroom_count (count)
6. outdoor_spaces_count (balcony/terrace)
7. room_type_entropy (Shannon entropy of space distribution)
8. circulation_area_ratio (circulation px area / total room px area)
9. living_area_ratio (living px area / total room px area)
10. bedroom_area_ratio (bedroom px area / total room px area)
11. wet_area_ratio (kitchen + bath px area / total room px area)
12. outdoor_area_ratio (outdoor px area / total room px area)
13. mean_room_aspect_ratio (mean bounding box aspect ratio across rooms)
14. max_room_aspect_ratio (worst-case elongation across rooms)
15. room_adjacency_edge_count (number of shared boundary pairs between rooms)
16. room_adjacency_graph_density (graph edges / max possible edges)
17. room_door_connectivity_ratio (fraction of rooms connected via doors)
18. doors_per_room (total doors / total rooms)
19. windows_per_habitable_room (total windows / habitable rooms)
20. fenestration_proxy_ratio (rooms with window / habitable rooms)
21. footprint_compactness_polsby_popper (4 * pi * Area / Perimeter^2 of footprint)
22. footprint_boundary_complexity (footprint perimeter / sqrt(footprint area))
23. public_private_separation_proxy (mean graph distance from living/entry to bedrooms)
24. service_clustering_proxy (proximity between wet spaces: kitchen, bathrooms)

AI Proxy Quality Rubric (0.0 to 1.0):
- functional_arrangement_proxy
- circulation_quality_proxy
- room_usability_proxy
- adjacency_privacy_proxy
- spatial_organization_proxy
- ai_proxy_quality_score (Weighted composite)
Target Origin: AI_PROXY_NOT_HUMAN_EXPERT
"""
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

from app.components.gab_gen.dataset.cubicasa_loader import CubiCasaParsedSample, CubiCasaElement


CUBICASA_FEATURE_KEYS = [
    "total_rooms",
    "habitable_rooms_count",
    "circulation_rooms_count",
    "wet_rooms_count",
    "bedroom_count",
    "outdoor_spaces_count",
    "room_type_entropy",
    "circulation_area_ratio",
    "living_area_ratio",
    "bedroom_area_ratio",
    "wet_area_ratio",
    "outdoor_area_ratio",
    "mean_room_aspect_ratio",
    "max_room_aspect_ratio",
    "room_adjacency_edge_count",
    "room_adjacency_graph_density",
    "room_door_connectivity_ratio",
    "doors_per_room",
    "windows_per_habitable_room",
    "fenestration_proxy_ratio",
    "footprint_compactness_polsby_popper",
    "footprint_boundary_complexity",
    "public_private_separation_proxy",
    "service_clustering_proxy",
]


def _build_shapely_polygon(element: CubiCasaElement) -> Optional[Polygon]:
    if len(element.polygon_points) < 3:
        return None
    pts = [(pt.x, pt.y) for pt in element.polygon_points]
    try:
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        return p if (p.is_valid and not p.is_empty) else None
    except Exception:
        return None


def extract_cubicasa_architectural_features(sample: CubiCasaParsedSample) -> Dict[str, float]:
    """
    Extracts 24 scale-independent, topological and geometric features from a CubiCasaParsedSample.
    All ratios and dimensionless indices avoid fabricating real-world metric dimensions.
    """
    rooms = sample.rooms
    total_rooms = len(rooms)
    if total_rooms == 0:
        return {k: 0.0 for k in CUBICASA_FEATURE_KEYS}

    # Build polygons and categories
    room_polys = []
    room_types = []
    room_areas = []

    for r in rooms:
        sp = _build_shapely_polygon(r)
        if sp is not None:
            room_polys.append(sp)
            room_types.append(r.canonical_type)
            room_areas.append(sp.area)

    valid_room_count = len(room_polys)
    if valid_room_count == 0:
        return {k: 0.0 for k in CUBICASA_FEATURE_KEYS}

    total_room_area = sum(room_areas) if sum(room_areas) > 0 else 1.0

    # Counts
    habitable_types = {"bedroom", "living", "dining", "general_room"}
    habitable_count = sum(1 for t in room_types if t in habitable_types)
    circ_count = sum(1 for t in room_types if t in ("corridor", "entry_lobby"))
    wet_count = sum(1 for t in room_types if t in ("kitchen", "bathroom"))
    bed_count = sum(1 for t in room_types if t == "bedroom")
    outdoor_count = sum(1 for t in room_types if t == "outdoor")

    # Room type entropy
    type_counts: Dict[str, int] = {}
    for t in room_types:
        type_counts[t] = type_counts.get(t, 0) + 1
    entropy = 0.0
    for cnt in type_counts.values():
        p = cnt / valid_room_count
        if p > 0:
            entropy -= p * math.log2(p)

    # Area ratios
    circ_area = sum(a for a, t in zip(room_areas, room_types) if t in ("corridor", "entry_lobby"))
    living_area = sum(a for a, t in zip(room_areas, room_types) if t == "living")
    bed_area = sum(a for a, t in zip(room_areas, room_types) if t == "bedroom")
    wet_area = sum(a for a, t in zip(room_areas, room_types) if t in ("kitchen", "bathroom"))
    outdoor_area = sum(a for a, t in zip(room_areas, room_types) if t == "outdoor")

    circ_ratio = circ_area / total_room_area
    living_ratio = living_area / total_room_area
    bed_ratio = bed_area / total_room_area
    wet_ratio = wet_area / total_room_area
    outdoor_ratio = outdoor_area / total_room_area

    # Room aspect ratios (length / width of minimum rotated rectangle or bounding box)
    aspect_ratios = []
    for sp in room_polys:
        minx, miny, maxx, maxy = sp.bounds
        w = max(0.1, maxx - minx)
        h = max(0.1, maxy - miny)
        ar = max(w / h, h / w)
        aspect_ratios.append(ar)

    mean_ar = float(np.mean(aspect_ratios)) if aspect_ratios else 1.0
    max_ar = float(np.max(aspect_ratios)) if aspect_ratios else 1.0

    # Adjacency graph via buffer intersection
    adjacency_pairs = 0
    adj_graph = {i: [] for i in range(valid_room_count)}
    for i in range(valid_room_count):
        for j in range(i + 1, valid_room_count):
            # Adaptive boundary proximity threshold (~0.2% of plan bounding diagonal or 2.0px)
            plan_diag = math.sqrt(max(10.0, max(sp.bounds[2] for sp in room_polys) - min(sp.bounds[0] for sp in room_polys))**2 + max(10.0, max(sp.bounds[3] for sp in room_polys) - min(sp.bounds[1] for sp in room_polys))**2)
            adj_thresh = max(1.5, plan_diag * 0.003)
            if room_polys[i].distance(room_polys[j]) < adj_thresh:
                adjacency_pairs += 1
                adj_graph[i].append(j)
                adj_graph[j].append(i)

    max_possible_pairs = (valid_room_count * (valid_room_count - 1)) / 2 if valid_room_count > 1 else 1
    graph_density = adjacency_pairs / max_possible_pairs if max_possible_pairs > 0 else 0.0

    # Door and Window relationships
    door_count = len(sample.doors)
    win_count = len(sample.windows)
    doors_per_room = door_count / valid_room_count if valid_room_count > 0 else 0.0
    wins_per_habitable = win_count / max(1, habitable_count)

    # Fenestration proxy: check rooms containing or intersecting windows
    rooms_with_window = 0
    for i, sp in enumerate(room_polys):
        if room_types[i] in habitable_types:
            has_w = False
            for w in sample.windows:
                if w.polygon_points:
                    w_pt = Point(w.polygon_points[0].x, w.polygon_points[0].y)
                    # Adaptive door/window buffer (~0.8% of plan diagonal or 8px)
                    plan_diag = math.sqrt(max(10.0, max(p.bounds[2] for p in room_polys) - min(p.bounds[0] for p in room_polys))**2 + max(10.0, max(p.bounds[3] for p in room_polys) - min(p.bounds[1] for p in room_polys))**2)
                    win_thresh = max(6.0, plan_diag * 0.008)
                    if sp.distance(w_pt) < win_thresh:
                        has_w = True
                        break
            if has_w:
                rooms_with_window += 1
    fenestration_ratio = rooms_with_window / max(1, habitable_count)

    # Door connectivity proxy
    rooms_with_door = 0
    for i, sp in enumerate(room_polys):
        has_d = False
        for d in sample.doors:
            if d.polygon_points:
                d_pt = Point(d.polygon_points[0].x, d.polygon_points[0].y)
                plan_diag = math.sqrt(max(10.0, max(p.bounds[2] for p in room_polys) - min(p.bounds[0] for p in room_polys))**2 + max(10.0, max(p.bounds[3] for p in room_polys) - min(p.bounds[1] for p in room_polys))**2)
                door_thresh = max(6.0, plan_diag * 0.008)
                if sp.distance(d_pt) < door_thresh:
                    has_d = True
                    break
        if has_d:
            rooms_with_door += 1
    door_conn_ratio = rooms_with_door / valid_room_count

    # Footprint compactness & boundary complexity
    polsby_popper = 0.5
    boundary_complexity = 4.0
    try:
        footprint_poly = unary_union(room_polys)
        if footprint_poly.is_valid and not footprint_poly.is_empty:
            f_area = footprint_poly.area
            f_perim = footprint_poly.length
            if f_perim > 0 and f_area > 0:
                polsby_popper = (4.0 * math.pi * f_area) / (f_perim ** 2)
                boundary_complexity = f_perim / math.sqrt(f_area)
    except Exception:
        pass

    # Public/Private Separation Proxy (Graph-based separation)
    public_indices = [i for i, t in enumerate(room_types) if t in ("living", "entry_lobby")]
    private_indices = [i for i, t in enumerate(room_types) if t == "bedroom"]
    if public_indices and private_indices:
        distances = []
        for pub in public_indices:
            for priv in private_indices:
                # Direct adjacency is distance 1, otherwise 2 if through intermediate, else 3
                if priv in adj_graph[pub]:
                    distances.append(1.0)
                elif any(neighbor in adj_graph[priv] for neighbor in adj_graph[pub]):
                    distances.append(2.0)
                else:
                    distances.append(3.0)
        # Moderate buffer between living and bedroom is ideal (~2 steps)
        mean_dist = float(np.mean(distances))
        public_private_proxy = max(0.0, min(1.0, 1.0 - abs(mean_dist - 2.0) * 0.4))
    else:
        public_private_proxy = 0.5

    # Service Clustering Proxy (Proximity between kitchen and bath)
    wet_indices = [i for i, t in enumerate(room_types) if t in ("kitchen", "bathroom")]
    if len(wet_indices) >= 2:
        wet_distances = []
        for i_idx, w1 in enumerate(wet_indices):
            for w2 in wet_indices[i_idx + 1:]:
                d = room_polys[w1].centroid.distance(room_polys[w2].centroid)
                wet_distances.append(d)
        max_dist = max(sp.bounds[2] - sp.bounds[0] for sp in room_polys) * math.sqrt(valid_room_count)
        mean_wet_dist = float(np.mean(wet_distances)) if wet_distances else 0.0
        service_clustering_proxy = max(0.0, min(1.0, 1.0 - (mean_wet_dist / max(1.0, max_dist))))
    else:
        service_clustering_proxy = 0.6

    return {
        "total_rooms": float(valid_room_count),
        "habitable_rooms_count": float(habitable_count),
        "circulation_rooms_count": float(circ_count),
        "wet_rooms_count": float(wet_count),
        "bedroom_count": float(bed_count),
        "outdoor_spaces_count": float(outdoor_count),
        "room_type_entropy": round(entropy, 4),
        "circulation_area_ratio": round(circ_ratio, 4),
        "living_area_ratio": round(living_ratio, 4),
        "bedroom_area_ratio": round(bed_ratio, 4),
        "wet_area_ratio": round(wet_ratio, 4),
        "outdoor_area_ratio": round(outdoor_ratio, 4),
        "mean_room_aspect_ratio": round(mean_ar, 4),
        "max_room_aspect_ratio": round(max_ar, 4),
        "room_adjacency_edge_count": float(adjacency_pairs),
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


def compute_deterministic_ai_proxy_scores(features: Dict[str, float]) -> Dict[str, float]:
    """
    Transparent, deterministic AI-assisted architectural proxy scoring rubric.
    Calculates sub-scores and composite target: ai_proxy_quality_score (0.0 to 1.0).
    Origin is strictly tagged as AI_PROXY_NOT_HUMAN_EXPERT.
    """
    # 1. Functional Arrangement (Balance of living, bedroom, wet spaces without dominance)
    living_r = features.get("living_area_ratio", 0.0)
    bed_r = features.get("bedroom_area_ratio", 0.0)
    wet_r = features.get("wet_area_ratio", 0.0)
    entropy = features.get("room_type_entropy", 0.0)
    func_score = min(1.0, max(0.1, (
        (1.0 - abs(living_r - 0.25) * 2.0) * 0.25 +
        (1.0 - abs(bed_r - 0.35) * 2.0) * 0.25 +
        (1.0 - abs(wet_r - 0.18) * 2.5) * 0.20 +
        min(1.0, entropy / 2.5) * 0.30
    )))

    # 2. Circulation Quality (Healthy corridor ratio between 8% and 18%, good door connectivity)
    circ_r = features.get("circulation_area_ratio", 0.0)
    door_conn = features.get("room_door_connectivity_ratio", 0.0)
    circ_score = min(1.0, max(0.1, (
        (1.0 - abs(circ_r - 0.12) * 3.5) * 0.50 +
        door_conn * 0.50
    )))

    # 3. Room Usability (Aspect ratios close to 1:1 or 4:3, avoiding narrow bowling-alley rooms)
    mean_ar = features.get("mean_room_aspect_ratio", 1.0)
    max_ar = features.get("max_room_aspect_ratio", 1.0)
    fenestration = features.get("fenestration_proxy_ratio", 0.0)
    usability_score = min(1.0, max(0.1, (
        (1.0 - min(1.0, max(0.0, mean_ar - 1.2) * 0.8)) * 0.40 +
        (1.0 - min(1.0, max(0.0, max_ar - 2.0) * 0.4)) * 0.30 +
        fenestration * 0.30
    )))

    # 4. Adjacency & Privacy (Public/private buffer separation and service clustering)
    pub_priv = features.get("public_private_separation_proxy", 0.5)
    service_clust = features.get("service_clustering_proxy", 0.5)
    privacy_score = min(1.0, max(0.1, (
        pub_priv * 0.60 + service_clust * 0.40
    )))

    # 5. Spatial Organization & Compactness (Polsby-Popper compactness and moderate complexity)
    compactness = features.get("footprint_compactness_polsby_popper", 0.5)
    density = features.get("room_adjacency_graph_density", 0.0)
    spatial_score = min(1.0, max(0.1, (
        min(1.0, compactness * 1.5) * 0.50 +
        min(1.0, density * 2.0) * 0.50
    )))

    # Composite AI Proxy Quality Score
    overall_proxy = round(
        func_score * 0.25 +
        circ_score * 0.20 +
        usability_score * 0.20 +
        privacy_score * 0.20 +
        spatial_score * 0.15,
        4
    )

    return {
        "functional_arrangement_proxy": round(func_score, 4),
        "circulation_quality_proxy": round(circ_score, 4),
        "room_usability_proxy": round(usability_score, 4),
        "adjacency_privacy_proxy": round(privacy_score, 4),
        "spatial_organization_proxy": round(spatial_score, 4),
        "ai_proxy_quality_score": min(1.0, max(0.0, overall_proxy)),
        "target_origin": "AI_PROXY_NOT_HUMAN_EXPERT",
    }
