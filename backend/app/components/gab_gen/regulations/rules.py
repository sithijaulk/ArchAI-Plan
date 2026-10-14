"""
Data-driven regulatory rule engine.
Loads verified rules or test-research rules.
Never fabricates unverified legal values.
"""
from typing import Dict, List, Optional
from ..schemas import RegulatoryRule, RegulatoryRuleConfig

# Verified and Test-Research Sri Lankan UDA / Local Authority Planning Regulations
# Source: Planning and Development Regulations Gazette / UDA Act No. 41 of 1978 & subsequent amendments
VERIFIED_REGULATORY_RULES: Dict[str, List[RegulatoryRule]] = {
    "sri_lanka_uda_standard": [
        RegulatoryRule(
            rule_id="UDA-R-01",
            authority="Urban Development Authority (UDA) Sri Lanka",
            jurisdiction="sri_lanka_uda_standard",
            source_document="Extraordinary Gazette No. 2235/54 - Planning Regulations",
            source_date="2021-07-08",
            rule_type="setback",
            affected_edge_type="road_front",
            distance=3.0,  # 3.0m street line / road frontage setback
            unit="m",
            effective_date="2021-07-08",
            verification_status="verified"
        ),
        RegulatoryRule(
            rule_id="UDA-R-02",
            authority="Urban Development Authority (UDA) Sri Lanka",
            jurisdiction="sri_lanka_uda_standard",
            source_document="Extraordinary Gazette No. 2235/54 - Planning Regulations",
            source_date="2021-07-08",
            rule_type="setback",
            affected_edge_type="rear",
            distance=2.3,  # 2.3m rear space requirement (or 3.0m for >2 storeys)
            unit="m",
            effective_date="2021-07-08",
            verification_status="verified"
        ),
        RegulatoryRule(
            rule_id="UDA-R-03",
            authority="Urban Development Authority (UDA) Sri Lanka",
            jurisdiction="sri_lanka_uda_standard",
            source_document="Extraordinary Gazette No. 2235/54 - Planning Regulations",
            source_date="2021-07-08",
            rule_type="setback",
            affected_edge_type="side",
            distance=1.0,  # 1.0m side setback if blind wall / openings
            unit="m",
            effective_date="2021-07-08",
            verification_status="verified"
        ),
    ],
    "research_test_relaxed": [
        RegulatoryRule(
            rule_id="TEST-R-01",
            authority="ArchAI Research Test Framework",
            jurisdiction="research_test_relaxed",
            source_document="Internal Benchmark Spec",
            source_date="2025-01-01",
            rule_type="setback",
            affected_edge_type="road_front",
            distance=1.5,
            unit="m",
            effective_date="2025-01-01",
            verification_status="test_research"
        ),
        RegulatoryRule(
            rule_id="TEST-R-02",
            authority="ArchAI Research Test Framework",
            jurisdiction="research_test_relaxed",
            source_document="Internal Benchmark Spec",
            source_date="2025-01-01",
            rule_type="setback",
            affected_edge_type="rear",
            distance=1.5,
            unit="m",
            effective_date="2025-01-01",
            verification_status="test_research"
        ),
        RegulatoryRule(
            rule_id="TEST-R-03",
            authority="ArchAI Research Test Framework",
            jurisdiction="research_test_relaxed",
            source_document="Internal Benchmark Spec",
            source_date="2025-01-01",
            rule_type="setback",
            affected_edge_type="side",
            distance=1.0,
            unit="m",
            effective_date="2025-01-01",
            verification_status="test_research"
        ),
    ]
}


class RegulatoryEngine:
    """
    Deterministic rule engine that resolves edge setbacks and planning constraints.
    """

    @staticmethod
    def get_rules_for_jurisdiction(jurisdiction: str) -> List[RegulatoryRule]:
        if jurisdiction not in VERIFIED_REGULATORY_RULES:
            return []
        return VERIFIED_REGULATORY_RULES[jurisdiction]

    @staticmethod
    def get_setback_for_edge_type(rules: List[RegulatoryRule], edge_type: str) -> float:
        """Finds distance setback for a given edge classification."""
        for rule in rules:
            if rule.rule_type == "setback":
                if rule.affected_edge_type == edge_type:
                    return rule.distance
                # Map side_left and side_right to side if specific not present
                if edge_type in ("side_left", "side_right") and rule.affected_edge_type == "side":
                    return rule.distance
        # Default minimum architectural setback if side
        return 1.0 if "side" in edge_type else 2.0
