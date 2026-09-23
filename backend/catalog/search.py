from __future__ import annotations

import json
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from django.conf import settings

from config.observability import set_cache_hit


class SearchIndexError(Exception):
    pass


_cache_lock = threading.Lock()
_cache_key: tuple[str, int, int] | None = None
_cache_items: tuple[dict[str, Any], ...] = ()
_word_pattern = re.compile(r"[\w]+", re.UNICODE)
_number_unit_pattern = re.compile(r"\d+(?:[.,]\d+)?\s*(?:а|a|в|v|ка|кa|квт|kw|вт|w|ма|мм|м|гц|hz|ip\s*\d+)", re.IGNORECASE)
_stop_words = {
    "и", "или", "для", "на", "с", "со", "по", "в", "во", "из", "от", "до", "не",
    "нужен", "нужна", "нужно", "требуется", "ищу", "подберите", "товар", "товары",
    "обязательно", "желательно", "желательная", "желательный", "предпочтительно",
    "можно", "хочу", "мне", "который", "которая", "которые",
}
_desired_markers = {"желательно", "желательная", "желательный", "предпочтительно", "можно"}


def clear_index_cache() -> None:
    global _cache_key, _cache_items
    with _cache_lock:
        _cache_key = None
        _cache_items = ()


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(_word_pattern.findall(normalized))


def _compact(value: Any) -> str:
    return re.sub(r"[^\w]+", "", _normalize(value), flags=re.UNICODE)


def _load_items(index_path: Path) -> tuple[dict[str, Any], ...]:
    global _cache_key, _cache_items
    try:
        stat = index_path.stat()
    except OSError as exc:
        raise SearchIndexError("catalog index is not available") from exc
    key = (str(index_path.resolve()), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if key == _cache_key:
            set_cache_hit(True)
            return _cache_items
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SearchIndexError("catalog index cannot be read") from exc
        index_source = payload.get("data_source") if isinstance(payload, dict) else None
        if settings.CATALOG_PROVIDER == "ekt" and index_source == "fixture":
            raise SearchIndexError("live catalog index has not been synchronized")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise SearchIndexError("catalog index has an invalid items array")
        valid_items = tuple(item for item in items if isinstance(item, dict) and isinstance(item.get("id"), int))
        _cache_key = key
        _cache_items = valid_items
        set_cache_hit(False)
        return _cache_items


def _score(query: str, name: str) -> tuple[float, str]:
    if query in name:
        return 1.0, "partial"
    query_tokens = _word_pattern.findall(query)
    name_tokens = _word_pattern.findall(name)
    token_score = max(
        (SequenceMatcher(None, query_token, name_token).ratio() for query_token in query_tokens for name_token in name_tokens),
        default=0.0,
    )
    full_score = SequenceMatcher(None, query, name).ratio()
    score = max(full_score, token_score * 0.9)
    return score, "fuzzy"


def _tokens(value: Any) -> list[str]:
    normalized = _normalize(value)
    numbers = [_compact(match.group(0)) for match in _number_unit_pattern.finditer(normalized)]
    words = [
        token
        for token in _word_pattern.findall(normalized)
        if token not in _stop_words and (len(token) > 1 or token.isdigit())
    ]
    return list(dict.fromkeys(numbers + words))


def _flatten_search_text(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for key, nested in value.items():
            result.extend(_flatten_search_text(key))
            result.extend(_flatten_search_text(nested))
        return result
    if isinstance(value, list):
        result = []
        for nested in value:
            result.extend(_flatten_search_text(nested))
        return result
    return _tokens(value)


def _parse_semantic_query(query: str) -> tuple[list[str], list[str]]:
    normalized = _normalize(query)
    all_tokens = _tokens(normalized)
    desired_tokens: list[str] = []
    for marker in _desired_markers:
        if marker in normalized:
            suffix = normalized.split(marker, 1)[1]
            desired_tokens.extend(_tokens(suffix))
    desired = list(dict.fromkeys(desired_tokens))
    required = [token for token in all_tokens if token not in set(desired)]
    return required, desired


def semantic_search_catalog(query: str, index_path: Path, max_results: int = 5) -> dict[str, Any]:
    required, desired = _parse_semantic_query(query)
    if not required and not desired:
        raise ValueError("semantic search query must contain a purpose or characteristic")
    items = _load_items(index_path)
    candidates: list[tuple[float, int, dict[str, Any], list[str], list[str]]] = []
    for item in items:
        searchable_tokens = set(
            _flatten_search_text(
                {
                    "name": item.get("name"),
                    "article": item.get("article"),
                    "description": item.get("description"),
                    "properties": item.get("properties"),
                }
            )
        )
        matched_required = [token for token in required if token in searchable_tokens]
        matched_desired = [token for token in desired if token in searchable_tokens]
        missing_required = [token for token in required if token not in searchable_tokens]
        required_score = len(matched_required) / len(required) if required else 1.0
        desired_score = len(matched_desired) / len(desired) if desired else 1.0
        score = required_score * 0.75 + desired_score * 0.25
        if score <= 0:
            continue
        candidates.append((score, int(item["id"]), item, matched_required, matched_desired))

    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
    results = []
    for score, _, item, matched_required, matched_desired in candidates[:max_results]:
        matched = matched_required + matched_desired
        missing = [token for token in required if token not in matched_required]
        explanation_parts = []
        if matched_required:
            explanation_parts.append(f"обязательные параметры: {', '.join(matched_required)}")
        if matched_desired:
            explanation_parts.append(f"желательные параметры: {', '.join(matched_desired)}")
        if missing:
            explanation_parts.append(f"не подтверждено: {', '.join(missing)}")
        if not explanation_parts:
            explanation_parts.append("совпадение по назначению или названию")
        results.append(
            dict(
                item,
                match_type="semantic",
                score=round(score, 4),
                explanation="; ".join(explanation_parts),
                matched_parameters=matched,
                missing_required_parameters=missing,
            )
        )
    return {
        "query": query,
        "mode": "semantic",
        "parsed": {"required": required, "desired": desired},
        "results": results,
        "count": len(results),
    }


def search_catalog(query: str, index_path: Path, max_results: int = 5) -> dict[str, Any]:
    normalized_query = _normalize(query)
    if not normalized_query:
        raise ValueError("search query must not be empty")
    items = _load_items(index_path)
    compact_query = _compact(query)

    exact: list[dict[str, Any]] = []
    if normalized_query.isdecimal():
        numeric_id = int(normalized_query)
        exact.extend(item for item in items if item.get("id") == numeric_id)
    if not exact:
        exact.extend(
            item
            for item in items
            if compact_query
            and compact_query in {_compact(item.get("article")), _compact(item.get("name"))}
        )
    if exact:
        return {
            "query": query,
            "mode": "exact",
            "results": [dict(item, match_type="exact", score=1.0) for item in exact[:1]],
            "count": 1,
        }

    candidates: list[tuple[float, int, str, dict[str, Any]]] = []
    for item in items:
        name = _normalize(item.get("name"))
        if not name:
            continue
        score, match_type = _score(normalized_query, name)
        if score >= 0.25:
            candidates.append((score, int(item["id"]), match_type, item))
    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
    results = [dict(item, match_type=match_type, score=round(score, 4)) for score, _, match_type, item in candidates[:max_results]]
    return {"query": query, "mode": "fuzzy", "results": results, "count": len(results)}
