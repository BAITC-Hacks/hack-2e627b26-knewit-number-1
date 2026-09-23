from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from catalog.providers.fixture import FIXTURE_DATASET_VERSION, PRODUCTS


SAMPLE_VERSION = "acceptance-sample-v1"
SAMPLE_SIZE = 200
LABEL_COUNTS = {
    "exact_article_or_id": 40,
    "name_or_typo": 50,
    "characteristic": 60,
    "absence_or_analog": 50,
}


@dataclass(frozen=True, slots=True)
class AcceptanceSample:
    case_id: str
    label: str
    query: str
    target_product_id: int | None
    analog_product_id: int | None
    data_version: str = FIXTURE_DATASET_VERSION


def _product(index: int) -> dict[str, Any]:
    return PRODUCTS[index % len(PRODUCTS)]


def _typo(name: str) -> str:
    # A deterministic one-character edit keeps the label reproducible while
    # avoiding a hand-maintained list that can drift from fixture-v1.
    for source, replacement in (("а", "о"), ("е", "и"), ("и", "ы")):
        if source in name.casefold():
            position = name.casefold().index(source)
            return name[:position] + replacement + name[position + 1 :]
    return name + "x"


def _absence_token(index: int) -> str:
    first = chr(ord("a") + (index // 26) % 26)
    second = chr(ord("a") + index % 26)
    return f"zzqvxlmno{first}{second}"


def build_acceptance_sample() -> tuple[AcceptanceSample, ...]:
    rows: list[AcceptanceSample] = []
    for index in range(LABEL_COUNTS["exact_article_or_id"]):
        product = _product(index)
        query = product["article"] if index % 2 == 0 else str(product["id"])
        rows.append(
            AcceptanceSample(
                f"AT-SAMPLE-{len(rows) + 1:03d}",
                "exact_article_or_id",
                query,
                product["id"],
                None,
            )
        )
    for index in range(LABEL_COUNTS["name_or_typo"]):
        product = _product(index + 40)
        rows.append(
            AcceptanceSample(
                f"AT-SAMPLE-{len(rows) + 1:03d}",
                "name_or_typo",
                _typo(product["name"]),
                product["id"],
                None,
            )
        )
    for index in range(LABEL_COUNTS["characteristic"]):
        product = _product(index + 90)
        properties = product.get("properties") or {}
        category = properties.get("CATEGORY") or "товар"
        characteristic = properties.get("RATED_CURRENT") or next(
            (
                value
                for key, value in properties.items()
                if key not in {"CATEGORY", "SEARCH_ALIASES", "FIXTURE_NOTE", "ANALOG_GROUP"}
                and isinstance(value, str)
            ),
            "характеристика",
        )
        rows.append(
            AcceptanceSample(
                f"AT-SAMPLE-{len(rows) + 1:03d}",
                "characteristic",
                f"{category} {characteristic}",
                product["id"],
                None,
            )
        )
    for index in range(LABEL_COUNTS["absence_or_analog"]):
        analog = _product(index + 21)
        rows.append(
            AcceptanceSample(
                f"AT-SAMPLE-{len(rows) + 1:03d}",
                "absence_or_analog",
                _absence_token(index),
                None,
                analog["id"],
            )
        )
    return tuple(rows)


def sample_counts(rows: Iterable[AcceptanceSample] | None = None) -> dict[str, int]:
    values = rows if rows is not None else build_acceptance_sample()
    counts = {label: 0 for label in LABEL_COUNTS}
    for row in values:
        counts[row.label] = counts.get(row.label, 0) + 1
    return counts
