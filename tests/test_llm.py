from __future__ import annotations

import json

import httpx
import pytest

from refcheck.llm import LLMResponseError, OpenRouterClient
from refcheck.trace import TraceWriter


def _response(content):
    return httpx.Response(
        200,
        json={
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}}
            ]
        },
    )


def test_llm_can_only_propose_query_and_select_index(
    tmp_path, source_factory, record_factory
):
    payloads = []
    replies = iter(
        [
            _response('{"query":"bibcode:2025ApJ...985L..43O"}'),
            _response('{"index":0}'),
        ]
    )

    def handler(request):
        payloads.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer router-secret"
        return next(replies)

    trace = TraceWriter(tmp_path / "trace.jsonl", reset=True)
    client = OpenRouterClient(
        api_key="router-secret",
        model="provider/model",
        trace=trace,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    query = client.propose_query(source_factory(), ["year:2025"], 1)
    index = client.select_record(source_factory(), query, [record_factory()])

    assert query == "bibcode:2025ApJ...985L..43O"
    assert index == 0
    assert set(payloads[0]["response_format"]["json_schema"]["schema"]["properties"]) == {
        "query"
    }
    assert set(payloads[1]["response_format"]["json_schema"]["schema"]["properties"]) == {
        "index"
    }
    assert all(
        payload["response_format"]["json_schema"]["schema"][
            "additionalProperties"
        ]
        is False
        for payload in payloads
    )
    persisted = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "router-secret" not in persisted


@pytest.mark.parametrize(
    "content",
    [
        '{"query":"author:Ouyang","title":"invented"}',
        "not json",
        '{"query":""}',
    ],
)
def test_llm_rejects_non_schema_query_output(tmp_path, source_factory, content):
    client = OpenRouterClient(
        api_key="secret",
        model="provider/model",
        trace=TraceWriter(tmp_path / "trace.jsonl", reset=True),
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: _response(content))
        ),
    )

    with pytest.raises(LLMResponseError):
        client.propose_query(source_factory(), [], 1)


def test_llm_rejects_index_outside_ads_results(
    tmp_path, source_factory, record_factory
):
    client = OpenRouterClient(
        api_key="secret",
        model="provider/model",
        trace=TraceWriter(tmp_path / "trace.jsonl", reset=True),
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: _response('{"index":2}'))
        ),
    )

    with pytest.raises(LLMResponseError, match="outside"):
        client.select_record(source_factory(), "year:2025", [record_factory()])
