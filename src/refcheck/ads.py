from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from refcheck.cache import CachedResponse, DiskCache
from refcheck.models import ADSRecord, SearchResponse
from refcheck.trace import TraceWriter


ADS_BASE_URL = "https://api.adsabs.harvard.edu"
SEARCH_PATH = "/v1/search/query"
EXPORT_PATH = "/v1/export/bibtex"
SEARCH_FIELDS = (
    "bibcode,title,author,first_author,year,pub,volume,page,doi,identifier,pubdate"
)
_RATE_HEADERS = {
    "x-ratelimit-limit": "X-RateLimit-Limit",
    "x-ratelimit-remaining": "X-RateLimit-Remaining",
    "x-ratelimit-reset": "X-RateLimit-Reset",
}
T = TypeVar("T")


class ADSAPIError(RuntimeError):
    """Raised when ADS returns an HTTP or response-schema error."""


class RateLimitExhausted(ADSAPIError):
    """Raised before an uncached request would exceed the ADS quota."""


def _rate_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    return {
        canonical: lowered[key]
        for key, canonical in _RATE_HEADERS.items()
        if key in lowered
    }


class ADSClient:
    """Small ADS HTTP client with persistent caching, quota tracking, and tracing."""

    def __init__(
        self,
        *,
        token: str,
        cache: DiskCache,
        trace: TraceWriter,
        http_client: httpx.Client | None = None,
        base_url: str = ADS_BASE_URL,
    ) -> None:
        if not token:
            raise ValueError("ADS token must not be empty")
        self._token = token
        self.cache = cache
        self.trace = trace
        self.trace.register_secret(token)
        self.base_url = base_url.rstrip("/")
        self._http_client = http_client or httpx.Client(timeout=30.0)
        self._owns_http_client = http_client is None
        self._remaining: int | None = None

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def _update_quota(self, headers: dict[str, str]) -> None:
        value = headers.get("X-RateLimit-Remaining")
        if value is None:
            return
        try:
            self._remaining = int(value)
        except ValueError as exc:
            raise ADSAPIError("ADS returned an invalid rate-limit header") from exc

    def _trace_event(
        self,
        *,
        method: str,
        endpoint: str,
        request: object,
        cache_hit: bool,
        status_code: int,
        headers: dict[str, str],
        body: object,
    ) -> None:
        self.trace.write(
            {
                "service": "ads",
                "method": method,
                "endpoint": endpoint,
                "request": request,
                "cache_hit": cache_hit,
                "status_code": status_code,
                "rate_limit": headers,
                "response": body,
            }
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        request_data: dict[str, Any],
        parser: Callable[[dict[str, Any]], T],
    ) -> T:
        cached = self.cache.get(method, endpoint, request_data)
        if cached is not None:
            self._trace_event(
                method=method,
                endpoint=endpoint,
                request=request_data,
                cache_hit=True,
                status_code=cached.status_code,
                headers=cached.headers,
                body=cached.body,
            )
            return parser(cached.body)

        if self._remaining == 0:
            raise RateLimitExhausted("ADS rate limit exhausted before uncached request")

        headers = {"Authorization": f"Bearer {self._token}"}
        url = f"{self.base_url}{endpoint}"
        try:
            if method == "GET":
                response = self._http_client.get(url, params=request_data, headers=headers)
            else:
                response = self._http_client.post(url, json=request_data, headers=headers)
        except httpx.HTTPError as exc:
            raise ADSAPIError(f"ADS request failed: {exc}") from exc

        selected_headers = _rate_headers(response.headers)
        self._update_quota(selected_headers)
        try:
            body = response.json()
        except ValueError as exc:
            self._trace_event(
                method=method,
                endpoint=endpoint,
                request=request_data,
                cache_hit=False,
                status_code=response.status_code,
                headers=selected_headers,
                body={"error": "non-JSON response"},
            )
            raise ADSAPIError("ADS returned a non-JSON response") from exc

        self._trace_event(
            method=method,
            endpoint=endpoint,
            request=request_data,
            cache_hit=False,
            status_code=response.status_code,
            headers=selected_headers,
            body=body,
        )
        if response.status_code == 429:
            self._remaining = 0
            raise RateLimitExhausted("ADS rate limit exhausted")
        if response.status_code >= 400:
            raise ADSAPIError(f"ADS returned HTTP {response.status_code}")
        if not isinstance(body, dict):
            raise ADSAPIError("ADS returned a non-object JSON response")

        parsed = parser(body)
        safe_body = self.trace.scrub(body)
        if not isinstance(safe_body, dict):
            raise ADSAPIError("ADS response could not be sanitized for caching")
        self.cache.put(
            method,
            endpoint,
            request_data,
            CachedResponse(
                status_code=response.status_code,
                headers=selected_headers,
                body=safe_body,
            ),
        )
        return parsed

    @staticmethod
    def _parse_search(body: dict[str, Any]) -> SearchResponse:
        try:
            response = body["response"]
            if not isinstance(response, dict) or not isinstance(response["docs"], list):
                raise TypeError
            return SearchResponse(
                num_found=response["numFound"],
                records=[ADSRecord.model_validate(record) for record in response["docs"]],
            )
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            raise ADSAPIError("ADS search response has an invalid schema") from exc

    @staticmethod
    def _parse_export(body: dict[str, Any]) -> str:
        exported = body.get("export")
        if not isinstance(exported, str):
            raise ADSAPIError("ADS export response has an invalid schema")
        return exported

    def search(self, query: str) -> SearchResponse:
        request = {"q": query, "fl": SEARCH_FIELDS, "rows": 50}
        return self._request("GET", SEARCH_PATH, request, self._parse_search)

    def export_bibtex(self, bibcodes: list[str]) -> str:
        if not bibcodes:
            return ""
        request = {"bibcode": bibcodes, "sort": "no sort"}
        return self._request("POST", EXPORT_PATH, request, self._parse_export)
