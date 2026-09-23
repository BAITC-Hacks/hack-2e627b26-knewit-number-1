from typing import Any, Protocol


class CatalogProvider(Protocol):
    data_source: str

    def list_products(
        self, page: int, per_page: int, fixture_case: str | None = None
    ) -> dict[str, Any]: ...

    def get_product(self, product_id: int, fixture_case: str | None = None) -> dict[str, Any]: ...
