from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CacheError(RuntimeError):
    """Raised when a persisted cache entry is malformed."""


@dataclass(frozen=True)
class CachedResponse:
    status_code: int
    headers: dict[str, str]
    body: dict[str, Any]


class DiskCache:
    """Persist safe JSON API responses by canonical request identity."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _identity(method: str, endpoint: str, request: object) -> dict[str, object]:
        return {
            "method": method.upper(),
            "endpoint": endpoint,
            "request": request,
        }

    def _path(self, method: str, endpoint: str, request: object) -> Path:
        identity = self._identity(method, endpoint, request)
        canonical = json.dumps(
            identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        return self.root / f"{digest}.json"

    def get(
        self, method: str, endpoint: str, request: object
    ) -> CachedResponse | None:
        path = self._path(method, endpoint, request)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = self._identity(method, endpoint, request)
            if payload["request_identity"] != expected:
                raise CacheError(f"Cache identity mismatch in {path}")
            return CachedResponse(
                status_code=int(payload["status_code"]),
                headers={str(key): str(value) for key, value in payload["headers"].items()},
                body=payload["body"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CacheError(f"Malformed cache entry {path}") from exc

    def put(
        self,
        method: str,
        endpoint: str,
        request: object,
        response: CachedResponse,
    ) -> None:
        path = self._path(method, endpoint, request)
        payload = {
            "request_identity": self._identity(method, endpoint, request),
            "status_code": response.status_code,
            "headers": response.headers,
            "body": response.body,
        }
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
