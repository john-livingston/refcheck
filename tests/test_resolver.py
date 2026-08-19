from __future__ import annotations

from io import StringIO

from rich.console import Console

from refcheck.models import SearchResponse, Verdict
from refcheck.resolver import Resolver, build_deterministic_queries


class QueueADS:
    def __init__(self, responses):
        self.responses = list(responses)
        self.queries: list[str] = []

    def search(self, query: str) -> SearchResponse:
        self.queries.append(query)
        return self.responses.pop(0)


class EmptyLLM:
    def __init__(self):
        self.proposals = 0
        self.selections = 0

    def propose_query(self, entry, prior_queries, attempt):
        self.proposals += 1
        return f'bibcode:"missing-{attempt}"'

    def select_record(self, entry, query, records):
        self.selections += 1
        return None


def response(*records):
    return SearchResponse(num_found=len(records), records=list(records))


def test_builds_resolution_ladder_in_order(source_factory):
    source = source_factory(
        doi="10.3847/2041-8213/adda4b",
        arxiv="2505.13066",
        title="Retention of Surface Water on Tidally Locked Rocky Planets",
    )

    queries = build_deterministic_queries(source)

    assert [stage.value for stage, _ in queries] == [
        "identifier",
        "identifier",
        "author_year_journal",
        "author_year_range",
        "title_author",
    ]
    assert queries[0][1] == 'doi:"10.3847/2041-8213/adda4b"'
    assert queries[1][1] == 'identifier:"arXiv:2505.13066"'
    assert "bibstem:ApJL" in queries[2][1]
    assert "year:2024-2026" in queries[3][1]
    assert "title:" in queries[4][1]


def test_exact_identifier_stops_ladder(source_factory, record_factory):
    source = source_factory(doi="10.3847/2041-8213/adda4b")
    ads = QueueADS([response(record_factory())])

    result = Resolver(ads).resolve(source)

    assert result.verdict == Verdict.CONFIRMED
    assert result.record.bibcode == "2025ApJ...985L..43O"
    assert len(ads.queries) == 1


def test_unique_strong_metadata_match_is_corrected(source_factory, record_factory):
    source = source_factory(page="L44")
    ads = QueueADS([response(record_factory())])

    result = Resolver(ads).resolve(source)

    assert result.verdict == Verdict.CORRECTED
    assert [diff.field for diff in result.differences] == ["page"]


def test_tied_safe_candidates_are_ambiguous(source_factory, record_factory):
    first = record_factory(bibcode="one")
    second = record_factory(bibcode="two")
    ads = QueueADS([response(first, second), response(first, second)])

    result = Resolver(ads).resolve(source_factory())

    assert result.verdict == Verdict.AMBIGUOUS
    assert result.candidates == ["one", "two"]


def test_empty_searches_are_not_found(source_factory):
    ads = QueueADS([response(), response()])

    result = Resolver(ads).resolve(source_factory())

    assert result.verdict == Verdict.NOT_FOUND


def test_near_candidate_without_enough_evidence_is_unresolved(
    source_factory, record_factory
):
    unsafe = record_factory(pub="Icarus", volume="1")
    ads = QueueADS([response(unsafe), response(unsafe)])

    result = Resolver(ads).resolve(source_factory())

    assert result.verdict == Verdict.UNRESOLVED


def test_unrelated_broad_search_result_does_not_match_fabricated_entry(
    source_factory, record_factory
):
    unrelated = record_factory(pub="Icarus", volume="1", page=["1"])
    ads = QueueADS([response(), response(unrelated)])

    result = Resolver(ads).resolve(source_factory())

    assert result.verdict == Verdict.NOT_FOUND


def test_llm_has_three_query_attempts_and_warns_on_exhaustion(source_factory):
    llm = EmptyLLM()
    ads = QueueADS([response(), response(), response(), response(), response()])
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)

    result = Resolver(ads, llm=llm, console=console).resolve(
        source_factory(), use_llm=True
    )

    assert result.verdict == Verdict.NOT_FOUND
    assert llm.proposals == 3
    assert llm.selections == 0
    assert "LLM resolution exhausted after 3 attempts" in stream.getvalue()
