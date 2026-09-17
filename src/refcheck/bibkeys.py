from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from refcheck.models import ADSRecord
from refcheck.normalize import latex_to_text


_ENTRY = re.compile(r"@(?P<kind>[A-Za-z]+)\s*\{(?P<key>[^,}\s]+)\s*,")


def _suffix(ordinal: int) -> str:
    """Return the lowercase key suffix for the ordinal duplicate, 0 -> a."""

    chars: list[str] = []
    ordinal += 1
    while ordinal > 0:
        ordinal, remainder = divmod(ordinal - 1, 26)
        chars.append(chr(ord("a") + remainder))
    return "".join(reversed(chars))


def _slug(record: ADSRecord) -> str | None:
    """Return the first-author surname plus year key, or None if unavailable."""

    if record.year is None or not record.first_author:
        return None
    surname = re.sub(
        r"\s+", "", latex_to_text(record.first_author.split(",", 1)[0])
    )
    if not surname:
        return None
    return f"{surname}{record.year}"


def _plan_keys(records: Sequence[ADSRecord]) -> list[str | None]:
    slugs = [_slug(record) for record in records]
    counts = Counter(slug for slug in slugs if slug is not None)
    seen: Counter[str] = Counter()
    planned: list[str | None] = []
    for slug in slugs:
        if slug is None or counts[slug] == 1:
            planned.append(slug)
            continue
        ordinal = seen[slug]
        seen[slug] += 1
        planned.append(slug + _suffix(ordinal))
    return planned


def rewrite_bibtex_keys(
    corrected_bib: str, records: Sequence[ADSRecord]
) -> str:
    """Replace ADS bibcode-derived keys with first-author surname plus year
    slugs (Murphy2026, Murphy2026a, ...), preserving the export text verbatim.

    `records` must list the resolved records in the same order as the exported
    BibTeX entries, which is the requested bibcode order.
    """

    if not corrected_bib:
        return corrected_bib
    matches = list(_ENTRY.finditer(corrected_bib))
    if len(matches) != len(records):
        raise ValueError(
            "ADS BibTeX export returned "
            f"{len(matches)} entries for {len(records)} resolved records"
        )
    planned = _plan_keys(records)
    parts: list[str] = []
    cursor = 0
    for match, key in zip(matches, planned):
        parts.append(corrected_bib[cursor : match.start("key")])
        parts.append(key if key is not None else match.group("key"))
        cursor = match.end("key")
    parts.append(corrected_bib[cursor:])
    return "".join(parts)
