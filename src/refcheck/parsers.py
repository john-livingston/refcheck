from __future__ import annotations

import re
from pathlib import Path

from pydantic import ValidationError

from refcheck.models import SourceEntry
from refcheck.normalize import latex_to_text, normalize_arxiv, normalize_doi


class BibliographyParseError(ValueError):
    """Raised when a bibliography file cannot be parsed safely."""


_BIBITEM = re.compile(
    r"\\bibitem(?:\[(?P<label>[^]]*)\])?\{(?P<key>[^}]+)\}(?P<body>.*?)(?=\\bibitem|\\end\{thebibliography\}|\Z)",
    flags=re.DOTALL,
)
_YEAR = re.compile(r"(?:^|,)\s*((?:18|19|20)\d{2})\s*,")
_DOI = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/|\bdoi\s*:\s*)(10\.\d{4,9}/[^\s,}\]]+)",
    flags=re.IGNORECASE,
)
_ARXIV = re.compile(
    r"(?:https?://arxiv\.org/(?:abs|pdf)/|\barxiv\s*:\s*)([a-z-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?",
    flags=re.IGNORECASE,
)


def _strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", text)


def _remove_identifiers(text: str) -> str:
    text = _DOI.sub("", text)
    text = _ARXIV.sub("", text)
    return text


def _parse_author_pairs(text: str) -> tuple[list[str], bool]:
    truncated = bool(re.search(r"\bet\s+al\.?", text, flags=re.IGNORECASE))
    cleaned = re.sub(r"\bet\s+al\.?,?", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace(r"\&", "&")
    segments = re.split(r"\s+(?:&|and)\s+", cleaned, flags=re.IGNORECASE)
    authors: list[str] = []
    for segment in segments:
        tokens = [token.strip() for token in segment.strip(" ,;\n").split(",")]
        tokens = [token for token in tokens if token]
        if len(tokens) == 1:
            authors.append(latex_to_text(tokens[0]))
            continue
        index = 0
        while index + 1 < len(tokens):
            authors.append(latex_to_text(f"{tokens[index]}, {tokens[index + 1]}"))
            index += 2
        if index < len(tokens):
            authors.append(latex_to_text(tokens[index]))
    return authors, truncated


def _parse_bibitems(text: str) -> list[SourceEntry]:
    entries: list[SourceEntry] = []
    for match in _BIBITEM.finditer(_strip_comments(text)):
        raw_body = match.group("body").strip()
        doi_match = _DOI.search(raw_body)
        arxiv_match = _ARXIV.search(raw_body)
        citation = _remove_identifiers(raw_body)
        citation = re.sub(r"\\(?:newblock|url)\b", " ", citation)
        citation = re.sub(r"\s+", " ", citation).strip(" ,.;")
        year_match = _YEAR.search(citation)
        if year_match is None:
            raise BibliographyParseError(
                f"Entry {match.group('key')} has no parseable publication year"
            )

        author_text = citation[: year_match.start()].strip(" ,;")
        authors, truncated = _parse_author_pairs(author_text)
        remaining = citation[year_match.end() :].strip(" ,.;")
        parts = [part.strip(" .;") for part in remaining.split(",") if part.strip()]
        if len(parts) < 3:
            raise BibliographyParseError(
                f"Entry {match.group('key')} has no journal, volume, and page tuple"
            )
        journal, volume, page = parts[-3:]
        title = ", ".join(parts[:-3]) or None
        page = re.split(r"-{1,2}|\N{EN DASH}", page, maxsplit=1)[0]
        try:
            entries.append(
                SourceEntry(
                    key=match.group("key"),
                    raw=raw_body,
                    authors=authors,
                    authors_truncated=truncated,
                    year=int(year_match.group(1)),
                    journal=latex_to_text(journal) or journal,
                    volume=latex_to_text(volume),
                    page=latex_to_text(page),
                    title=latex_to_text(title) if title else None,
                    doi=normalize_doi(doi_match.group(1)) if doi_match else None,
                    arxiv=normalize_arxiv(arxiv_match.group(1)) if arxiv_match else None,
                )
            )
        except ValidationError as exc:
            raise BibliographyParseError(str(exc)) from exc
    return entries


def _matching_delimiter(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_quote = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    raise BibliographyParseError("Unbalanced BibTeX entry")


def _first_top_level_comma(text: str) -> int:
    depth = 0
    in_quote = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"':
            in_quote = not in_quote
        elif not in_quote and char == "{":
            depth += 1
        elif not in_quote and char == "}":
            depth -= 1
        elif not in_quote and depth == 0 and char == ",":
            return index
    raise BibliographyParseError("BibTeX entry has no citation key separator")


def _parse_bibtex_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    while index < len(text):
        while index < len(text) and (text[index].isspace() or text[index] == ","):
            index += 1
        if index >= len(text):
            break
        name_match = re.match(r"[A-Za-z][A-Za-z0-9_-]*", text[index:])
        if name_match is None:
            raise BibliographyParseError(
                f"Invalid BibTeX field near {text[index:index + 20]!r}"
            )
        name = name_match.group(0).lower()
        index += len(name_match.group(0))
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] != "=":
            raise BibliographyParseError(f"BibTeX field {name} has no value")
        index += 1
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            raise BibliographyParseError(f"BibTeX field {name} has no value")

        if text[index] == "{":
            end = _matching_delimiter(text, index, "{", "}")
            value = text[index + 1 : end]
            index = end + 1
        elif text[index] == '"':
            start = index + 1
            index = start
            escaped = False
            while index < len(text):
                if escaped:
                    escaped = False
                elif text[index] == "\\":
                    escaped = True
                elif text[index] == '"':
                    break
                index += 1
            if index >= len(text):
                raise BibliographyParseError(f"Unbalanced quoted value for {name}")
            value = text[start:index]
            index += 1
        else:
            start = index
            while index < len(text) and text[index] != ",":
                index += 1
            value = text[start:index].strip()
        fields[name] = value.strip()
    return fields


def _parse_bibtex(text: str) -> list[SourceEntry]:
    entries: list[SourceEntry] = []
    string_macros: dict[str, str] = {}
    position = 0
    entry_start = re.compile(r"@(?P<kind>[A-Za-z]+)\s*(?P<opening>[({])")
    while match := entry_start.search(text, position):
        kind = match.group("kind").lower()
        opening = match.group("opening")
        closing = "}" if opening == "{" else ")"
        open_index = match.end() - 1
        close_index = _matching_delimiter(text, open_index, opening, closing)
        body = text[open_index + 1 : close_index]
        position = close_index + 1
        if kind in {"comment", "preamble"}:
            continue
        if kind == "string":
            for name, value in _parse_bibtex_fields(body).items():
                string_macros[name] = latex_to_text(value) or value
            continue
        comma = _first_top_level_comma(body)
        key = body[:comma].strip()
        fields = _parse_bibtex_fields(body[comma + 1 :])
        fields = {
            name: string_macros.get(value.strip().lower(), value)
            for name, value in fields.items()
        }
        author_value = fields.get("author", "")
        authors = [
            latex_to_text(author.strip())
            for author in re.split(r"\s+and\s+", author_value, flags=re.IGNORECASE)
            if author.strip()
        ]
        pages = fields.get("pages") or fields.get("page") or fields.get("eid")
        page = (
            re.split(r"-{1,2}|\N{EN DASH}", pages, maxsplit=1)[0].strip()
            if pages
            else None
        )
        archive_prefix = normalize_doi(fields.get("archiveprefix"))
        eprint = fields.get("eprint")
        arxiv = (
            normalize_arxiv(eprint)
            if eprint and (archive_prefix == "arxiv" or "." in eprint)
            else None
        )
        year_text = latex_to_text(fields.get("year", ""))
        year_match = re.search(r"(?:18|19|20)\d{2}", year_text)
        try:
            entries.append(
                SourceEntry(
                    key=key,
                    raw=text[match.start() : close_index + 1],
                    authors=authors,
                    authors_truncated=False,
                    year=int(year_match.group(0)) if year_match else None,
                    journal=latex_to_text(fields.get("journal", ""))
                    or fields.get("journal"),
                    volume=latex_to_text(fields.get("volume", "")) or None,
                    page=latex_to_text(page) if page else None,
                    title=latex_to_text(fields.get("title", "")) or None,
                    doi=normalize_doi(fields.get("doi")) or None,
                    arxiv=arxiv,
                )
            )
        except ValidationError as exc:
            raise BibliographyParseError(str(exc)) from exc
    return entries


def parse_bibliography(path: Path) -> list[SourceEntry]:
    """Parse a supported bibliography file into normalized source entries."""

    suffix = path.suffix.lower()
    if suffix not in {".tex", ".bbl", ".bib"}:
        raise BibliographyParseError(
            f"Unsupported bibliography extension {path.suffix or '<none>'}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BibliographyParseError(f"Cannot read {path}: {exc}") from exc
    entries = _parse_bibtex(text) if suffix == ".bib" else _parse_bibitems(text)
    if not entries:
        raise BibliographyParseError("No bibliography entries found")
    return entries
