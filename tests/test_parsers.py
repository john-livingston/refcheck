from __future__ import annotations

import pytest

from refcheck.parsers import BibliographyParseError, parse_bibliography


@pytest.mark.parametrize("suffix", [".tex", ".bbl"])
def test_parse_bibitems_with_identifiers_and_et_al(tmp_path, suffix):
    source = tmp_path / f"references{suffix}"
    source.write_text(
        r"""
\begin{thebibliography}{99}
\bibitem[Ouyang et al.(2025)]{ouyang}
Ouyang, Y., Ding, F., Yang, J., 2025, ApJL, 985, L43,
doi:10.3847/2041-8213/adda4b

\bibitem[Radica et al.(2023)]{radica}
Radica, M., Albert, L., Taylor, J., et al., 2023, MNRAS, 524, 835

\bibitem[Ramirez \& Kaltenegger(2014)]{ramirez}
Ramirez, R. M. \& Kaltenegger, L., 2014, ApJL, 797, L25,
arXiv:1412.1764
\end{thebibliography}
""",
        encoding="utf-8",
    )

    entries = parse_bibliography(source)

    assert [entry.key for entry in entries] == ["ouyang", "radica", "ramirez"]
    assert entries[0].authors == ["Ouyang, Y.", "Ding, F.", "Yang, J."]
    assert entries[0].doi == "10.3847/2041-8213/adda4b"
    assert entries[1].authors == ["Radica, M.", "Albert, L.", "Taylor, J."]
    assert entries[1].authors_truncated is True
    assert entries[2].authors == ["Ramirez, R. M.", "Kaltenegger, L."]
    assert entries[2].arxiv == "1412.1764"


def test_parse_balanced_bibtex_fields(tmp_path):
    source = tmp_path / "references.bib"
    source.write_text(
        r"""
@article{ramirez2014,
  author = {Ramirez, Ramses M. and Kaltenegger, Lisa},
  title = {The {Habitable} Zones of {Pre-main-sequence} Stars},
  journal = "The Astrophysical Journal Letters",
  year = {2014},
  volume = 797,
  pages = {L25--L32},
  doi = {10.1088/2041-8205/797/2/L25},
  archivePrefix = {arXiv},
  eprint = {1412.1764}
}
""",
        encoding="utf-8",
    )

    [entry] = parse_bibliography(source)

    assert entry.key == "ramirez2014"
    assert entry.title == "The Habitable Zones of Pre-main-sequence Stars"
    assert entry.authors == ["Ramirez, Ramses M.", "Kaltenegger, Lisa"]
    assert entry.page == "L25"
    assert entry.arxiv == "1412.1764"


def test_parse_bibtex_skips_directives_and_expands_string_macro(tmp_path):
    source = tmp_path / "references.bib"
    source.write_text(
        r"""
@string{apjl = "The Astrophysical Journal Letters"}
@preamble{"Ignored preamble"}
@comment{This entry is not a citation}
@article{ouyang2025,
  author = {Ouyang, Yueyun and Ding, Feng and Yang, Jun},
  title = {Retention of Surface Water on Tidally Locked Rocky Planets},
  journal = apjl,
  year = {2025},
  volume = {985},
  pages = {L43}
}
""",
        encoding="utf-8",
    )

    [entry] = parse_bibliography(source)

    assert entry.key == "ouyang2025"
    assert entry.journal == "The Astrophysical Journal Letters"


def test_parser_rejects_unknown_or_empty_input(tmp_path):
    unknown = tmp_path / "references.txt"
    unknown.write_text("nothing", encoding="utf-8")
    empty = tmp_path / "empty.bib"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(BibliographyParseError, match="extension"):
        parse_bibliography(unknown)
    with pytest.raises(BibliographyParseError, match="No bibliography entries"):
        parse_bibliography(empty)
