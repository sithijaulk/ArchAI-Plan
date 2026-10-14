"""
Data-driven regulatory rule engine.
Loads verified rules or explicit test-research rules from repository.
Never fabricates unverified legal values.
"""
import json
import os
from typing import Any, Dict, List, Optional
from ..schemas import RegulatoryRule

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
        edge_type: str
    ) -> Optional[RegulatoryRule]:
        """Finds applicable setback rule for an edge classification."""
        for rule in rules:
            if rule.rule_type == "setback":
                if rule.affected_edge_type == edge_type:
                    return rule
                if edge_type in ("side_left", "side_right") and rule.affected_edge_type == "side":
                    return rule
        return None
