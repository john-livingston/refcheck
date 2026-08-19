from __future__ import annotations

from refcheck.models import ADSRecord, FieldDifference, SourceEntry
from refcheck.normalize import (
    authors_equivalent,
    normalize_journal,
    normalize_page,
    normalize_text,
)


def _display(value: object) -> str | None:
    return None if value is None else str(value)


def _surname(value: str) -> str:
    if "," in value:
        return value.split(",", 1)[0].strip()
    parts = value.split()
    return parts[-1] if parts else value


def _author_order_difference(
    source: SourceEntry, record: ADSRecord
) -> FieldDifference | None:
    if not source.authors and not record.author:
        return None

    details: list[str] = []
    if source.authors_truncated:
        for ours_position, source_author in enumerate(source.authors, start=1):
            matches = [
                index
                for index, ads_author in enumerate(record.author, start=1)
                if authors_equivalent(source_author, ads_author)
            ]
            label = _surname(source_author)
            if not matches:
                details.append(f"{label}: absent from ADS author list")
            elif matches[0] != ours_position:
                details.append(
                    f"{label}: ours position {ours_position} -> ADS position {matches[0]}"
                )
    else:
        same_length = len(source.authors) == len(record.author)
        same_order = same_length and all(
            authors_equivalent(ours, ads)
            for ours, ads in zip(source.authors, record.author, strict=True)
        )
        if same_order:
            return None
        for ours_position, source_author in enumerate(source.authors, start=1):
            matches = [
                index
                for index, ads_author in enumerate(record.author, start=1)
                if authors_equivalent(source_author, ads_author)
            ]
            label = _surname(source_author)
            if not matches:
                details.append(f"{label}: absent from ADS author list")
            elif matches[0] != ours_position:
                details.append(
                    f"{label}: ours position {ours_position} -> ADS position {matches[0]}"
                )
        if len(source.authors) != len(record.author):
            details.append(
                f"ours {len(source.authors)} authors -> ADS {len(record.author)} authors"
            )

    if not details:
        return None
    return FieldDifference(
        field="author_order",
        ours="; ".join(source.authors) if source.authors else None,
        ads="; ".join(record.author) if record.author else None,
        details=details,
    )


def compare_entry(source: SourceEntry, record: ADSRecord) -> list[FieldDifference]:
    """Return every core bibliographic difference after normalization."""

    differences: list[FieldDifference] = []
    comparisons = [
        (
            "year",
            source.year,
            record.year,
            lambda left, right: left is not None
            and right is not None
            and int(left) == int(right),
        ),
        (
            "journal",
            source.journal,
            record.pub,
            lambda left, right: bool(normalize_journal(left))
            and normalize_journal(left) == normalize_journal(right),
        ),
        (
            "volume",
            source.volume,
            record.volume,
            lambda left, right: bool(normalize_text(left))
            and normalize_text(left) == normalize_text(right),
        ),
        (
            "page",
            source.page,
            record.page,
            lambda left, right: bool(normalize_page(left))
            and normalize_page(left) == normalize_page(right),
        ),
        (
            "first_author",
            source.first_author,
            record.first_author,
            authors_equivalent,
        ),
    ]
    for field, ours, ads, equivalent in comparisons:
        if not equivalent(ours, ads):
            differences.append(
                FieldDifference(field=field, ours=_display(ours), ads=_display(ads))
            )

    author_difference = _author_order_difference(source, record)
    if author_difference is not None:
        differences.append(author_difference)
    return differences
