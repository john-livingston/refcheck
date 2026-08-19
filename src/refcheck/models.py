from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Base model that rejects misspelled and unexpected fields."""

    model_config = ConfigDict(extra="forbid")


class Verdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNRESOLVED = "UNRESOLVED"


class ResolutionStage(StrEnum):
    IDENTIFIER = "identifier"
    AUTHOR_YEAR_JOURNAL = "author_year_journal"
    AUTHOR_YEAR_RANGE = "author_year_range"
    TITLE_AUTHOR = "title_author"
    LLM = "llm"


class SourceEntry(StrictModel):
    key: str
    raw: str
    authors: list[str] = Field(default_factory=list)
    authors_truncated: bool = False
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    page: str | None = None
    title: str | None = None
    doi: str | None = None
    arxiv: str | None = None

    @field_validator("key")
    @classmethod
    def key_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Bibliography key must not be blank")
        return value.strip()

    @property
    def first_author(self) -> str | None:
        return self.authors[0] if self.authors else None


class ADSRecord(StrictModel):
    bibcode: str
    title: str = ""
    author: list[str] = Field(default_factory=list)
    first_author: str = ""
    year: int | None = None
    pub: str = ""
    volume: str | None = None
    page: str | None = None
    doi: list[str] = Field(default_factory=list)
    identifier: list[str] = Field(default_factory=list)
    pubdate: str | None = None

    @field_validator("title", mode="before")
    @classmethod
    def flatten_title(cls, value: object) -> str:
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return "" if value is None else str(value)

    @field_validator("page", mode="before")
    @classmethod
    def flatten_page(cls, value: object) -> str | None:
        if isinstance(value, list):
            return str(value[0]) if value else None
        return None if value is None else str(value)

    @field_validator("volume", mode="before")
    @classmethod
    def stringify_volume(cls, value: object) -> str | None:
        return None if value is None else str(value)

    @field_validator("first_author", mode="before")
    @classmethod
    def default_first_author(cls, value: object) -> str:
        return "" if value is None else str(value)

    @model_validator(mode="after")
    def derive_first_author(self) -> ADSRecord:
        if not self.first_author and self.author:
            self.first_author = self.author[0]
        return self


class SearchResponse(StrictModel):
    num_found: int
    records: list[ADSRecord] = Field(default_factory=list)


class FieldDifference(StrictModel):
    field: str
    ours: str | None
    ads: str | None
    details: list[str] = Field(default_factory=list)


class Resolution(StrictModel):
    source: SourceEntry
    verdict: Verdict
    record: ADSRecord | None = None
    stage: ResolutionStage | None = None
    differences: list[FieldDifference] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)


class RunResult(StrictModel):
    schema_version: int = 1
    results: list[Resolution]
    corrected_bib: str = ""

    @property
    def has_unverified_entries(self) -> bool:
        return any(
            result.verdict
            in {Verdict.AMBIGUOUS, Verdict.NOT_FOUND, Verdict.UNRESOLVED}
            for result in self.results
        )


class RunConfig(StrictModel):
    input_path: Path
    output_dir: Path
    cache_dir: Path
    ads_token: SecretStr
    use_llm: bool = False
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None
