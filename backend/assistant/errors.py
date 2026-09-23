from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AssistantApiError(Exception):
    status_code: int
    code: str
    message: str
    extra: dict[str, Any] = field(default_factory=dict)
