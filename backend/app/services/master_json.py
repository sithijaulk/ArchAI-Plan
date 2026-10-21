from copy import deepcopy
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

logger = logging.getLogger(__name__)

VALID_COMPONENTS = ("gab_gen", "vsai_rectifier", "esai_engine", "elia_engine")

CONFIG_FILE_NAME = "master_json_config.json"
_CONFIG_CACHE: Optional[Dict[str, Any]] = None
_CONFIG_MTIME: float = 0.0

DEFAULT_MASTER_JSON: dict[str, Any] = {
    "project_id": "",
    "project_name": "",
    "schema_version": "1.0",
    "land_info": {},
    "buildable_footprint": {},
    "floor_plan": {},
    "structural_rectification": {},
    "interior_layout": {},
    "exterior_landscape": {},
    "processing": {
        component: {"status": "pending"} for component in VALID_COMPONENTS
    },
}


def get_config_path() -> Path:
    """Returns the absolute path to master_json_config.json."""
    return Path(__file__).resolve().parent / CONFIG_FILE_NAME


def load_master_json_config(force_reload: bool = False) -> Dict[str, Any]:
    """Loads and caches master_json_config.json, automatically reloading if the file changed."""
    global _CONFIG_CACHE, _CONFIG_MTIME
    cfg_path = get_config_path()
    try:
        if cfg_path.exists():
            mtime = os.path.getmtime(cfg_path)
            if force_reload or _CONFIG_CACHE is None or mtime != _CONFIG_MTIME:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    _CONFIG_CACHE = json.load(f)
                _CONFIG_MTIME = mtime
                logger.info(f"Loaded Master JSON configuration from {cfg_path}")
            return _CONFIG_CACHE
    except Exception as e:
        logger.warning(f"Could not load master_json_config.json ({e}); using internal fallback.")

    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = _get_default_config()
    return _CONFIG_CACHE


def _get_default_config() -> Dict[str, Any]:
    """Fallback configuration if master_json_config.json is missing."""
    return {
        "field_mappings": {
            "project_id": ["project_id", "id", "projectId"],
            "project_name": ["project_name", "name", "projectName", "floor_plan.name"],
            "orientation": ["land_info.orientation", "orientation", "spatial_metadata.north_direction", "site.orientation"],
            "units": ["floor_plan.units", "units"],
            "rooms": ["floor_plan.rooms", "rooms", "spaces", "layout.rooms"],
            "doors": ["floor_plan.doors", "doors", "openings.doors", "entrances"],
            "windows": ["floor_plan.windows", "windows"],
            "walls": ["floor_plan.walls", "walls"],
            "structural_elements": ["floor_plan.structural_elements", "structural_elements", "columns", "pillars"],
            "boundary": ["floor_plan.boundary.coordinates", "floor_plan.boundary", "land_info.boundary_points", "boundary"],
            "area_sqft": ["land_info.area_sqft", "area_sqft"]
        },
        "room_type_aliases": {
            "living_room": ["living", "living_room", "sejour", "salon", "lounge"],
            "kitchen": ["kitchen", "cuisine", "cooking"],
            "master_bedroom": ["master_bedroom", "master_bed", "chambre_principale"],
            "bedroom": ["bedroom", "chambre", "bed"],
            "pooja_room": ["pooja", "pooja_room", "mandir", "prayer", "temple"],
            "toilet": ["toilet", "wc", "washroom", "bathroom", "bath"],
            "store_room": ["store", "store_room", "cellier", "storage"],
            "garage": ["garage", "atelier", "carport", "parking"],
            "hallway": ["hall", "hallway", "corridor"]
        },
        "direction_aliases": {
            "NORTH": ["North", "N", "top", "NORTH"],
            "SOUTH": ["South", "S", "bottom", "SOUTH"],
            "EAST": ["East", "E", "right", "EAST"],
            "WEST": ["West", "W", "left", "WEST"]
        },
        "coordinate_system_defaults": {
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down"
        },
        "unit_settings": {
            "default_unit": "mm",
            "auto_convert_m_to_mm": True,
            "meter_to_mm_factor": 1000.0,
            "sqm_to_sqft_factor": 10.7639
        }
    }


class MasterJsonAdapter:
    """Configurable normalizer and adapter that transforms raw JSON (from GAB-Gen or manual upload)
    into standard canonical ArchAI-Plan Master JSON."""

    @staticmethod
    def get_by_dot_path(data: Any, path: str) -> Any:
        """Retrieves a nested value from a dictionary using dot notation (e.g., 'floor_plan.rooms')."""
        if not isinstance(data, dict):
            return None
        parts = path.split(".")
        curr: Any = data
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return None
        return curr

    @classmethod
    def find_first(cls, data: dict, candidate_paths: List[str]) -> Any:
        """Searches for the first matching non-None value among candidate dot-paths."""
        for path in candidate_paths:
            val = cls.get_by_dot_path(data, path)
            if val is not None:
                return val
        return None

    @classmethod
    def resolve_room_type(cls, raw_type: Optional[str], raw_name: Optional[str] = None, config: Optional[dict] = None) -> str:
        """Maps any room type synonym (or room name) to its canonical room type."""
        cfg = config or load_master_json_config()
        aliases: Dict[str, List[str]] = cfg.get("room_type_aliases", {})

        targets = [t.lower().strip().replace("-", "_") for t in (raw_type or "", raw_name or "") if t]

        # 1. First pass: exact matches
        for candidate in targets:
            if candidate in aliases:
                return candidate
            for canonical, syn_list in aliases.items():
                for syn in syn_list:
                    if syn.lower().strip().replace("-", "_") == candidate:
                        return canonical

        # 2. Second pass: token / sub-word matching (avoiding false positives on generic fragments)
        for candidate in targets:
            cand_tokens = set(candidate.split("_"))
            for canonical, syn_list in aliases.items():
                for syn in syn_list:
                    syn_clean = syn.lower().strip().replace("-", "_")
                    if syn_clean in cand_tokens or (len(syn_clean) >= 4 and syn_clean in candidate):
                        return canonical

        return (raw_type or "room").lower().strip().replace("-", "_")

    @classmethod
    def resolve_direction(cls, raw_dir: Optional[str], config: Optional[dict] = None) -> str:
        """Maps any direction synonym (e.g., 'N', 'top', 'dakshina') to standard cardinal direction."""
        if not raw_dir or not isinstance(raw_dir, str):
            return "NORTH"
        cfg = config or load_master_json_config()
        aliases: Dict[str, List[str]] = cfg.get("direction_aliases", {})

        clean = raw_dir.strip().upper()
        clean_raw = raw_dir.strip().lower()

        # Check canonical uppercase keys
        if clean in aliases:
            return clean

        # Check synonyms
        for canonical, syn_list in aliases.items():
            for syn in syn_list:
                if syn.lower().strip() == clean_raw:
                    return canonical

        return raw_dir.capitalize()

    @classmethod
    def normalize(cls, raw_data: dict, force_reload_config: bool = False) -> dict:
        """Normalizes any incoming raw JSON into standard canonical ArchAI-Plan Master JSON.
        Preserves original fields while ensuring all standard paths are correctly populated."""
        if not isinstance(raw_data, dict):
            return deepcopy(DEFAULT_MASTER_JSON)

        cfg = load_master_json_config(force_reload=force_reload_config)
        mappings = cfg.get("field_mappings", {})
        unit_settings = cfg.get("unit_settings", {})
        coord_defaults = cfg.get("coordinate_system_defaults", {"origin": "top_left", "x_axis": "right", "y_axis": "down"})

        # 1. Project Identification (Do not inject defaults if absent in raw input)
        raw_pid = cls.find_first(raw_data, mappings.get("project_id", []))
        project_id = str(raw_pid).strip() if raw_pid is not None else None

        raw_pname = cls.find_first(raw_data, mappings.get("project_name", []))
        project_name = str(raw_pname).strip() if raw_pname is not None else (f"Project {project_id}" if project_id else None)

        # 2. Units & Scaling
        raw_units = str(cls.find_first(raw_data, mappings.get("units", [])) or unit_settings.get("default_unit", "mm")).lower().strip()
        is_meters = raw_units in ("m", "meter", "meters")
        auto_scale = unit_settings.get("auto_convert_m_to_mm", True) and is_meters
        scale_factor = unit_settings.get("meter_to_mm_factor", 1000.0) if auto_scale else 1.0
        final_units = "mm" if auto_scale else ("m" if is_meters else raw_units)

        # 3. Orientation & Land Info
        raw_orientation = cls.find_first(raw_data, mappings.get("orientation", []))
        final_orientation = None
        if raw_orientation is not None:
            if isinstance(raw_orientation, str) and raw_orientation.lower() in (
                "north", "south", "east", "west",
                "north-east", "north-west", "south-east", "south-west",
                "northeast", "northwest", "southeast", "southwest"
            ):
                final_orientation = raw_orientation
            else:
                canonical_dir = cls.resolve_direction(str(raw_orientation), cfg)
                final_orientation = canonical_dir.capitalize() if canonical_dir in ("NORTH", "SOUTH", "EAST", "WEST") else canonical_dir

        raw_area = cls.find_first(raw_data, mappings.get("area_sqft", []))
        area_sqft = float(raw_area) if isinstance(raw_area, (int, float)) else None

        existing_land_info = raw_data.get("land_info") if isinstance(raw_data.get("land_info"), dict) else None
        if existing_land_info is not None or final_orientation is not None or area_sqft is not None:
            land_info = deepcopy(existing_land_info or {})
            if final_orientation is not None:
                land_info["orientation"] = final_orientation
            if area_sqft is not None:
                land_info["area_sqft"] = area_sqft
        else:
            land_info = None

        # Boundary Points
        raw_boundary = cls.find_first(raw_data, mappings.get("boundary", []))
        boundary_points: List[Tuple[float, float]] = []
        if isinstance(raw_boundary, dict) and "coordinates" in raw_boundary:
            raw_boundary = raw_boundary["coordinates"]
        if isinstance(raw_boundary, list):
            if len(raw_boundary) > 0 and isinstance(raw_boundary[0], list) and len(raw_boundary[0]) > 0 and isinstance(raw_boundary[0][0], list):
                raw_boundary = raw_boundary[0]
            for pt in raw_boundary:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        boundary_points.append((float(pt[0]) * scale_factor, float(pt[1]) * scale_factor))
                    except (ValueError, TypeError):
                        pass
        if boundary_points and land_info is not None:
            land_info["boundary_points"] = boundary_points

        # 4. Rooms Normalization
        raw_rooms = cls.find_first(raw_data, mappings.get("rooms", []))
        normalized_rooms = None
        if isinstance(raw_rooms, list):
            normalized_rooms = []
            for i, r in enumerate(raw_rooms):
                if not isinstance(r, dict):
                    continue
                room_id = str(r.get("id") or f"room-{i+1:02d}")
                room_name = str(r.get("name") or room_id)
                raw_type = str(r.get("type") or "room")
                canonical_type = cls.resolve_room_type(raw_type, room_name, cfg)

                # Normalize Polygon, retaining non-numeric coordinates if invalid so validator can report them
                raw_poly = r.get("polygon") or r.get("coordinates")
                norm_poly = None
                if isinstance(raw_poly, list):
                    norm_poly = []
                    for pt in raw_poly:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            try:
                                norm_poly.append([float(pt[0]) * scale_factor, float(pt[1]) * scale_factor])
                            except (ValueError, TypeError):
                                norm_poly.append([pt[0], pt[1]])
                        else:
                            norm_poly.append(pt)

                norm_room = deepcopy(r)
                norm_room["id"] = room_id
                norm_room["name"] = room_name
                norm_room["type"] = canonical_type
                if norm_poly is not None:
                    norm_room["polygon"] = norm_poly
                normalized_rooms.append(norm_room)

        # 5. Doors Normalization
        raw_doors = cls.find_first(raw_data, mappings.get("doors", []))
        normalized_doors = []
        if isinstance(raw_doors, list):
            for i, d in enumerate(raw_doors):
                if not isinstance(d, dict):
                    continue
                d_id = str(d.get("id") or f"door-{i+1:02d}")
                d_dir = cls.resolve_direction(d.get("direction"), cfg)

                norm_door = deepcopy(d)
                norm_door["id"] = d_id
                norm_door["direction"] = d_dir
                if "position" in d and isinstance(d["position"], (list, tuple)) and len(d["position"]) >= 2:
                    try:
                        norm_door["position"] = [float(d["position"][0]) * scale_factor, float(d["position"][1]) * scale_factor]
                    except (ValueError, TypeError):
                        pass
                normalized_doors.append(norm_door)

        # 6. Windows, Walls, Structural Elements
        raw_windows = cls.find_first(raw_data, mappings.get("windows", []))
        normalized_windows = []
        if isinstance(raw_windows, list):
            for w in raw_windows:
                if isinstance(w, dict):
                    nw = deepcopy(w)
                    if "direction" in w:
                        nw["direction"] = cls.resolve_direction(w["direction"], cfg)
                    if "position" in w and isinstance(w["position"], (list, tuple)) and len(w["position"]) >= 2:
                        try:
                            nw["position"] = [float(w["position"][0]) * scale_factor, float(w["position"][1]) * scale_factor]
                        except (ValueError, TypeError):
                            pass
                    normalized_windows.append(nw)

        raw_walls = cls.find_first(raw_data, mappings.get("walls", []))
        normalized_walls = []
        if isinstance(raw_walls, list):
            for w in raw_walls:
                if isinstance(w, dict):
                    nw = deepcopy(w)
                    for pt_key in ("start", "end"):
                        if pt_key in nw and isinstance(nw[pt_key], (list, tuple)) and len(nw[pt_key]) >= 2:
                            try:
                                nw[pt_key] = [float(nw[pt_key][0]) * scale_factor, float(nw[pt_key][1]) * scale_factor]
                            except (ValueError, TypeError):
                                pass
                    normalized_walls.append(nw)

        raw_struct = cls.find_first(raw_data, mappings.get("structural_elements", []))
        normalized_struct = []
        if isinstance(raw_struct, list):
            for s in raw_struct:
                if isinstance(s, dict):
                    ns = deepcopy(s)
                    if "polygon" in s and isinstance(s["polygon"], list):
                        ns["polygon"] = [
                            [float(p[0]) * scale_factor, float(p[1]) * scale_factor]
                            for p in s["polygon"] if isinstance(p, (list, tuple)) and len(p) >= 2
                        ]
                    normalized_struct.append(ns)

        # 7. Coordinate System & Floor Plan Assembly
        existing_fp = raw_data.get("floor_plan") if isinstance(raw_data.get("floor_plan"), dict) else None
        if existing_fp is not None or normalized_rooms is not None:
            floor_plan = deepcopy(existing_fp or {})
            if project_id and not floor_plan.get("id"):
                floor_plan["id"] = f"FP-{project_id}"
            if project_name and not floor_plan.get("name"):
                floor_plan["name"] = project_name
            floor_plan["units"] = final_units

            coord_sys = floor_plan.get("coordinate_system")
            if not isinstance(coord_sys, dict):
                coord_sys = deepcopy(coord_defaults)
            floor_plan["coordinate_system"] = coord_sys

            if normalized_rooms is not None:
                floor_plan["rooms"] = normalized_rooms
            if raw_doors is not None:
                floor_plan["doors"] = normalized_doors
            if raw_windows is not None:
                floor_plan["windows"] = normalized_windows
            if raw_walls is not None:
                floor_plan["walls"] = normalized_walls
            if raw_struct is not None:
                floor_plan["structural_elements"] = normalized_struct
        else:
            floor_plan = None

        # 8. Assemble Canonical Master JSON (preserving raw structure and fields)
        canonical = deepcopy(raw_data)
        if project_id is not None:
            canonical["project_id"] = project_id
        if project_name is not None:
            canonical["project_name"] = project_name
        if land_info is not None:
            canonical["land_info"] = land_info
        if floor_plan is not None:
            canonical["floor_plan"] = floor_plan

        if final_orientation is not None:
            if "spatial_metadata" not in canonical or not isinstance(canonical["spatial_metadata"], dict):
                canonical["spatial_metadata"] = {}
            canonical["spatial_metadata"]["north_direction"] = final_orientation

        return canonical


def new_master_json(project_id: str, project_name: str) -> dict[str, Any]:
    document = deepcopy(DEFAULT_MASTER_JSON)
    document["project_id"] = project_id
    document["project_name"] = project_name
    return document


def _merge_dicts(current: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(current.get(key), dict):
            _merge_dicts(current[key], value)
        else:
            current[key] = deepcopy(value)
    return current


def merge_master_json(current: Mapping[str, Any] | None, updates: Mapping[str, Any]) -> dict[str, Any]:
    document = deepcopy(DEFAULT_MASTER_JSON)
    if current:
        _merge_dicts(document, current)
    _merge_dicts(document, updates)
    return document