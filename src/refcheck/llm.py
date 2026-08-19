from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import Field, ValidationError, field_validator

from refcheck.models import ADSRecord, SourceEntry, StrictModel
from refcheck.trace import TraceWriter


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMResponseError(RuntimeError):
    """Raised when OpenRouter fails or returns output outside the strict schema."""


class QueryProposal(StrictModel):
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def query_must_be_one_line(cls, value: str) -> str:
        query = value.strip()
        if not query or "\n" in query or "\r" in query:
            raise ValueError("ADS query must be one non-empty line")
        return query


class RecordSelection(StrictModel):
    index: int | None


class OpenRouterClient:
    """Constrain LLM output to ADS query strings and result indexes."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        trace: TraceWriter,
        http_client: httpx.Client | None = None,
        url: str = OPENROUTER_URL,
    ) -> None:
        if not api_key or not model:
            raise ValueError("OpenRouter API key and model must not be empty")
        self._api_key = api_key
        self.model = model
        self.trace = trace
        self.trace.register_secret(api_key)
        self.url = url
        self._http_client = http_client or httpx.Client(timeout=60.0)
        self._owns_http_client = http_client is None

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def _complete(
        self,
        *,
        operation: str,
        messages: list[dict[str, str]],
        schema_model: type[StrictModel],
    ) -> StrictModel:
        schema = schema_model.model_json_schema()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": operation,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        try:
            response = self._http_client.post(
                self.url,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            raise LLMResponseError(f"OpenRouter request failed: {exc}") from exc

        try:
            response_body: Any = response.json()
        except ValueError as exc:
            response_body = {"error": "non-JSON response"}
            self.trace.write(
                {
                    "service": "openrouter",
                    "operation": operation,
                    "request": {"model": self.model, "messages": messages},
                    "status_code": response.status_code,
                    "response": response_body,
                }
            )
            raise LLMResponseError("OpenRouter returned a non-JSON response") from exc

        self.trace.write(
            {
                "service": "openrouter",
                "operation": operation,
                "request": {"model": self.model, "messages": messages},
                "status_code": response.status_code,
                "response": response_body,
            }
        )
        if response.status_code >= 400:
            raise LLMResponseError(f"OpenRouter returned HTTP {response.status_code}")
        try:
            content = response_body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            decoded = json.loads(content)
            return schema_model.model_validate(decoded)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise LLMResponseError(
                f"OpenRouter {operation} output violated the required schema"
            ) from exc

    def propose_query(
        self, entry: SourceEntry, prior_queries: list[str], attempt: int
    ) -> str:
        prompt = json.dumps(
            {
                "source_entry": entry.model_dump(mode="json"),
                "prior_ads_queries": prior_queries,
                "attempt": attempt,
                "instruction": "Propose one NASA ADS query. Do not provide bibliographic fields.",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        proposal = self._complete(
            operation="ads_query_proposal",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You only propose NASA ADS query strings. Never generate, correct, "
                        "or return bibliographic field values."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            schema_model=QueryProposal,
        )
        assert isinstance(proposal, QueryProposal)
        return proposal.query

    def select_record(
        self, entry: SourceEntry, query: str, records: list[ADSRecord]
    ) -> int | None:
        indexed_records = [
            {"index": index, "ads_record": record.model_dump(mode="json")}
            for index, record in enumerate(records)
        ]
        prompt = json.dumps(
            {
                "source_entry": entry.model_dump(mode="json"),
                "ads_query": query,
                "ads_results": indexed_records,
                "instruction": (
                    "Select one ADS result by zero-based index, or null. "
                    "Do not provide bibliographic fields."
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        selection = self._complete(
            operation="ads_record_selection",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You only select among supplied NASA ADS records by index. Never "
                        "generate, correct, or return bibliographic field values."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            schema_model=RecordSelection,
        )
        assert isinstance(selection, RecordSelection)
        if selection.index is not None and not 0 <= selection.index < len(records):
            raise LLMResponseError("OpenRouter selected an index outside ADS results")
        return selection.index
