from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping


def build_updated_master(master: Mapping[str, Any], exterior: Mapping[str, Any], run_id: str,
                         outcome: str, version: str = "1.0", generation_mode: str = "baseline",
                         source_revision: int | None = None, model_version: str | None = None) -> dict[str, Any]:
    """Copy the existing document and replace only ELIA-owned fields."""
    updated = deepcopy(dict(master))
    if outcome == "valid":
        updated["exterior_landscape"] = deepcopy(dict(exterior))
    processing = updated.setdefault("processing", {})
    if not isinstance(processing, dict):
        processing = {}
        updated["processing"] = processing
    processing["elia_engine"] = {
        "status": "completed" if outcome == "valid" else "infeasible",
        "run_id": run_id, "version": version, "schema_version": exterior.get("schema_version", version),
        "generation_mode": generation_mode, "model_version": model_version,
        "source_revision": source_revision,
        "started_at": exterior.get("started_at"),
        "completed_at": datetime.now(timezone.utc).isoformat(), "outcome": outcome,
    }
    return updated


def build_processing_master(master: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    updated = deepcopy(dict(master))
    processing = updated.setdefault("processing", {})
    if not isinstance(processing, dict):
        processing = {}
        updated["processing"] = processing
    processing["elia_engine"] = deepcopy(dict(metadata))
    return updated
