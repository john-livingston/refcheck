from __future__ import annotations

from refcheck.comparison import compare_entry
from refcheck.normalize import (
    authors_equivalent,
    journal_bibstem,
    normalize_journal,
    normalize_page,
)


def test_normalizes_accents_initials_conjunctions_and_pages():
    assert authors_equivalent(r"Lafreni\`ere, D.", "Lafrenière, David")
    assert authors_equivalent("Ramirez, R. M.", "Ramirez, Ramses M.")
    assert normalize_journal("ApJL") == normalize_journal(
        "The Astrophysical Journal Letters"
    )
    assert normalize_journal("ApJ Lett") == normalize_journal("ApJ")
    assert normalize_page("L43") == normalize_page("43")
    assert normalize_page("835--856") == normalize_page("835")
    assert journal_bibstem("ApJL") == "ApJL"
    assert journal_bibstem("ApJ Lett") == "ApJL"
    assert journal_bibstem("The Astrophysical Journal Letters") == "ApJL"
    assert journal_bibstem("The Astrophysical Journal") == "ApJ"


def test_ouyang_alias_and_letter_page_are_confirmed(source_factory, record_factory):
    differences = compare_entry(source_factory(), record_factory(page=["43"]))

    assert differences == []


def test_comparison_lists_every_core_field_change(source_factory, record_factory):
    source = source_factory(
        authors=["Other, A.", "Ding, F."],
        year=2024,
        journal="MNRAS",
        volume="984",
        page="L42",
    )

    differences = compare_entry(source, record_factory())

    assert {difference.field for difference in differences} == {
        "year",
        "journal",
        "volume",
        "page",
        "first_author",
        "author_order",
    }
    assert all(difference.ours is not None for difference in differences)
    assert all(difference.ads is not None for difference in differences)


def test_truncated_author_list_reports_explicit_ads_positions(
    source_factory, record_factory
):
    source = source_factory(
        key="radica",
        authors=["Radica, M.", "Albert, L.", "Taylor, J."],
        authors_truncated=True,
        year=2023,
        journal="MNRAS",
        volume="524",
        page="835",
    )
    ads_authors = [
        "Radica, Michael",
        "Welbanks, Luis",
        "Espinoza, Néstor",
        "Taylor, Jake",
        "Coulombe, Louis-Philippe",
        "Feinstein, Adina D.",
        "Goyal, Jayesh",
        "Scarsdale, Nicholas",
        "Baghel, Priyanka",
        "Albert, Loïc",
    ]
    record = record_factory(
        bibcode="2023MNRAS.524..835R",
        author=ads_authors,
        first_author=ads_authors[0],
        year="2023",
        pub="Monthly Notices of the Royal Astronomical Society",
        volume="524",
        page=["835"],
    )

    differences = compare_entry(source, record)

    [author_diff] = [diff for diff in differences if diff.field == "author_order"]
    assert "Albert: ours position 2 -> ADS position 10" in author_diff.details
    assert "Taylor: ours position 3 -> ADS position 4" in author_diff.details


def test_full_author_order_accepts_and_or_ampersand(source_factory, record_factory):
    source = source_factory(
        authors=["Ramirez, R. M.", "Kaltenegger, L."],
        year=2014,
        journal="ApJ Lett",
        volume="797",
        page="L25",
    )
    record = record_factory(
        bibcode="2014ApJ...797L..25R",
        author=["Ramirez, Ramses M.", "Kaltenegger, Lisa"],
        first_author="Ramirez, Ramses M.",
        year="2014",
        pub="The Astrophysical Journal Letters",
        volume="797",
        page=["25"],
    )

    assert compare_entry(source, record) == []
