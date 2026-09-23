from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import KnowledgeEntry


_WORD_RE = re.compile(r"[\w]+", re.UNICODE)
_PUBLISHED = {KnowledgeEntry.Status.APPROVED, KnowledgeEntry.Status.APPROVED_WITH_QUALIFICATION}


def _tokens(value: Any) -> set[str]:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return {token for token in _WORD_RE.findall(normalized) if len(token) > 2}


def _match_score(query: str, entry: KnowledgeEntry) -> float:
    query_tokens = _tokens(query)
    variants = entry.variants if isinstance(entry.variants, list) else []
    variant_tokens = set().union(*(_tokens(variant) for variant in variants), _tokens(entry.intent))
    if not query_tokens or not variant_tokens:
        return 0.0
    return len(query_tokens & variant_tokens) / len(query_tokens)


def _answer(entry: KnowledgeEntry, language: str) -> str:
    if language == "kk" and entry.answer_kk:
        return entry.answer_kk
    return entry.answer_ru


def _safe_exception(language: str, status: str) -> str:
    if language == "kk":
        if status == KnowledgeEntry.Status.CONFLICTED:
            return "Дереккөздердегі шарттар бір-біріне қайшы. Дұрыс шартты өзім таңдамаймын — менеджер нақтылайды."
        return "Бұл шарт расталмаған. Нақты ақпарат алу үшін менеджерге қосамын."
    if status == KnowledgeEntry.Status.CONFLICTED:
        return "В источниках указаны разные условия. Я не буду выбирать вариант сам — передам вопрос менеджеру для уточнения."
    return "Условие пока не подтверждено. Передам вопрос менеджеру, чтобы получить точный ответ."


def answer_query(query: str, language: str = "ru", intent: str | None = None) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip() or len(query) > 1200:
        raise ValueError("query must be a non-empty string up to 1200 characters")
    current = list(KnowledgeEntry.objects.filter(is_current=True))
    if intent:
        current = [entry for entry in current if entry.intent == intent]
    ranked = sorted((( _match_score(query, entry), entry) for entry in current), key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 0.25:
        return {"status": "not_found", "answer": None, "manager_required": False, "sources": []}
    best_score = ranked[0][0]
    matches = [entry for score, entry in ranked if score == best_score]
    statuses = {entry.status for entry in matches}
    if KnowledgeEntry.Status.CONFLICTED in statuses:
        return {
            "status": KnowledgeEntry.Status.CONFLICTED,
            "intent": matches[0].intent,
            "answer": _safe_exception(language, KnowledgeEntry.Status.CONFLICTED),
            "manager_required": True,
            "sources": [
                {"source_url": entry.source_url, "answer": _answer(entry, language), "verified_at": entry.verified_at}
                for entry in matches
                if entry.status == KnowledgeEntry.Status.CONFLICTED
            ],
        }
    entry = next((item for item in matches if item.status in _PUBLISHED), matches[0])
    if entry.status == KnowledgeEntry.Status.MISSING:
        return {
            "status": KnowledgeEntry.Status.MISSING,
            "intent": entry.intent,
            "answer": _safe_exception(language, KnowledgeEntry.Status.MISSING),
            "manager_required": True,
            "sources": [{"source_url": entry.source_url, "verified_at": entry.verified_at}],
        }
    return {
        "status": "qualified" if entry.status == KnowledgeEntry.Status.APPROVED_WITH_QUALIFICATION else "approved",
        "intent": entry.intent,
        "answer": _answer(entry, language),
        "manager_required": False,
        "source_url": entry.source_url,
        "verified_at": entry.verified_at,
    }
