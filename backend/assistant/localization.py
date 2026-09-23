from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


SUPPORTED_LANGUAGES = frozenset({"ru", "kk"})

# The mapping is an input aid for the future catalog-search service.  It maps a
# buyer's Kazakh need to a catalog-neutral/Russian lookup term; it does not
# translate articles, brands, or official product titles.
_KAZAKH_SEARCH_TERMS: tuple[tuple[str, str], ...] = (
    ("автоматты ажыратқыш", "автоматический выключатель"),
    ("қорғаныс автоматы", "автоматический выключатель"),
    ("ажыратқыш", "выключатель"),
    ("автомат", "автоматический выключатель"),
    ("кабель", "кабель"),
    ("сым", "провод"),
    ("өткізгіш", "провод"),
    ("жарық", "светильник"),
    ("шам", "светильник"),
    ("балама", "аналог"),
    ("аналог", "аналог"),
    ("қоймада", "наличие"),
    ("бар ма", "наличие"),
)
_KAZAKH_SIGNALS = frozenset(
    {
        "қажет",
        "керек",
        "тауар",
        "баға",
        "бағасы",
        "жеткізу",
        "себет",
        "қосу",
        "бар",
        "барма",
        "қойма",
        "балама",
        "қалай",
    }
)
_WORD_RE = re.compile(r"[\w\-]+", re.UNICODE)
_ARTICLE_RE = re.compile(r"(?<!\w)[a-zа-яё0-9][a-zа-яё0-9_\-]{2,}(?!\w)", re.IGNORECASE)


def normalize_language(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("language must be a string")
    language = value.strip().casefold()
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("language must be one of: ru, kk")
    return language


def is_substantive(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    return len("".join(_WORD_RE.findall(text))) >= 2


def detect_language(text: Any, *, fallback: str = "ru") -> str:
    """Detect only the supported locales; unknown/ambiguous input keeps RU."""

    fallback = normalize_language(fallback)
    if not is_substantive(text):
        return fallback
    normalized = str(text).casefold()
    if any(character in normalized for character in "әғқңөұүһі"):
        return "kk"
    words = {word.replace("-", "") for word in _WORD_RE.findall(normalized)}
    if words.intersection(_KAZAKH_SIGNALS):
        return "kk"
    return "ru"


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def catalog_search_context(text: Any, language: str) -> dict[str, Any]:
    """Return locale-independent terms for a catalog search adapter.

    The original request is retained.  A search adapter must use the returned
    terms against its own index and must still obtain prices/stock from the same
    catalog data source used by Russian requests.
    """

    language = normalize_language(language)
    original = text.strip() if isinstance(text, str) else ""
    canonical_terms: list[str] = []
    if language == "kk":
        lowered = original.casefold()
        canonical_terms.extend(
            canonical for phrase, canonical in _KAZAKH_SEARCH_TERMS if phrase in lowered
        )
    # Preserve likely article/SKU tokens verbatim.  This prevents accidental
    # translation of identifiers such as 027228 or DRX250.
    canonical_terms.extend(_ARTICLE_RE.findall(original))
    return {
        "original_query": original,
        "language": language,
        "canonical_terms": _ordered_unique(canonical_terms),
        "fact_source_policy": "same_catalog_source_for_all_languages",
    }


def localized_message(language: str, key: str) -> str:
    language = normalize_language(language)
    messages = {
        "ru": {
            "llm_unavailable": "Сейчас не удалось сформировать ответ. Попробуйте ещё раз позже.",
            "cart_summary": "Предыдущее предложение корзины отменено из-за смены языка. Подтвердите новую заявку явно.",
            "information_not_found": "Информация не найдена.",
        },
        "kk": {
            "llm_unavailable": "Жауапты қазір қалыптастыру мүмкін болмады. Кейінірек қайталап көріңіз.",
            "cart_summary": "Тіл өзгергендіктен алдыңғы себет ұсынысы жойылды. Жаңа сұрауды нақты растаңыз.",
            "information_not_found": "Ақпарат табылмады.",
        },
    }
    return messages[language][key]
