from __future__ import annotations

import json
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


class SearchIndexError(Exception):
    pass


_cache_lock = threading.Lock()
_cache_key: tuple[str, int, int] | None = None
_cache_items: tuple[dict[str, Any], ...] = ()
_word_pattern = re.compile(r"[\w]+", re.UNICODE)


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
            return _cache_items
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SearchIndexError("catalog index cannot be read") from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise SearchIndexError("catalog index has an invalid items array")
        valid_items = tuple(item for item in items if isinstance(item, dict) and isinstance(item.get("id"), int))
        _cache_key = key
        _cache_items = valid_items
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

