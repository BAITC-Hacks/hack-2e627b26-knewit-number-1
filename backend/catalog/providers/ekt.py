from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import logging
import random
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.parse import urlsplit

from catalog.availability import calculate_availability
from catalog.errors import CatalogConfigurationError, CatalogError, CatalogTimeoutError, CatalogTransportError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EktCatalogProvider:
    base_url: str
    username: str
    password: str
    connect_timeout: float
    read_timeout: float
    sellable_store_ids: tuple[int, ...]
    availability_rule_version: str
    asset_allowed_hosts: tuple[str, ...] = ("ekt.kz",)
    deadline_seconds: float = 5.0
    max_retries: int = 2
    retry_jitter_seconds: float = 0.1
    max_response_bytes: int = 5_000_000
    data_source: str = "ekt"

    def __post_init__(self) -> None:
        if not 0 <= self.max_retries <= 2:
            raise CatalogConfigurationError("EKT max_retries must be between 0 and 2")
        if self.deadline_seconds <= 0:
            raise CatalogConfigurationError("EKT deadline_seconds must be positive")
        if self.retry_jitter_seconds < 0:
            raise CatalogConfigurationError("EKT retry_jitter_seconds cannot be negative")
        self.asset_allowed_hosts = tuple(host.casefold().rstrip(".") for host in self.asset_allowed_hosts if host)

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

    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CatalogTimeoutError("EKT API request deadline exceeded")
        return remaining

    def _request_once(
        self, path: str, params: dict[str, Any], deadline: float | None = None
    ) -> dict[str, Any]:
        if not self.username or not self.password:
            raise CatalogConfigurationError("EKT API credentials are not configured")
        host, port, base_path = self._origin()
        query = urlencode(params)
        target = f"{base_path}/{path}" + (f"?{query}" if query else "")
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        connect_timeout = min(self.connect_timeout, self._remaining(deadline) or self.connect_timeout)
        connection = http.client.HTTPSConnection(host, port=port, timeout=connect_timeout)
        try:
            connection.connect()
            if connection.sock is not None:
                read_timeout = min(self.read_timeout, self._remaining(deadline) or self.read_timeout)
                connection.sock.settimeout(read_timeout)
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
                if response.status in (401, 403):
                    logger.critical("EKT API authorization failure: status=%s path=%s", response.status, path)
                    code = "upstream_unauthorized" if response.status == 401 else "upstream_forbidden"
                elif response.status == 404:
                    code = "product_unavailable"
                elif response.status == 429:
                    code = "rate_limited"
                else:
                    code = "ekt_api_error"
                raise CatalogError(
                    response.status,
                    code,
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
        deadline = time.monotonic() + self.deadline_seconds
        for attempt in range(self.max_retries + 1):
            try:
                return self._request_once(path, params, deadline)
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
                backoff = retry_after if retry_after > 0 else 0.1 * (2**attempt)
                jitter = random.uniform(0, self.retry_jitter_seconds)
                delay = min(2.0, backoff + jitter)
                remaining = self._remaining(deadline)
                if remaining is not None and delay >= remaining:
                    raise CatalogTimeoutError("EKT API retry deadline exceeded") from exc
                time.sleep(delay)
        raise CatalogTransportError()

    def _sanitize_external_urls(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._sanitize_external_urls(item) for item in value]
        if isinstance(value, dict):
            return {key: self._sanitize_external_urls(item) for key, item in value.items()}
        if not isinstance(value, str) or not value.casefold().startswith(("https://", "http://")):
            return value

        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        try:
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme.casefold() != "https"
            or not hostname
            or parsed.username
            or parsed.password
            or port not in (None, 443)
            or hostname not in self.asset_allowed_hosts
        ):
            return None
        try:
            addresses = {
                info[4][0]
                for info in socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
            }
        except OSError:
            return None
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return None
        return value

    def _mark_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["data_source"] = "ekt"
        candidates = payload.get("items")
        if candidates is None:
            candidates = []
        if not isinstance(candidates, list):
            raise CatalogTransportError("EKT API returned an invalid items field")
        for item in candidates:
            if isinstance(item, dict):
                sanitized = self._sanitize_external_urls(item)
                item.clear()
                item.update(sanitized)
                item["data_source"] = "ekt"
                if isinstance(item.get("id"), int):
                    item["url_api_detail"] = f"/api/products/detail?id={item['id']}"
        if isinstance(payload.get("id"), int):
            sanitized = self._sanitize_external_urls(payload)
            payload.clear()
            payload.update(sanitized)
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
