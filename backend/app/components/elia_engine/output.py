from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping


def build_updated_master(master: Mapping[str, Any], exterior: Mapping[str, Any], run_id: str,
                         outcome: str, version: str = "1.0") -> dict[str, Any]:
    """Copy the existing document and replace only ELIA-owned fields."""
    updated = deepcopy(dict(master))
    updated["exterior_landscape"] = deepcopy(dict(exterior))
    processing = updated.setdefault("processing", {})
    if not isinstance(processing, dict):
        processing = {}
        updated["processing"] = processing
    processing["elia_engine"] = {
        "status": "completed", "run_id": run_id, "version": version,
        "started_at": exterior.get("started_at"),
        "completed_at": datetime.now(timezone.utc).isoformat(), "outcome": outcome,
    }
    return updated
