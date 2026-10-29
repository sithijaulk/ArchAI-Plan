"""
Ergonomic Rules & Standards Repository
Loads and validates Neufert / Architects' Data & anthropometric clearances.

Provenance policy (Phase 3):
- A "verified" string in JSON is NOT accepted as proof of verification.
- A rule is only kept as VERIFIED if it carries complete evidence metadata:
  source_title, source_edition, source_section, evidence_reference, verified_by, verified_on.
- Any rule claiming VERIFIED without that evidence is automatically demoted to PROVISIONAL
  and an audit warning is recorded. This prevents unsupported source claims from being
  promoted to mandatory compliance constraints.
- Only VERIFIED + HARD rules are mandatory compliance constraints for the GA.
- PROVISIONAL / RECOMMENDED rules are advisory design heuristics (usable, never mandatory).
- UNVERIFIED rules are informational only and never enforced.
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


RULE_CLASSES = ("published_standard", "design_recommendation", "internal_heuristic")
REQUIRED_VERIFICATION_EVIDENCE = (
    "source_title",
    "source_edition",
    "source_section",
    "evidence_reference",
    "verified_by",
    "verified_on",
)


class ErgonomicRule(BaseModel):
    id: str
    category: str = "clearance"
    description: Optional[str] = None
    applicable_categories: List[str]
    clearance_direction: ClearanceDirection
    threshold_m: float = Field(..., gt=0.0)
    units: str = "m"
    priority: ConstraintPriority
    rule_class: str = "design_recommendation"
    source_title: str
    source_edition: Optional[str] = None
    source_section: Optional[str] = None
    evidence_reference: Optional[str] = None
    verified_by: Optional[str] = None
    verified_on: Optional[str] = None
    historical_source_claim: Optional[str] = None
    verification_status: StandardVerificationStatus = StandardVerificationStatus.PROVISIONAL
    verification_notes: Optional[str] = None
    conditions: List[str] = Field(default_factory=list)
    exceptions: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    audit_warnings: List[str] = Field(default_factory=list)

    @property
    def is_enforceable(self) -> bool:
        """Verified, recommended, or provisional rules may be used by the optimizer (advisory unless verified+hard)."""
        return self.verification_status in (
            StandardVerificationStatus.VERIFIED,
            StandardVerificationStatus.RECOMMENDED,
            StandardVerificationStatus.PROVISIONAL,
        )

    @property
    def is_mandatory_compliance(self) -> bool:
        """Only evidence-backed verified standards with hard priority are mandatory compliance rules."""
        return (
            self.verification_status == StandardVerificationStatus.VERIFIED
            and self.priority == ConstraintPriority.HARD
        )

    @property
    def is_advisory(self) -> bool:
        return self.is_enforceable and not self.is_mandatory_compliance


def validate_rule_provenance(raw: Dict) -> Dict:
    """
    Provenance gate. Returns a (possibly corrected) copy of the raw rule dict.
    Demotes unsupported VERIFIED claims to PROVISIONAL and records why.
    """
    data = dict(raw)
    warnings: List[str] = list(data.get("audit_warnings", []))
    status = str(data.get("verification_status", "provisional")).lower()

    if status == StandardVerificationStatus.VERIFIED.value:
        missing = [k for k in REQUIRED_VERIFICATION_EVIDENCE if not data.get(k)]
        if missing:
            data["verification_status"] = StandardVerificationStatus.PROVISIONAL.value
            warnings.append(
                "Demoted from 'verified' to 'provisional': missing verification evidence "
                f"({', '.join(missing)})."
            )

    rule_class = data.get("rule_class", "design_recommendation")
    if rule_class not in RULE_CLASSES:
        warnings.append(f"Unknown rule_class '{rule_class}'; treated as internal_heuristic.")
        data["rule_class"] = "internal_heuristic"

    data["audit_warnings"] = warnings
    return data


class ErgonomicStandardsRepository:
    """Singleton repository for Neufert and anthropometric ergonomic standards."""

    _instance: Optional["ErgonomicStandardsRepository"] = None

    def __init__(self, json_path: Optional[str] = None):
        if json_path is None:
            base_dir = os.path.dirname(__file__)
            json_path = os.path.join(base_dir, "data", "ergonomic_rules.json")
        self.json_path = json_path
        self._rules: Dict[str, ErgonomicRule] = {}
        self.load_errors: List[str] = []
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
        self.load_errors = []
        for raw in data.get("rules", []):
            checked = validate_rule_provenance(raw)
            try:
                threshold = float(checked["threshold_m"])
            except (KeyError, TypeError, ValueError):
                self.load_errors.append(f"Rule '{checked.get('id')}' has invalid threshold_m; skipped.")
                continue
            if threshold <= 0:
                self.load_errors.append(f"Rule '{checked.get('id')}' has non-positive threshold_m; skipped.")
                continue

            rule = ErgonomicRule(
                id=checked["id"],
                category=checked.get("category", "clearance"),
                description=checked.get("description"),
                applicable_categories=checked.get("applicable_categories", []),
                clearance_direction=ClearanceDirection(checked["clearance_direction"]),
                threshold_m=threshold,
                units=checked.get("units", "m"),
                priority=ConstraintPriority(checked.get("priority", "soft")),
                rule_class=checked.get("rule_class", "design_recommendation"),
                source_title=checked.get("source_title") or "Unspecified source",
                source_edition=checked.get("source_edition"),
                source_section=checked.get("source_section"),
                evidence_reference=checked.get("evidence_reference"),
                verified_by=checked.get("verified_by"),
                verified_on=checked.get("verified_on"),
                historical_source_claim=checked.get("historical_source_claim"),
                verification_status=StandardVerificationStatus(
                    checked.get("verification_status", "provisional")
                ),
                verification_notes=checked.get("verification_notes"),
                conditions=checked.get("conditions", []),
                exceptions=checked.get("exceptions", []),
                notes=checked.get("notes"),
                audit_warnings=checked.get("audit_warnings", []),
            )
            self._rules[rule.id] = rule

    def get_all(self, enforceable_only: bool = False, mandatory_only: bool = False) -> List[ErgonomicRule]:
        rules = list(self._rules.values())
        if mandatory_only:
            return [r for r in rules if r.is_mandatory_compliance]
        if enforceable_only:
            return [r for r in rules if r.is_enforceable]
        return rules

    def get_unverified_rules(self) -> List[ErgonomicRule]:
        """Returns separate unverified rules that must not be treated as mandatory standards."""
        return [
            r for r in self._rules.values()
            if r.verification_status == StandardVerificationStatus.UNVERIFIED
        ]

    def get_by_status(self, status: StandardVerificationStatus) -> List[ErgonomicRule]:
        return [r for r in self._rules.values() if r.verification_status == status]

    def audit_summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {s.value: 0 for s in StandardVerificationStatus}
        for r in self._rules.values():
            summary[r.verification_status.value] += 1
        summary["mandatory_compliance"] = sum(1 for r in self._rules.values() if r.is_mandatory_compliance)
        summary["with_audit_warnings"] = sum(1 for r in self._rules.values() if r.audit_warnings)
        return summary

    def get_by_id(self, rule_id: str) -> ErgonomicRule:
        if rule_id not in self._rules:
            raise NeufertStandardRuleNotFoundError(rule_id)
        return self._rules[rule_id]

    def get_rules_for_category(self, category: str) -> List[ErgonomicRule]:
        return [
            r for r in self._rules.values()
            if category in r.applicable_categories or "all" in r.applicable_categories
        ]
