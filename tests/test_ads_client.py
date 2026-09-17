from __future__ import annotations

import json

import httpx
import pytest

from refcheck.ads import ADSAPIError, ADSClient, RateLimitExhausted
from refcheck.cache import DiskCache
from refcheck.trace import TraceWriter


def _search_payload(record_factory):
    record = record_factory().model_dump(mode="json")
    record["title"] = [record["title"]]
    record["page"] = [record["page"]]
    return {"response": {"numFound": 1, "docs": [record]}}


def _client(tmp_path, handler):
    return ADSClient(
        token="ads-super-secret",
        cache=DiskCache(tmp_path / "cache"),
        trace=TraceWriter(tmp_path / "trace.jsonl", reset=True),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_search_contract_cache_trace_and_secret_safety(tmp_path, record_factory):
    requests: list[httpx.Request] = []

    def handler(request):
        requests.append(request)
        payload = _search_payload(record_factory)
        payload["echo"] = "ads-super-secret"
        return httpx.Response(
            200,
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000"},
            json=payload,
        )

    client = _client(tmp_path, handler)

    first = client.search('author:"^Ouyang" year:2025 bibstem:ApJ')
    second = client.search('author:"^Ouyang" year:2025 bibstem:ApJ')

    assert first == second
    assert first.records[0].bibcode == "2025ApJ...985L..43O"
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/v1/search/query"
    assert request.url.params["fl"] == (
        "bibcode,title,author,first_author,year,pub,volume,page,doi,"
        "identifier,pubdate"
    )
    assert request.url.params["rows"] == "50"
    assert request.headers["Authorization"] == "Bearer ads-super-secret"

    trace_lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["cache_hit"] for line in trace_lines] == [False, True]
    persisted = "".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    assert "ads-super-secret" not in persisted


def test_zero_remaining_allows_cache_but_blocks_new_request(tmp_path, record_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"X-RateLimit-Remaining": "0"},
            json=_search_payload(record_factory),
        )

    client = _client(tmp_path, handler)
    query = 'author:"^Ouyang" year:2025 bibstem:ApJ'

    client.search(query)
    client.search(query)
    with pytest.raises(RateLimitExhausted, match="rate limit"):
        client.search('author:"^Yang" year:2025')
    assert calls == 1


def test_http_429_marks_quota_exhausted(tmp_path):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": "quota"})

    client = _client(tmp_path, handler)

    with pytest.raises(RateLimitExhausted):
        client.search("first")
    with pytest.raises(RateLimitExhausted):
        client.search("second")
    assert calls == 1


def test_export_posts_bibcodes_and_returns_verbatim(tmp_path):
    requests: list[httpx.Request] = []
    exported = "@ARTICLE{one,\n  title = {Exact ADS text}\n}\n"

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"export": exported})

    client = _client(tmp_path, handler)

    assert client.export_bibtex(["one", "two"]) == exported
    assert client.export_bibtex(["one", "two"]) == exported
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/export/bibtex"
    assert json.loads(requests[0].content) == {
        "bibcode": ["one", "two"],
        "sort": "no sort",
    }


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": "failure"}),
        httpx.Response(200, json={"unexpected": "shape"}),
    ],
)
def test_http_and_schema_failures_are_loud_and_safe(tmp_path, response):
    client = _client(tmp_path, lambda request: response)

    with pytest.raises(ADSAPIError):
        client.search("bibcode:missing")
