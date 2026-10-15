"""
Ergonomic Rules & Standards Repository
Loads and validates Neufert / Architects' Data & anthropometric clearances.
Enforces provenance and verification status: unverified rules are never treated as hard constraints.
"""
import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .contracts import (
    ClearanceDirection,
    ConstraintPriority,
    StandardVerificationStatus,
)
from .exceptions import NeufertStandardRuleNotFoundError


class ErgonomicRule(BaseModel):
    id: str
    applicable_categories: List[str]
    clearance_direction: ClearanceDirection
    threshold_m: float = Field(..., gt=0.0)
    priority: ConstraintPriority
    source_title: str
    source_edition: Optional[str] = None
    source_section: Optional[str] = None
    verification_status: StandardVerificationStatus = StandardVerificationStatus.VERIFIED
    notes: Optional[str] = None

    @property
    def is_enforceable(self) -> bool:
        """Only verified or recommended rules are enforceable as design constraints."""
        return self.verification_status in (
            StandardVerificationStatus.VERIFIED,
            StandardVerificationStatus.RECOMMENDED,
        )


class ErgonomicStandardsRepository:
    """Singleton repository for Neufert and anthropometric ergonomic standards."""

    _instance: Optional["ErgonomicStandardsRepository"] = None

    def __init__(self, json_path: Optional[str] = None):
        if json_path is None:
            base_dir = os.path.dirname(__file__)
            json_path = os.path.join(base_dir, "data", "ergonomic_rules.json")
        self.json_path = json_path
        self._rules: Dict[str, ErgonomicRule] = {}
        self.load()

    @classmethod
    def get_instance(cls, json_path: Optional[str] = None) -> "ErgonomicStandardsRepository":
        if cls._instance is None:
            cls._instance = ErgonomicStandardsRepository(json_path)
        return cls._instance

    def load(self) -> None:
        if not os.path.exists(self.json_path):
            raise FileNotFoundError(f"Ergonomic rules JSON not found at {self.json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._rules.clear()
        for raw in data.get("rules", []):
            rule = ErgonomicRule(
                id=raw["id"],
                applicable_categories=raw.get("applicable_categories", []),
                clearance_direction=ClearanceDirection(raw["clearance_direction"]),
                threshold_m=float(raw["threshold_m"]),
                priority=ConstraintPriority(raw.get("priority", "hard")),
                source_title=raw.get("source_title", "Neufert Architects' Data"),
                source_edition=raw.get("source_edition"),
                source_section=raw.get("source_section"),
                verification_status=StandardVerificationStatus(raw.get("verification_status", "verified")),
                notes=raw.get("notes"),
            )
            self._rules[rule.id] = rule

    def get_all(self, enforceable_only: bool = False) -> List[ErgonomicRule]:
        rules = list(self._rules.values())
        if enforceable_only:
            return [r for r in rules if r.is_enforceable]
        return rules

    def get_by_id(self, rule_id: str) -> ErgonomicRule:
        if rule_id not in self._rules:
            raise NeufertStandardRuleNotFoundError(rule_id)
        return self._rules[rule_id]

    def get_rules_for_category(self, category: str) -> List[ErgonomicRule]:
        return [
            r for r in self._rules.values()
            if category in r.applicable_categories or "all" in r.applicable_categories
        ]
