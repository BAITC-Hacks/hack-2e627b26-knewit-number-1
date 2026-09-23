from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from catalog.availability import calculate_availability
from catalog.errors import CatalogError, CatalogTimeoutError
from catalog.normalization import normalize_product


FIXTURE_DATASET_VERSION = "catalog-fixture-v1"
FIXTURE_SEED = 20260923
FIXTURE_PRODUCT_COUNT = 120

GROUPS = (
    ("Автоматический выключатель ВА47-29", "автомат", "IEK", "poles", ("1P", "2P", "3P")),
    ("Кабель ВВГнг-LS", "кабель", "Казцентрэлектропровод", "section", ("3x1.5", "3x2.5", "5x2.5")),
    ("Светильник LED ДПО", "светильник", "MEGALIGHT", "power", ("18W", "24W", "36W")),
    ("Розетка с заземлением", "розетка", "Legrand", "color", ("белая", "бежевая", "графит")),
    ("Контактор КМИ", "контактор", "IEK", "coil_voltage", ("24V", "220V", "380V")),
    ("Дифференциальный автомат АВДТ", "дифавтомат", "EKF", "leakage_current", ("10mA", "30mA", "100mA")),
    ("Коробка распределительная", "коробка", "HEGEL", "ip_rating", ("IP44", "IP55", "IP65")),
    ("Лоток кабельный перфорированный", "лоток", "DKC", "width", ("50mm", "100mm", "200mm")),
    ("Реле контроля напряжения", "реле", "DigiTOP", "phases", ("1-фазное", "3-фазное", "универсальное")),
    ("Мультиметр цифровой", "мультиметр", "UNI-T", "precision", ("basic", "true-rms", "pro")),
    ("Щит распределительный навесной", "щит", "Schneider Electric", "modules", ("12", "24", "36")),
    ("Клемма винтовая на DIN-рейку", "клемма", "Phoenix Contact", "section", ("2.5mm2", "4mm2", "6mm2")),
)


def _stores_for(index: int) -> list[dict[str, Any]]:
    mode = index % 6
    if mode == 0:
        return [
            {"id": 1, "name": "Алматы (ул. Рыскулова)", "quantity": 8 + index % 5},
            {"id": 900, "name": "Брак", "quantity": 2},
        ]
    if mode == 1:
        return [
            {"id": 1, "name": "Алматы (ул. Рыскулова)", "quantity": 0},
            {"id": 2, "name": "Астана (ул. Пушкина)", "quantity": 0},
        ]
    if mode == 2:
        return [
            {"id": 900, "name": "Брак", "quantity": 4},
            {"id": 901, "name": "перемещение", "quantity": 7},
        ]
    if mode == 3:
        return [{"id": 777, "name": "Новый склад — классификация не утверждена", "quantity": 9}]
    if mode == 4:
        return [
            {"id": 2, "name": "Астана (ул. Пушкина)", "quantity": 3},
            {"id": 3, "name": "Шымкент (ул. Байдукова)", "quantity": 6},
        ]
    return [
        {"id": 3, "name": "Шымкент (ул. Байдукова)", "quantity": 1},
        {"id": 901, "name": "перемещение", "quantity": 12},
    ]


def _build_products() -> tuple[dict[str, Any], ...]:
    products: list[dict[str, Any]] = []
    for index in range(FIXTURE_PRODUCT_COUNT):
        group_index = index // 10
        variant_index = index % 10
        title, category, brand, critical_key, critical_values = GROUPS[group_index]
        critical_value = critical_values[variant_index % len(critical_values)]
        product_id = 900001 + index
        amperage = 6 + (variant_index * 2)
        article = f"ДЕМО-{group_index + 1:02d}-{variant_index + 1:03d}"
        name = f"{title} {critical_value} {amperage}A {brand}"
        stores = _stores_for(index)
        aliases = [title.casefold()]
        if group_index == 0:
            aliases.extend(["автомтический выключатель", "автомат выклчатель"])
        elif group_index == 2:
            aliases.extend(["светелник led", "лед светильнк"])
        properties = {
            "TORGOVAYA_MARKA": brand,
            "CATEGORY": category,
            "ANALOG_GROUP": f"AG-{group_index + 1:02d}",
            "RATED_CURRENT": f"{amperage}A",
            critical_key.upper(): critical_value,
            "SEARCH_ALIASES": aliases,
            "FIXTURE_NOTE": "Синтетические данные для демонстрации, не реальные цена и остаток",
        }
        seeded_offset = int(
            hashlib.sha256(f"{FIXTURE_SEED}:{index}".encode()).hexdigest()[:8], 16
        ) % 101
        price = 850 + group_index * 1775 + variant_index * 135 + seeded_offset
        products.append(
            {
                "id": product_id,
                "name": name,
                "article": article,
                "description": (
                    f"Демонстрационный товар категории «{category}». "
                    f"Критичная характеристика {critical_key}={critical_value}."
                ),
                "price": price,
                "quantity": sum(store["quantity"] for store in stores),
                "stores": stores,
                "image": "/api/fixtures/product-placeholder.svg",
                "url": f"/demo/catalog/{product_id}/",
                "url_api_detail": f"/api/products/detail?id={product_id}",
                "offers": [],
                "properties": properties,
                "data_source": "fixture",
                "fixture_version": FIXTURE_DATASET_VERSION,
            }
        )
    return tuple(products)


PRODUCTS = _build_products()
PRODUCTS_BY_ID = {product["id"]: product for product in PRODUCTS}


@dataclass(slots=True)
class FixtureCatalogProvider:
    sellable_store_ids: tuple[int, ...]
    availability_rule_version: str
    timeout_seconds: float
    default_currency: str | None = "KZT"
    data_source: str = "fixture"

    def _apply_scenario(self, fixture_case: str | None) -> None:
        if fixture_case in (None, "", "missing_field", "null_field"):
            return
        if fixture_case == "timeout":
            time.sleep(max(0, self.timeout_seconds))
            raise CatalogTimeoutError("Synthetic catalog timeout")
        scenarios = {
            "unauthorized": CatalogError(
                401,
                "unauthorized",
                "Synthetic authentication failure",
                {"WWW-Authenticate": 'Basic realm="Fixture API"'},
            ),
            "not_found": CatalogError(404, "not_found", "Synthetic resource not found"),
            "rate_limited": CatalogError(
                429,
                "rate_limited",
                "Synthetic rate limit exceeded",
                {"Retry-After": "2"},
            ),
            "server_error": CatalogError(503, "upstream_error", "Synthetic upstream failure"),
        }
        if fixture_case not in scenarios:
            raise CatalogError(400, "unknown_fixture_case", f"Unknown fixture_case: {fixture_case}")
        raise scenarios[fixture_case]

    def _mutate_for_data_scenario(self, payload: dict[str, Any], fixture_case: str | None) -> None:
        if fixture_case == "missing_field":
            if "items" in payload:
                if payload["items"]:
                    payload["items"][0].pop("name", None)
            else:
                payload.pop("description", None)
        elif fixture_case == "null_field":
            if "items" in payload:
                if payload["items"]:
                    payload["items"][0]["price"] = None
            else:
                payload["price"] = None

    def list_products(
        self, page: int, per_page: int, fixture_case: str | None = None
    ) -> dict[str, Any]:
        self._apply_scenario(fixture_case)
        start = (page - 1) * per_page
        items = []
        for source in PRODUCTS[start : start + per_page]:
            item = copy.deepcopy(source)
            for detail_only in ("description", "quantity", "stores", "properties"):
                item.pop(detail_only)
            items.append(item)
        payload = {
            "page": page,
            "per_page": per_page,
            "count": len(items),
            "items": items,
            "data_source": "fixture",
            "fixture_version": FIXTURE_DATASET_VERSION,
            "fixture_seed": FIXTURE_SEED,
        }
        self._mutate_for_data_scenario(payload, fixture_case)
        return payload

    def get_product(self, product_id: int, fixture_case: str | None = None) -> dict[str, Any]:
        self._apply_scenario(fixture_case)
        if product_id not in PRODUCTS_BY_ID:
            raise CatalogError(404, "product_not_found", f"Product {product_id} was not found")
        payload = copy.deepcopy(PRODUCTS_BY_ID[product_id])
        fetched_at = datetime.now(timezone.utc)
        payload["availability"] = calculate_availability(
            payload["stores"],
            payload["quantity"],
            self.sellable_store_ids,
            self.availability_rule_version,
            observed_at=fetched_at,
        )
        self._mutate_for_data_scenario(payload, fixture_case)
        payload["normalized"] = normalize_product(
            payload,
            default_currency=self.default_currency,
            availability=payload["availability"],
            fetched_at=fetched_at,
        )
        return payload
