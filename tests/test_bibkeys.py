from __future__ import annotations

import pytest

from refcheck.bibkeys import rewrite_bibtex_keys
from refcheck.models import ADSRecord


def _record(bibcode: str, *, first_author: str = "Ouyang, Yueyun", year=2025) -> ADSRecord:
    return ADSRecord(
        bibcode=bibcode,
        first_author=first_author,
        year=str(year) if year is not None else None,
    )


def _bib(keys: list[str]) -> str:
    entries = []
    for key in keys:
        entries.append(
            "@ARTICLE{" + key + ",\n"
            "       author = {Ouyang}, Yueyun},\n"
            "         year = 2025\n"
            "}"
        )
    return "\n\n".join(entries)


def test_distinct_surnames_keep_plain_base_keys():
    corrected = _bib(["2025ApJ...985L..43O", "2025ApJ...797L..25R", "2025A&A...999L...1M"])
    records = [
        _record("2025ApJ...985L..43O", first_author="Ouyang, Yueyun"),
        _record("2025ApJ...797L..25R", first_author="Ramirez, Ramses M."),
        _record("2025A&A...999L...1M", first_author="Murphy, Mia"),
    ]

    rewritten = rewrite_bibtex_keys(corrected, records)

    assert rewritten == _bib(["ouyang2025", "ramirez2025", "murphy2025"])


def test_duplicates_in_same_surname_year_get_letters():
    corrected = _bib(["2026A...172..66M", "2026A...173..67M", "2026A...174..68M", "2025A...200..10O"])
    records = [
        _record("2026A...172..66M", first_author="Murphy, Mia", year=2026),
        _record("2026A...173..67M", first_author="Murphy, Ned", year=2026),
        _record("2026A...174..68M", first_author="Murphy, Pat", year=2026),
        _record("2025A...200..10O", first_author="Ouyang, Yueyun", year=2025),
    ]

    rewritten = rewrite_bibtex_keys(corrected, records)

    assert rewritten == _bib(["murphy2026a", "murphy2026b", "murphy2026c", "ouyang2025"])


def test_non_ascii_surnames_are_transliterated_to_ascii():
    corrected = _bib(["2011ApJ...742....2Ö", "2022A&A...664A.132M"])
    records = [
        _record("2011ApJ...742....2Ö", first_author="Öberg, Karin I.", year=2011),
        _record("2022A&A...664A.132M", first_author="Mollière, Paul", year=2022),
    ]

    rewritten = rewrite_bibtex_keys(corrected, records)

    assert rewritten == _bib(["oberg2011", "molliere2022"])


def test_surname_without_ascii_letters_keeps_exported_key():
    corrected = _bib(["2025ApJ...985L..43O"])
    records = [_record("2025ApJ...985L..43O", first_author="张, 伟")]

    rewritten = rewrite_bibtex_keys(corrected, records)

    assert rewritten == _bib(["2025ApJ...985L..43O"])


def test_missing_first_author_keeps_exported_key():
    corrected = _bib(["2025ApJ...985L..43O"])
    records = [_record("2025ApJ...985L..43O", first_author="")]

    rewritten = rewrite_bibtex_keys(corrected, records)

    assert rewritten == _bib(["2025ApJ...985L..43O"])


def test_missing_year_keeps_exported_key():
    corrected = _bib(["2025ApJ...985L..43O"])
    records = [_record("2025ApJ...985L..43O", year=None)]

    rewritten = rewrite_bibtex_keys(corrected, records)

    assert rewritten == _bib(["2025ApJ...985L..43O"])


def test_entry_and_record_count_mismatch_raises():
    corrected = _bib(["2025ApJ...985L..43O", "2025ApJ...797L..25R"])
    records = [_record("2025ApJ...985L..43O"), _record("2025ApJ...797L..25R")]
    with_extra = corrected + "\n" + _bib(["2025A&A...999L...1M"])

    with pytest.raises(ValueError, match="3 entries for 2 resolved"):
        rewrite_bibtex_keys(with_extra, records)


def test_body_is_preserved_verbatim_except_key():
    corrected = (
        "@ARTICLE{2025ApJ...985L..43O,\n"
        "       author = {{Ouyang}, Yueyun and {Ding}, Feng},\n"
        "        title = {Retention of Surface Water},\n"
        "         year = 2025,\n"
        "       volume = {985},\n"
        "        pages = {L43}\n"
        "}"
    )
    records = [_record("2025ApJ...985L..43O")]

    rewritten = rewrite_bibtex_keys(corrected, records)

    assert rewritten.startswith("@ARTICLE{ouyang2025,")
    for original, renamed in zip(corrected.splitlines(), rewritten.splitlines()):
        assert original.replace("2025ApJ...985L..43O", "ouyang2025") == renamed
