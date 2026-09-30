"""Read-only asynchronous FHIR client for the OAH sandbox.

Guarantees (tested in tests/unit/test_fhir_client.py):
- only GET requests, plus POST exclusively to `$validate` (which never persists) — anything else raises;
- search paging follows `next` links but never leaves the configured host;
- retries with exponential backoff on network errors, 429 and 5xx (honouring Retry-After);
- a polite delay between requests;
- raw response bodies are cached in SQLite and returned verbatim for evidence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from datadoctor.ingestion.cache import HttpCache

log = logging.getLogger(__name__)


class ReadOnlyViolation(RuntimeError):
    """Raised if code tries to issue a request that could modify the sandbox."""


class SandboxUnavailable(RuntimeError):
    pass


@dataclass
class FetchRecord:
    url: str
    status: int
    latency_s: float
    from_cache: bool
    fetched_at: float


class FhirClient:
    def __init__(
        self,
        base_url: str,
        cache: HttpCache | None = None,
        *,
        delay_s: float = 0.25,
        timeout_s: float = 60.0,
        retries: int = 4,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._host = urlparse(self.base_url).netloc
        self._cache = cache
        self._delay = delay_s
        self._retries = retries
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            transport=transport,
            headers={"Accept": "application/fhir+json", "User-Agent": "oah-data-doctor/0.1 (read-only auditor)"},
            follow_redirects=False,
        )
        self._last_request = 0.0
        self.log: list[FetchRecord] = []

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> FhirClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- guards -------------------------------------------------------------------------------------
    def _url(self, path_or_url: str) -> str:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        if urlparse(url).netloc != self._host:
            raise ReadOnlyViolation(f"refusing to follow a link to another host: {url}")
        return url

    @staticmethod
    def check_method(method: str, url: str) -> None:
        method = method.upper()
        if method == "GET":
            return
        if method == "POST" and urlparse(url).path.rstrip("/").endswith("$validate"):
            return
        raise ReadOnlyViolation(f"{method} {url} is not allowed: Data Doctor is read-only (GET and $validate only)")

    # -- transport ----------------------------------------------------------------------------------
    async def _polite_wait(self) -> None:
        wait = self._delay - (time.monotonic() - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def request(self, method: str, path_or_url: str, *, body: Any = None, use_cache: bool = True) -> tuple[int, str]:
        url = self._url(path_or_url)
        self.check_method(method, url)
        cacheable = method.upper() == "GET" and self._cache is not None and use_cache
        if cacheable and self._cache is not None:
            hit = self._cache.get(url)
            if hit is not None:
                self.log.append(FetchRecord(url, hit[0], 0.0, True, hit[2]))
                return hit[0], hit[1]

        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self._retries:
            await self._polite_wait()
            t0 = time.monotonic()
            try:
                headers = {"Cache-Control": "no-cache"}
                if body is not None:
                    headers["Content-Type"] = "application/fhir+json"
                resp = await self._client.request(method.upper(), url, headers=headers,
                                                  content=json.dumps(body) if body is not None else None)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                attempt += 1
                await asyncio.sleep(min(2 ** attempt * 0.5, 10))
                continue
            latency = time.monotonic() - t0
            if resp.status_code == 429 or resp.status_code >= 500:
                attempt += 1
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt * 0.5, 10)
                log.warning("retrying %s after HTTP %s (attempt %s)", url, resp.status_code, attempt)
                last_exc = SandboxUnavailable(f"HTTP {resp.status_code} from {url}")
                await asyncio.sleep(delay)
                continue
            text = resp.text
            self.log.append(FetchRecord(url, resp.status_code, latency, False, time.time()))
            if cacheable and self._cache is not None and resp.status_code == 200:
                self._cache.put(url, resp.status_code, text)
            return resp.status_code, text
        raise SandboxUnavailable(f"giving up on {url}: {last_exc}")

    async def get_json(self, path_or_url: str, *, use_cache: bool = True) -> dict[str, Any]:
        status, text = await self.request("GET", path_or_url, use_cache=use_cache)
        if status != 200:
            raise SandboxUnavailable(f"HTTP {status} for {path_or_url}: {text[:200]}")
        data: dict[str, Any] = json.loads(text)
        return data

    # -- FHIR operations ----------------------------------------------------------------------------
    async def capability_statement(self) -> dict[str, Any]:
        return await self.get_json("metadata", use_cache=False)

    async def search_all(self, resource_type: str, page_size: int = 200, *, use_cache: bool = True) -> list[dict[str, Any]]:
        """Fetch every resource of a type by following Bundle.link[next] (HAPI `_getpages` paging)."""
        url: str | None = f"{resource_type}?_count={page_size}"
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        while url:
            bundle = await self.get_json(url, use_cache=use_cache)
            for entry in bundle.get("entry", []):
                res = entry.get("resource")
                # Search filters on this server are not always honoured (DISCOVERY.md D2) — filter client-side.
                if res and res.get("resourceType") == resource_type and res.get("id") not in seen:
                    seen.add(res["id"])
                    out.append(res)
            url = next((link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"), None)
        return out

    async def validate_instance(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """Server-side `$validate` for an existing instance (GET form, read-only)."""
        return await self.get_json(f"{resource_type}/{resource_id}/$validate", use_cache=True)
