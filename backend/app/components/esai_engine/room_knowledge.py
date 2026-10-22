"""
Room Knowledge & Aesthetic Standards Repository
Loads and manages room profiles, functional relationships, and deterministic style compatibility matrices.
"""
import json
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .contracts import AestheticEvaluationDTO


class RoomProfile(BaseModel):
    room_type: str
    display_name: str
    recommended_assets: List[str] = Field(default_factory=list)
    optional_assets: List[str] = Field(default_factory=list)
    incompatible_assets: List[str] = Field(default_factory=list)
    default_min_area_sqm: float = 6.0
    typical_zones: List[str] = Field(default_factory=list)
    service_dependencies: List[str] = Field(default_factory=list)
    functional_relationships: List[Dict[str, Any]] = Field(default_factory=list)


class FunctionalRelation(BaseModel):
    primary_category: str
    related_category: str
    relation_type: str
    optimal_distance_m: Optional[float] = None
    min_distance_m: Optional[float] = None
    max_distance_m: Optional[float] = None
    is_hard_constraint: bool = False
    notes: Optional[str] = None


class StyleDefinition(BaseModel):
    name: str
    description: str
    compatible_materials: List[str] = Field(default_factory=list)
    recommended_palettes: List[str] = Field(default_factory=list)
    lighting_character: str = "neutral_architectural"
    symmetry_bias: float = 0.5
    visual_weight_balance: str = "distributed"


class RoomKnowledgeRepository:
    """Singleton repository for room profiles, functional relations, and aesthetic rules."""

    _instance: Optional["RoomKnowledgeRepository"] = None

    def __init__(
        self,
        profiles_path: Optional[str] = None,
        relations_path: Optional[str] = None,
        styles_path: Optional[str] = None,
    ):
        base_dir = os.path.dirname(__file__)
        self.profiles_path = profiles_path or os.path.join(base_dir, "data", "room_profiles.json")
        self.relations_path = relations_path or os.path.join(base_dir, "data", "functional_relations.json")
        self.styles_path = styles_path or os.path.join(base_dir, "data", "styles_catalog.json")

        self._profiles: Dict[str, RoomProfile] = {}
        self._relations: List[FunctionalRelation] = []
        self._styles: Dict[str, StyleDefinition] = {}
        self.load()

    @classmethod
    def get_instance(cls) -> "RoomKnowledgeRepository":
        if cls._instance is None:
            cls._instance = RoomKnowledgeRepository()
        return cls._instance

    def load(self) -> None:
        # 1. Room Profiles
        if os.path.exists(self.profiles_path):
            with open(self.profiles_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._profiles.clear()
            for raw in data.get("profiles", []):
                profile = RoomProfile(**raw)
                self._profiles[profile.room_type.lower()] = profile

        # 2. Functional Relations
        if os.path.exists(self.relations_path):
            with open(self.relations_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._relations.clear()
            for raw in data.get("rules", []):
                self._relations.append(FunctionalRelation(**raw))

        # 3. Styles Catalog
        if os.path.exists(self.styles_path):
            with open(self.styles_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._styles.clear()
            for key, raw in data.get("styles", {}).items():
                self._styles[key.lower()] = StyleDefinition(**raw)

    def get_profile(self, room_type: str) -> Optional[RoomProfile]:
        return self._profiles.get(room_type.lower())

    def list_profiles(self) -> List[RoomProfile]:
        return list(self._profiles.values())

    def get_functional_relations(
        self, primary_category: Optional[str] = None, related_category: Optional[str] = None
    ) -> List[FunctionalRelation]:
        results = self._relations
        if primary_category:
            results = [r for r in results if r.primary_category == primary_category]
        if related_category:
            results = [r for r in results if r.related_category == related_category]
        return results

    def list_styles(self) -> Dict[str, StyleDefinition]:
        return self._styles

    def get_style(self, style_name: str) -> Optional[StyleDefinition]:
        return self._styles.get(style_name.lower())

    def evaluate_aesthetic_compatibility(
        self,
        style_name: str,
        palette: List[str],
        materials: List[str],
    ) -> AestheticEvaluationDTO:
        """
        Deterministic, explainable aesthetic evaluation score.
        Compares selected style, palette, and materials against design knowledge standards.
        """
        style_key = style_name.lower().strip()
        style_def = self._styles.get(style_key)

        evaluations: List[str] = []

        if not style_def:
            evaluations.append(f"Style '{style_name}' is not in the recognized architectural style library.")
            return AestheticEvaluationDTO(
                overall_compatibility_score=0.5,
                dominant_style=style_name,
                palette=palette,
                material_harmony_score=0.5,
                style_cohesion_score=0.5,
                evaluations=evaluations,
            )

        # Style cohesion: checks if palette matches recommended palettes
        cohesion_matches = 0
        for p in palette:
            p_clean = p.lower().strip()
            if any(rec in p_clean or p_clean in rec for rec in style_def.recommended_palettes):
                cohesion_matches += 1

        palette_score = (cohesion_matches / len(palette)) if palette else 0.8
        style_cohesion_score = round(max(0.4, min(1.0, 0.4 + 0.6 * palette_score)), 2)
        if palette_score >= 0.5:
            evaluations.append(f"Color palette aligns with {style_def.name} design aesthetics.")
        else:
            evaluations.append(f"Color palette introduces accent contrast against standard {style_def.name} recommendations.")

        # Material harmony: checks if selected materials match compatible materials
        mat_matches = 0
        for m in materials:
            m_clean = m.lower().strip()
            if any(comp in m_clean or m_clean in comp for comp in style_def.compatible_materials):
                mat_matches += 1

        mat_score = (mat_matches / len(materials)) if materials else 0.8
        material_harmony_score = round(max(0.4, min(1.0, 0.4 + 0.6 * mat_score)), 2)
        if mat_score >= 0.5:
            evaluations.append(f"Selected materials ({', '.join(materials)}) are architecturally compatible with {style_def.name}.")
        else:
            evaluations.append(f"Material selection includes custom or hybrid finishes outside standard {style_def.name} matrix.")

        overall_score = round((style_cohesion_score * 0.5) + (material_harmony_score * 0.5), 2)
        evaluations.append(f"Computed deterministic aesthetic harmony score: {overall_score:.2f}/1.00")

        return AestheticEvaluationDTO(
            overall_compatibility_score=overall_score,
            dominant_style=style_def.name,
            palette=palette,
            material_harmony_score=material_harmony_score,
            style_cohesion_score=style_cohesion_score,
            evaluations=evaluations,
        )
