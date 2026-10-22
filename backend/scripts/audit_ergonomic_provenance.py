"""
Phase 3 Ergonomic Rule Provenance Audit (idempotent).

Corrects misleading verification metadata in data/ergonomic_rules.json:
- Licensed Neufert material is NOT available in this repository, so no page number,
  section or numeric value attributed to Neufert can be confirmed here.
- Page references previously attached to rules are moved to `historical_source_claim`
  and explicitly labelled as unconfirmed; `source_section` keeps only the topic.
- Every rule lacking evidence (evidence_reference + verified_by + verified_on) is set to
  `provisional` (if it is a plausible published/design value) or `unverified`.
- Each rule is classified as published_standard / design_recommendation / internal_heuristic.

Run:  python scripts/audit_ergonomic_provenance.py
"""
import json
import os
import re
import sys

DATA = os.path.join(
    os.path.dirname(__file__), "..", "app", "components", "esai_engine", "data", "ergonomic_rules.json"
)

PAGE_RE = re.compile(r"\s*\(p+\.\s*\d+[^)]*\)")

INTERNAL_HEURISTICS = {
    "TV_VIEWING_DISTANCE_MIN",
    "BEDSIDE_SOCKET_REACH_HEURISTIC",
    "CUSTOM_EXPERIMENTAL_CLEARANCE",
}

NOTE_NEUFERT = (
    "Value and topic are attributed to Neufert 'Architects' Data'. Licensed source material was "
    "not available during the Phase 3 audit, so the page/section reference and numeric value "
    "could not be confirmed. Treated as an advisory design heuristic until verified against the "
    "physical edition by a qualified reviewer."
)
NOTE_ADA = (
    "Attributed to the 2010 ADA Standards for Accessible Design. The source document was not "
    "consulted during the Phase 3 audit; the value must be confirmed against the official text and "
    "the applicable local accessibility regulation before use as a mandatory constraint."
)
NOTE_HEURISTIC = (
    "Internal ArchAI heuristic. Not derived from a published standard; must never be presented "
    "as a regulatory or Neufert requirement."
)


def audit(rule: dict) -> dict:
    r = dict(rule)
    rid = r["id"]
    section = r.get("source_section") or ""
    title = r.get("source_title") or ""

    page_match = PAGE_RE.search(section)
    if page_match:
        r.setdefault(
            "historical_source_claim",
            f"Previously cited as '{section}' (UNCONFIRMED - not verified against licensed source).",
        )
        r["source_section"] = PAGE_RE.sub("", section).strip() or None

    if rid in INTERNAL_HEURISTICS:
        r["rule_class"] = "internal_heuristic"
        r["verification_status"] = "unverified" if rid == "CUSTOM_EXPERIMENTAL_CLEARANCE" else "provisional"
        r["verification_notes"] = NOTE_HEURISTIC
        if r.get("priority") == "hard":
            r["priority"] = "soft"
    elif "ADA" in title or "Accessible" in title or "Section 403" in section:
        r["rule_class"] = "published_standard"
        r["verification_status"] = "provisional"
        r["verification_notes"] = NOTE_ADA
    else:
        r["rule_class"] = "design_recommendation"
        r["verification_status"] = "provisional"
        r["verification_notes"] = NOTE_NEUFERT

    # Evidence fields are intentionally left empty: no evidence was produced in this audit.
    for k in ("evidence_reference", "verified_by", "verified_on"):
        r.setdefault(k, None)
    r.setdefault("units", "m")
    r.setdefault("category", "clearance")
    return r


def main() -> int:
    path = os.path.abspath(DATA)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["rules"] = [audit(r) for r in data.get("rules", [])]
    data["provenance_audit"] = {
        "phase": "phase3",
        "licensed_neufert_available": False,
        "policy": (
            "No rule may be 'verified' without evidence_reference, verified_by and verified_on. "
            "The runtime loader enforces this and demotes unsupported claims to 'provisional'."
        ),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    counts = {}
    for r in data["rules"]:
        counts[r["verification_status"]] = counts.get(r["verification_status"], 0) + 1
    print(f"Audited {len(data['rules'])} rules -> {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
