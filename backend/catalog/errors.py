from dataclasses import dataclass, field


@dataclass(slots=True)
class CatalogError(Exception):
    status_code: int
    code: str
    message: str
    headers: dict[str, str] = field(default_factory=dict)


class CatalogConfigurationError(CatalogError):
    def __init__(self, message: str) -> None:
        super().__init__(500, "catalog_configuration_error", message)


class CatalogTimeoutError(CatalogError):
    def __init__(self, message: str = "Catalog provider timed out") -> None:
        super().__init__(504, "catalog_timeout", message)


class CatalogTransportError(CatalogError):
    def __init__(self, message: str = "Catalog provider is unavailable") -> None:
        super().__init__(502, "catalog_unavailable", message)
