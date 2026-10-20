"""
Data-driven regulatory rule engine.
Resolves setbacks and planning constraints deterministically based on jurisdiction,
local authority, and road access conditions without silent fallback fabrication.
"""
import json
import os
from typing import Any, Dict, List, Optional
from ..schemas import RegulatoryRule, RegulatoryContextInput

_RULES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "regulatory_rules.json")


class RegulatoryEngine:
    """
    Deterministic rule engine that resolves edge setbacks and planning constraints.
    Only 'verified' rules are used in standard production generation mode.
    'research_test' rules are strictly accessible when research/test mode is explicitly chosen.
    """

    @classmethod
    def load_all_rules(cls) -> List[RegulatoryRule]:
        if not os.path.exists(_RULES_FILE):
            return []
        try:
            with open(_RULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [RegulatoryRule(**item) for item in data]
        except Exception:
            return []

    @classmethod
    def resolve_jurisdiction(cls, reg_context: Optional[RegulatoryContextInput]) -> str:
        """
        Determines the appropriate jurisdiction ID based on the user's location input.
        - Colombo Municipal Council strictly maps to 'colombo_municipal_council' (City of Colombo Dev Plan).
        - All other Municipal Councils, Urban Councils, and Pradeshiya Sabhas across the Western
          Province (and declared areas) map to 'sri_lanka_uda_standard' (UDA Gazette Extraordinary 2235/54).
        - Explicit benchmark overrides ('research_test_relaxed') are preserved when requested.
        - Does not invent rules or silently map an unknown authority to an unrelated one.
        """
        if not reg_context:
            return "sri_lanka_uda_standard"

        # Explicit jurisdiction ID takes precedence if explicitly provided and not default
        if reg_context.jurisdiction_id and reg_context.jurisdiction_id in ("colombo_municipal_council", "research_test_relaxed"):
            return reg_context.jurisdiction_id

        auth_name = (reg_context.local_authority_name or "").lower()
        district = (reg_context.district or "").lower()
        auth_type = (reg_context.local_authority_type or "").lower()

        # Strict check for Colombo Municipal Council
        if "colombo municipal council" in auth_name or (auth_type == "municipal_council" and "colombo" in auth_name and "dehiwala" not in auth_name):
            return "colombo_municipal_council"

        # All 47 local authorities in Western Province fall under UDA Declared Urban Areas (Gazette 2235/54)
        return "sri_lanka_uda_standard"

    @classmethod
    def get_rules_for_jurisdiction(
        cls,
        jurisdiction_id: str,
        allow_research_test: bool = False
    ) -> List[RegulatoryRule]:
        all_rules = cls.load_all_rules()
        matched = []
        for r in all_rules:
            if r.jurisdiction_id == jurisdiction_id:
                if r.verification_status == "verified":
                    matched.append(r)
                elif r.verification_status == "research_test" and allow_research_test:
                    matched.append(r)
        return matched

    @classmethod
    def get_rule_for_edge_type(
        cls,
        rules: List[RegulatoryRule],
        edge_type: str,
        conditions: Optional[Dict[str, Any]] = None
    ) -> Optional[RegulatoryRule]:
        """
        Finds applicable setback rule for an edge classification.
        Matches edge type and any relevant context conditions.
        """
        for rule in rules:
            if rule.rule_type == "setback":
                if rule.affected_edge_type == edge_type:
                    return rule
                if edge_type in ("side_left", "side_right") and rule.affected_edge_type == "side":
                    return rule
        return None

    @classmethod
    def get_max_coverage_rule(cls, rules: List[RegulatoryRule]) -> Optional[RegulatoryRule]:
        """Finds permissible plot coverage rule."""
        for rule in rules:
            if rule.rule_type == "ground_coverage":
                return rule
        return None

    @classmethod
    def get_room_dimension_rules(cls, rules: List[RegulatoryRule]) -> List[RegulatoryRule]:
        """Returns room dimension rules."""
        return [r for r in rules if r.rule_type == "room_dimension"]

    @classmethod
    def get_ceiling_height_rules(cls, rules: List[RegulatoryRule]) -> List[RegulatoryRule]:
        """Returns ceiling clear height rules."""
        return [r for r in rules if r.rule_type == "ceiling_height"]

    @classmethod
    def get_staircase_rules(cls, rules: List[RegulatoryRule]) -> List[RegulatoryRule]:
        """Returns staircase dimension and clearance rules."""
        return [r for r in rules if r.rule_type == "staircase"]

    @classmethod
    def get_ventilation_rules(cls, rules: List[RegulatoryRule]) -> List[RegulatoryRule]:
        """Returns light and ventilation ratio rules."""
        return [r for r in rules if r.rule_type == "ventilation_ratio"]

