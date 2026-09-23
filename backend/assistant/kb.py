from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StaticKnowledgeEntry:
    language: str
    text: str
    reviewed_by: str | None
    reviewed_at: datetime | None


def publishable_static_answer(entry: StaticKnowledgeEntry | None) -> str | None:
    """Return static copy only after a named human review.

    Kazakh customer-facing KB copy must enter the system through this gate.  An
    untranslated or machine-translated draft is intentionally indistinguishable
    from absent information to callers.
    """

    if entry is None or not entry.text.strip():
        return None
    if not entry.reviewed_by or entry.reviewed_at is None:
        return None
    return entry.text
