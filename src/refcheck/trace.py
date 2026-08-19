from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_SENSITIVE_KEYS = {"authorization", "token", "api_key", "apikey"}


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return (
        normalized in _SENSITIVE_KEYS
        or normalized.endswith("_token")
        or normalized.endswith("_api_key")
    )


def _scrub(value: Any, secrets: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if _is_sensitive_key(key)
            else _scrub(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if isinstance(value, str):
        scrubbed = value
        for secret in sorted(secrets, key=len, reverse=True):
            scrubbed = scrubbed.replace(secret, "[REDACTED]")
        return scrubbed
    return value


class TraceWriter:
    """Append credential-free JSON events as complete lines."""

    def __init__(self, path: Path, *, reset: bool = False) -> None:
        self.path = Path(path)
        self._secrets: set[str] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if reset:
            self.path.write_text("", encoding="utf-8")
        else:
            self.path.touch(exist_ok=True)

    def register_secret(self, secret: str) -> None:
        if secret:
            self._secrets.add(secret)

    def scrub(self, value: Any) -> Any:
        return _scrub(value, self._secrets)

    def write(self, event: dict[str, Any]) -> None:
        line = json.dumps(
            self.scrub(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, line)
        finally:
            os.close(descriptor)
