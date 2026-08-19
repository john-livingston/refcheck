from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rich.console import Console

from refcheck.comparison import compare_entry
from refcheck.models import (
    ADSRecord,
    Resolution,
    ResolutionStage,
    SearchResponse,
    SourceEntry,
    Verdict,
)
from refcheck.normalize import (
    authors_equivalent,
    journal_bibstem,
    normalize_arxiv,
    normalize_doi,
    normalize_journal,
    normalize_page,
    normalize_text,
    title_keywords,
    title_similarity,
)


class ADSLike(Protocol):
    def search(self, query: str) -> SearchResponse: ...


class LLMLike(Protocol):
    def propose_query(
        self, entry: SourceEntry, prior_queries: list[str], attempt: int
    ) -> str: ...

    def select_record(
        self, entry: SourceEntry, query: str, records: list[ADSRecord]
    ) -> int | None: ...


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r'\"').replace("\n", " ")


def _author_surname(entry: SourceEntry) -> str | None:
    if not entry.first_author:
        return None
    surname = entry.first_author.split(",", 1)[0]
    return surname.strip() or None


def build_deterministic_queries(
    entry: SourceEntry,
) -> list[tuple[ResolutionStage, str]]:
    """Build the fixed ADS query ladder without issuing any requests."""

    queries: list[tuple[ResolutionStage, str]] = []
    if entry.doi:
        queries.append(
            (ResolutionStage.IDENTIFIER, f'doi:"{_quote(normalize_doi(entry.doi))}"')
        )
    if entry.arxiv:
        queries.append(
            (
                ResolutionStage.IDENTIFIER,
                f'identifier:"arXiv:{_quote(normalize_arxiv(entry.arxiv))}"',
            )
        )

    surname = _author_surname(entry)
    stem = journal_bibstem(entry.journal)
    if surname and entry.year and stem:
        queries.append(
            (
                ResolutionStage.AUTHOR_YEAR_JOURNAL,
                f'author:"^{_quote(surname)}" year:{entry.year} bibstem:{stem}',
            )
        )
    if surname and entry.year:
        queries.append(
            (
                ResolutionStage.AUTHOR_YEAR_RANGE,
                f'author:"^{_quote(surname)}" year:{entry.year - 1}-{entry.year + 1}',
            )
        )
    keywords = title_keywords(entry.title)
    if surname and keywords:
        terms = " ".join(f'"{_quote(keyword)}"' for keyword in keywords)
        queries.append(
            (
                ResolutionStage.TITLE_AUTHOR,
                f'author:"^{_quote(surname)}" title:({terms})',
            )
        )
    return queries


@dataclass(frozen=True)
class _CandidateScore:
    record: ADSRecord
    score: int
    agreements: int


def _score(entry: SourceEntry, record: ADSRecord) -> _CandidateScore:
    score = 0
    agreements = 0
    checks: list[tuple[bool, int]] = [
        (
            bool(entry.first_author and record.first_author)
            and authors_equivalent(entry.first_author, record.first_author),
            2,
        ),
        (
            entry.year is not None
            and record.year is not None
            and entry.year == record.year,
            2,
        ),
        (
            bool(entry.journal and record.pub)
            and normalize_journal(entry.journal) == normalize_journal(record.pub),
            2,
        ),
        (
            bool(entry.volume and record.volume)
            and normalize_text(entry.volume) == normalize_text(record.volume),
            2,
        ),
        (
            bool(entry.page and record.page)
            and normalize_page(entry.page) == normalize_page(record.page),
            3,
        ),
        (
            bool(entry.title and record.title)
            and title_similarity(entry.title, record.title) >= 0.75,
            4,
        ),
    ]
    for agrees, weight in checks:
        if agrees:
            score += weight
            agreements += 1
    return _CandidateScore(record=record, score=score, agreements=agreements)


def _record_has_identifier(record: ADSRecord, query: str) -> bool:
    if query.startswith("doi:"):
        expected = normalize_doi(query.split('"', 2)[1])
        return any(normalize_doi(value) == expected for value in record.doi)
    if query.startswith("identifier:"):
        expected = normalize_arxiv(query.split('"', 2)[1])
        return any(normalize_arxiv(value) == expected for value in record.identifier)
    return False


def _select_candidate(
    entry: SourceEntry,
    records: list[ADSRecord],
    stage: ResolutionStage,
    query: str,
) -> tuple[str, ADSRecord | None, list[str]]:
    if stage == ResolutionStage.IDENTIFIER:
        exact = [record for record in records if _record_has_identifier(record, query)]
        if len(exact) == 1:
            return "match", exact[0], []
        if len(exact) > 1:
            return "ambiguous", None, [record.bibcode for record in exact]
        return "none", None, []

    ranked = sorted(
        (_score(entry, record) for record in records),
        key=lambda candidate: (-candidate.score, candidate.record.bibcode),
    )
    if not ranked:
        return "none", None, []
    top = ranked[0]
    if top.score < 8 or top.agreements < 3:
        return "none", None, []
    if len(ranked) > 1 and top.score - ranked[1].score < 2:
        tied = [
            candidate.record.bibcode
            for candidate in ranked
            if top.score - candidate.score < 2
        ]
        return "ambiguous", None, tied
    return "match", top.record, []


class Resolver:
    """Resolve source entries through deterministic ADS queries and optional LLM help."""

    def __init__(
        self,
        ads: ADSLike,
        *,
        llm: LLMLike | None = None,
        console: Console | None = None,
    ) -> None:
        self.ads = ads
        self.llm = llm
        self.console = console or Console(stderr=True)

    @staticmethod
    def _matched(
        entry: SourceEntry, record: ADSRecord, stage: ResolutionStage
    ) -> Resolution:
        differences = compare_entry(entry, record)
        verdict = Verdict.CORRECTED if differences else Verdict.CONFIRMED
        return Resolution(
            source=entry,
            verdict=verdict,
            record=record,
            stage=stage,
            differences=differences,
        )

    def resolve(self, entry: SourceEntry, *, use_llm: bool = False) -> Resolution:
        queries = build_deterministic_queries(entry)
        prior_queries: list[str] = []
        saw_plausible_candidate = False
        ambiguous_candidates: list[str] = []

        for stage, query in queries:
            prior_queries.append(query)
            response = self.ads.search(query)
            if response.records:
                best_score = max(_score(entry, record).score for record in response.records)
                saw_plausible_candidate = saw_plausible_candidate or best_score >= 5
            outcome, record, candidates = _select_candidate(
                entry, response.records, stage, query
            )
            if outcome == "match" and record is not None:
                return self._matched(entry, record, stage)
            if outcome == "ambiguous":
                ambiguous_candidates = candidates

        if use_llm:
            if self.llm is None:
                raise ValueError("LLM assistance was enabled without an LLM client")
            for attempt in range(1, 4):
                query = self.llm.propose_query(entry, prior_queries, attempt)
                prior_queries.append(query)
                response = self.ads.search(query)
                if response.records:
                    best_score = max(
                        _score(entry, record).score for record in response.records
                    )
                    saw_plausible_candidate = (
                        saw_plausible_candidate or best_score >= 5
                    )
                if not response.records:
                    continue
                index = self.llm.select_record(entry, query, response.records)
                if index is None:
                    continue
                if index < 0 or index >= len(response.records):
                    raise ValueError("LLM selected an ADS result index outside the response")
                return self._matched(entry, response.records[index], ResolutionStage.LLM)
            self.console.print(
                "[bold red]LLM resolution exhausted after 3 attempts[/bold red]"
            )

        if ambiguous_candidates:
            return Resolution(
                source=entry,
                verdict=Verdict.AMBIGUOUS,
                candidates=ambiguous_candidates,
            )
        return Resolution(
            source=entry,
            verdict=(
                Verdict.UNRESOLVED
                if saw_plausible_candidate
                else Verdict.NOT_FOUND
            ),
        )
