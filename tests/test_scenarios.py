from __future__ import annotations

import json

from refcheck.models import ADSRecord, RunConfig, SearchResponse, Verdict
from refcheck.outputs import write_outputs
from refcheck.parsers import parse_bibliography
from refcheck.resolver import Resolver
from refcheck.service import check_entries, run_check


def _load_response(path):
    payload = json.loads(path.read_text(encoding="utf-8"))["response"]
    return SearchResponse(
        num_found=payload["numFound"],
        records=[ADSRecord.model_validate(record) for record in payload["docs"]],
    )


class FixtureADS:
    def __init__(self, fixture_dir):
        self.responses = {
            "Ouyang": _load_response(fixture_dir / "ouyang.json"),
            "Ramirez": _load_response(fixture_dir / "ramirez.json"),
            "Radica": _load_response(fixture_dir / "radica.json"),
            "Fakerson": _load_response(fixture_dir / "not_found.json"),
        }
        self.export_text = json.loads(
            (fixture_dir / "export.json").read_text(encoding="utf-8")
        )["export"]
        self.queries = []
        self.exported = []

    def search(self, query):
        self.queries.append(query)
        for surname, response in self.responses.items():
            if surname in query:
                return response
        return SearchResponse(num_found=0, records=[])

    def export_bibtex(self, bibcodes):
        self.exported.append(bibcodes)
        return self.export_text

    def close(self):
        return None


def test_required_recorded_scenarios_are_safe_and_complete(
    tmp_path, fixture_dir
):
    entries = parse_bibliography(fixture_dir.parent / "references.bbl")
    ads = FixtureADS(fixture_dir)

    run = check_entries(entries, Resolver(ads), ads)
    write_outputs(run, tmp_path)

    assert [result.verdict for result in run.results] == [
        Verdict.CONFIRMED,
        Verdict.CONFIRMED,
        Verdict.CORRECTED,
        Verdict.NOT_FOUND,
    ]
    radica = run.results[2]
    [author_diff] = [
        difference
        for difference in radica.differences
        if difference.field == "author_order"
    ]
    assert "Albert: ours position 2 -> ADS position 10" in author_diff.details
    assert ads.exported == [
        [
            "2025ApJ...985L..43O",
            "2014ApJ...797L..25R",
            "2023MNRAS.524..835R",
        ]
    ]
    assert (tmp_path / "corrected.bib").read_text(encoding="utf-8") == (
        ads.export_text
    )
    assert all(path.exists() for path in [
        tmp_path / "report.md",
        tmp_path / "results.json",
        tmp_path / "corrected.bib",
        tmp_path / "trace.jsonl",
    ])


def test_run_check_orchestrates_parser_resolver_export_and_outputs(
    tmp_path, fixture_dir, monkeypatch
):
    source = tmp_path / "one.bbl"
    source.write_text(
        "\\begin{thebibliography}{1}\n"
        "\\bibitem[Ouyang et al.(2025)]{ouyang}\n"
        "Ouyang, Y., Ding, F., Yang, J., 2025, ApJL, 985, L43\n"
        "\\end{thebibliography}\n",
        encoding="utf-8",
    )
    ads = FixtureADS(fixture_dir)
    monkeypatch.setattr("refcheck.service.ADSClient", lambda **kwargs: ads)
    output_dir = tmp_path / "output"

    run = run_check(
        RunConfig(
            input_path=source,
            output_dir=output_dir,
            cache_dir=tmp_path / "cache",
            ads_token="test-token",
        )
    )

    assert run.results[0].verdict == Verdict.CONFIRMED
    assert (output_dir / "results.json").exists()
    assert (output_dir / "corrected.bib").read_text(encoding="utf-8") == (
        ads.export_text
    )
