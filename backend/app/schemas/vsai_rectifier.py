from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VsaiRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    master_json: dict[str, Any] | None = Field(
        default=None,
        description="Optional centralized Master JSON. Baseline sections are merged without replacing later-component data.",
    )
