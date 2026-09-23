from __future__ import annotations

import base64
import http.client
import json
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.parse import urlsplit

from catalog.availability import calculate_availability
from catalog.errors import CatalogConfigurationError, CatalogError, CatalogTimeoutError, CatalogTransportError


@dataclass(slots=True)
class EktCatalogProvider:
    base_url: str
    username: str
    password: str
    connect_timeout: float
    read_timeout: float
    sellable_store_ids: tuple[int, ...]
    availability_rule_version: str
    max_retries: int = 2
    max_response_bytes: int = 5_000_000
    data_source: str = "ekt"

    def _origin(self) -> tuple[str, int | None, str]:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise CatalogConfigurationError("EKT_API_BASE_URL must be a credential-free HTTPS URL")
        return parsed.hostname, parsed.port, parsed.path.rstrip("/")

    def _request_once(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.username or not self.password:
            raise CatalogConfigurationError("EKT API credentials are not configured")
        host, port, base_path = self._origin()
        query = urlencode(params)
        target = f"{base_path}/{path}" + (f"?{query}" if query else "")
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        connection = http.client.HTTPSConnection(host, port=port, timeout=self.connect_timeout)
        try:
            connection.connect()
            if connection.sock is not None:
                connection.sock.settimeout(self.read_timeout)
            connection.request(
                "GET",
                target,
                headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
            )
            response = connection.getresponse()
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise CatalogTransportError("EKT API response exceeded the configured size limit")
            if 300 <= response.status < 400:
                raise CatalogTransportError("EKT API redirect was rejected")
            if response.status >= 400:
                headers = {}
                if retry_after := response.getheader("Retry-After"):
                    headers["Retry-After"] = retry_after
                if challenge := response.getheader("WWW-Authenticate"):
                    headers["WWW-Authenticate"] = challenge
                raise CatalogError(
                    response.status,
                    "ekt_api_error",
                    f"EKT API returned HTTP {response.status}",
                    headers,
                )
            content_type = response.getheader("Content-Type", "")
            if "application/json" not in content_type.casefold():
                raise CatalogTransportError("EKT API returned a non-JSON response")
            payload = json.loads(body.decode("utf-8"))
        except CatalogError:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise CatalogTimeoutError("EKT API timed out") from exc
        except (OSError, http.client.HTTPException, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogTransportError() from exc
        finally:
            connection.close()
        if not isinstance(payload, dict):
            raise CatalogTransportError("EKT API returned an invalid JSON shape")
        return payload

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                return self._request_once(path, params)
            except CatalogConfigurationError:
                raise
            except CatalogError as exc:
                retryable = isinstance(exc, (CatalogTimeoutError, CatalogTransportError)) or (
                    exc.status_code == 429 or exc.status_code >= 500
                )
                if not retryable or attempt >= self.max_retries:
                    raise
                try:
                    retry_after = float(exc.headers.get("Retry-After", ""))
                except ValueError:
                    retry_after = 0.0
                delay = min(2.0, retry_after if retry_after > 0 else 0.1 * (2**attempt))
                time.sleep(delay)
        raise CatalogTransportError()

    @staticmethod
    def _mark_source(payload: dict[str, Any]) -> dict[str, Any]:
        payload["data_source"] = "ekt"
        candidates = payload.get("items", [])
        if not isinstance(candidates, list):
            raise CatalogTransportError("EKT API returned an invalid items field")
        for item in candidates:
            if isinstance(item, dict):
                item["data_source"] = "ekt"
                if isinstance(item.get("id"), int):
                    item["url_api_detail"] = f"/api/products/detail?id={item['id']}"
        if isinstance(payload.get("id"), int):
            payload["url_api_detail"] = f"/api/products/detail?id={payload['id']}"
        return payload

    def list_products(
        self, page: int, per_page: int, fixture_case: str | None = None
    ) -> dict[str, Any]:
        del fixture_case
        return self._mark_source(self._request("products", {"page": page, "per_page": per_page}))

    def get_product(self, product_id: int, fixture_case: str | None = None) -> dict[str, Any]:
        del fixture_case
        payload = self._mark_source(self._request("products/detail", {"id": product_id}))
        payload["availability"] = calculate_availability(
            payload.get("stores"),
            payload.get("quantity"),
            self.sellable_store_ids,
            self.availability_rule_version,
        )
        return payload
