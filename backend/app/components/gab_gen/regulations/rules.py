"""
Data-driven Western Province regulatory rule engine.
Resolves setbacks, planning constraints, and site-level restrictions deterministically
based on authority registry, UDA declared status, gazetted development plans, and zone verification.
Separates baseline technical rule availability from verified legal applicability.
An unknown authority or unconfirmed zone never receives a false-positive COMPLIANT verdict.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..schemas import (
    RegulatoryRule,
    RegulatoryContextInput,
    RegulatoryResolutionOutput,
    ApplicabilityStatus,
    ComplianceStatus,
    SiteRestrictionCheck,
    SiteRestrictionType
)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_RULES_FILE = os.path.join(_DATA_DIR, "regulatory_rules.json")
_AUTHORITY_FILE = os.path.join(_DATA_DIR, "authority_registry.json")
_SOURCES_FILE = os.path.join(_DATA_DIR, "regulatory_sources.json")


class AuthorityRegistry:
    """Canonical registry helper for Western Province Local Authorities."""
    _cache: Optional[Dict[str, Any]] = None

    @classmethod
    def load(cls) -> Dict[str, Any]:
        if cls._cache is None:
            if os.path.exists(_AUTHORITY_FILE):
                try:
                    with open(_AUTHORITY_FILE, "r", encoding="utf-8") as f:
                        cls._cache = json.load(f)
                except Exception:
                    cls._cache = {"authorities": []}
            else:
                cls._cache = {"authorities": []}
        return cls._cache

    @classmethod
    def find_authority(
        cls,
        name: Optional[str] = None,
        authority_id: Optional[str] = None,
        district: Optional[str] = None,
        authority_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        reg = cls.load()
        authorities = reg.get("authorities", [])

        # 1. Match by authority_id
        if authority_id:
            for auth in authorities:
                if auth.get("authority_id", "").upper() == authority_id.strip().upper():
                    return auth

        if not name:
            return None

        clean_name = name.strip().lower()

        # 2. Exact or alias match
        for auth in authorities:
            auth_name = auth.get("name", "").lower()
            if auth_name == clean_name:
                return auth
            for alias in auth.get("aliases", []):
                if alias.lower() == clean_name:
                    return auth

        # 3. Normalized string containment match (e.g., "Colombo Municipal Council" in "colombo mc")
        norm_input = re.sub(r"[^a-z0-9]", "", clean_name)
        for auth in authorities:
            norm_official = re.sub(r"[^a-z0-9]", "", auth.get("name", "").lower())
            if norm_input == norm_official or (len(norm_input) > 4 and norm_input in norm_official):
                # Filter by district if provided
                if district and auth.get("district", "").lower() != district.strip().lower():
                    continue
                return auth
            for alias in auth.get("aliases", []):
                norm_alias = re.sub(r"[^a-z0-9]", "", alias.lower())
                if norm_input == norm_alias:
                    return auth

        return None

    @classmethod
    def get_authorities_by_district(cls, district: str) -> List[Dict[str, Any]]:
        reg = cls.load()
        d_lower = district.strip().lower()
        return [a for a in reg.get("authorities", []) if a.get("district", "").lower() == d_lower]


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
    def load_all_sources(cls) -> List[Dict[str, Any]]:
        if not os.path.exists(_SOURCES_FILE):
            return []
        try:
            with open(_SOURCES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("sources", [])
        except Exception:
            return []

    @classmethod
    def resolve_jurisdiction(cls, reg_context: Optional[RegulatoryContextInput]) -> str:
        """
        Determines the appropriate planning jurisdiction ID based on the user's location input.
        - Colombo Municipal Council strictly maps to 'colombo_municipal_council' (City of Colombo Dev Plan).
        - Explicit benchmark overrides ('research_test_relaxed') are preserved when requested.
        - All verified Western Province councils default to 'sri_lanka_uda_standard'.
        - For backwards-compatibility with existing pipelines, returns the jurisdiction_id string.
          To get full verification status, use resolve_full_regulatory_context().
        """
        if not reg_context:
            return "sri_lanka_uda_standard"

        # Explicit benchmark or CMC override
        if reg_context.jurisdiction_id and reg_context.jurisdiction_id in ("colombo_municipal_council", "research_test_relaxed"):
            return reg_context.jurisdiction_id

        # Lookup in canonical registry
        auth = AuthorityRegistry.find_authority(
            name=reg_context.local_authority_name,
            authority_id=reg_context.authority_id,
            district=reg_context.district,
            authority_type=reg_context.local_authority_type
        )
        if auth:
            return auth.get("applicable_ruleset_id", "sri_lanka_uda_standard")

        auth_name = (reg_context.local_authority_name or "").lower()
        auth_type = (reg_context.local_authority_type or "").lower()

        # Strict check for Colombo Municipal Council
        if "colombo municipal council" in auth_name or (auth_type == "municipal_council" and "colombo" in auth_name and "dehiwala" not in auth_name):
            return "colombo_municipal_council"

        # Fallback to standard UDA baseline
        return "sri_lanka_uda_standard"

    @classmethod
    def resolve_full_regulatory_context(
        cls,
        reg_context: Optional[RegulatoryContextInput],
        allow_research_test: bool = False
    ) -> RegulatoryResolutionOutput:
        """
        Deterministic, evidence-based regulatory resolver.
        Distinguishes:
        - APPLICABLE_VERIFIED: Known council in Western Province, confirmed zone/baseline, operative gazette.
        - REQUIRES_REGULATORY_VERIFICATION: Unknown council, unverified development zone, or missing site coordinates.
        - CONFLICT_REQUIRES_REVIEW: Conflicting local bylaw vs UDA standard or contradictory rules.
        """
        disclaimers = [
            "Generated blueprints do not constitute official statutory building plan approval.",
            "Official submission to the relevant Local Authority and UDA is required prior to construction."
        ]

        if not reg_context:
            return RegulatoryResolutionOutput(
                planning_jurisdiction_id="sri_lanka_uda_standard",
                authority_verification_status="unverified",
                uda_declared_area=True,
                uda_jurisdiction_status="requires_regulatory_verification",
                development_zone=None,
                zone_verification_status="unverified",
                applicability_status=ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION,
                governing_sources=["SRC-UDA-2235-54"],
                applicable_rule_ids=[r.rule_id for r in cls.get_rules_for_jurisdiction("sri_lanka_uda_standard")],
                unresolved_requirements=[
                    "No local authority or site location provided; baseline rules applied provisionally."
                ],
                disclaimers=disclaimers
            )

        # Handle research benchmark explicitly
        if reg_context.jurisdiction_id == "research_test_relaxed":
            return RegulatoryResolutionOutput(
                planning_jurisdiction_id="research_test_relaxed",
                authority_verification_status="research_test",
                uda_declared_area=False,
                uda_jurisdiction_status="research_test",
                development_zone="research_benchmark",
                zone_verification_status="research_test",
                applicability_status=ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION,
                governing_sources=[],
                applicable_rule_ids=[r.rule_id for r in cls.get_rules_for_jurisdiction("research_test_relaxed", allow_research_test=True)],
                unresolved_requirements=["Research test benchmark active. Not valid for legal compliance."],
                disclaimers=disclaimers + ["Research test rules active. Not intended for actual construction."]
            )

        # 1. Resolve Local Authority against authoritative registry
        auth = AuthorityRegistry.find_authority(
            name=reg_context.local_authority_name,
            authority_id=reg_context.authority_id,
            district=reg_context.district,
            authority_type=reg_context.local_authority_type
        )

        unresolved: List[str] = []
        governing_sources: List[str] = []

        if auth:
            authority_id = auth.get("authority_id")
            authority_name = auth.get("name")
            authority_type = auth.get("authority_type")
            district = auth.get("district")
            jurisdiction_id = auth.get("applicable_ruleset_id", "sri_lanka_uda_standard")
            auth_status = auth.get("status", "verified")
            uda_declared = auth.get("uda_declared_area", True)
            uda_status = "verified"
            if jurisdiction_id == "colombo_municipal_council":
                governing_sources.extend(["SRC-CMC-DEV-PLAN-1999", "SRC-CMC-AMEND-2105-24"])
            else:
                governing_sources.append("SRC-UDA-2235-54")
        else:
            # UNKNOWN AUTHORITY: Safe fallback principle
            authority_id = None
            authority_name = reg_context.local_authority_name or "Unknown Authority"
            authority_type = reg_context.local_authority_type
            district = reg_context.district
            jurisdiction_id = "sri_lanka_uda_standard"
            auth_status = "unverified"
            uda_declared = True  # Baseline assumption for Western Province, but marked unverified
            uda_status = "requires_regulatory_verification"
            governing_sources.append("SRC-UDA-2235-54")
            unresolved.append(
                f"Local Authority '{authority_name}' is not in the verified Western Province Local Authority Registry. "
                "Baseline UDA rules applied provisionally, but local authority bylaws and street lines require verification."
            )

        # 2. Zone verification check
        dev_zone = reg_context.development_zone
        if dev_zone and reg_context.zone_confirmed:
            zone_status = "verified"
        elif dev_zone:
            zone_status = "requires_regulatory_verification"
            unresolved.append(
                f"Development zone '{dev_zone}' was specified without verified gazetted planning map confirmation."
            )
        else:
            zone_status = "unverified"
            unresolved.append(
                "Development zone has not been confirmed from official UDA zoning schedule; standard residential low-rise rules applied."
            )

        # 3. Road access / street line verification check
        if not reg_context.road_width or reg_context.road_width <= 0:
            unresolved.append(
                "Access road width and official street line are unconfirmed from survey deed; standard 3.0m building line applied provisionally."
            )

        # 4. Applicable Rules
        rules = cls.get_rules_for_jurisdiction(jurisdiction_id, allow_research_test=allow_research_test)
        rule_ids = [r.rule_id for r in rules]

        # 5. Applicability Status Determination
        if not auth or auth_status != "verified":
            applicability_status = ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION
        elif zone_status != "verified":
            applicability_status = ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION
        elif unresolved:
            applicability_status = ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION
        else:
            applicability_status = ApplicabilityStatus.APPLICABLE_VERIFIED

        return RegulatoryResolutionOutput(
            authority_id=authority_id,
            authority_name=authority_name,
            authority_type=authority_type,
            district=district,
            province="Western",
            authority_verification_status=auth_status,
            planning_jurisdiction_id=jurisdiction_id,
            uda_declared_area=uda_declared,
            uda_jurisdiction_status=uda_status,
            development_zone=dev_zone,
            zone_verification_status=zone_status,
            applicability_status=applicability_status,
            governing_sources=governing_sources,
            applicable_rule_ids=rule_ids,
            unresolved_requirements=unresolved,
            disclaimers=disclaimers
        )

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
