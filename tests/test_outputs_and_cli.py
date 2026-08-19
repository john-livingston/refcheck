from __future__ import annotations

import json

from refcheck.cli import main
from refcheck.models import Resolution, RunResult, Verdict
from refcheck.outputs import write_outputs


def test_writes_all_artifacts_with_verbatim_bibtex(
    tmp_path, source_factory, record_factory
):
    corrected_bib = "@ARTICLE{exact,\n  title = {Verbatim from ADS}\n}\n"
    run = RunResult(
        results=[
            Resolution(
                source=source_factory(),
                verdict=Verdict.CONFIRMED,
                record=record_factory(),
            ),
            Resolution(
                source=source_factory(key="missing"), verdict=Verdict.NOT_FOUND
            ),
        ],
        corrected_bib=corrected_bib,
    )
    (tmp_path / "trace.jsonl").write_text('{"existing":true}\n', encoding="utf-8")

    write_outputs(run, tmp_path)

    assert (tmp_path / "corrected.bib").read_text(encoding="utf-8") == corrected_bib
    payload = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert [item["verdict"] for item in payload["results"]] == [
        "CONFIRMED",
        "NOT_FOUND",
    ]
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "# refcheck report" in report
    assert "CONFIRMED: 1" in report
    assert "NOT_FOUND: 1" in report
    assert (tmp_path / "trace.jsonl").read_text(encoding="utf-8") == (
        '{"existing":true}\n'
    )
    assert not list(tmp_path.glob("*.tmp"))


def test_report_lists_every_correction_detail(tmp_path, source_factory, record_factory):
    from refcheck.comparison import compare_entry

    source = source_factory(page="L44")
    record = record_factory()
    run = RunResult(
        results=[
            Resolution(
                source=source,
                verdict=Verdict.CORRECTED,
                record=record,
                differences=compare_entry(source, record),
            )
        ],
        corrected_bib="",
    )

    write_outputs(run, tmp_path)

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "page: L44 -> L43" in report


def test_cli_requires_ads_token(tmp_path, monkeypatch, capsys):
    source = tmp_path / "references.bbl"
    source.write_text("not parsed before configuration", encoding="utf-8")
    monkeypatch.delenv("ADS_TOKEN", raising=False)
    monkeypatch.setattr("refcheck.cli.load_dotenv", lambda: False)

    exit_code = main([str(source)])

    assert exit_code == 2
    assert "ADS_TOKEN is required" in capsys.readouterr().err


def test_cli_requires_llm_configuration_only_with_flag(tmp_path, monkeypatch, capsys):
    source = tmp_path / "references.bbl"
    source.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("ADS_TOKEN", "ads")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setattr("refcheck.cli.load_dotenv", lambda: False)

    exit_code = main([str(source), "--llm"])

    assert exit_code == 2
    assert "OPENROUTER_API_KEY and OPENROUTER_MODEL are required" in (
        capsys.readouterr().err
    )


def test_cli_exit_codes_gate_unverified_entries(
    tmp_path, monkeypatch, source_factory, record_factory
):
    source = tmp_path / "references.bbl"
    source.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("ADS_TOKEN", "ads")
    monkeypatch.setattr("refcheck.cli.load_dotenv", lambda: False)

    confirmed = RunResult(
        results=[
            Resolution(
                source=source_factory(),
                verdict=Verdict.CONFIRMED,
                record=record_factory(),
            )
        ]
    )
    monkeypatch.setattr("refcheck.cli.run_check", lambda config: confirmed)
    assert main([str(source)]) == 0

    for verdict in (Verdict.AMBIGUOUS, Verdict.NOT_FOUND, Verdict.UNRESOLVED):
        failed = RunResult(
            results=[Resolution(source=source_factory(), verdict=verdict)]
        )
        monkeypatch.setattr("refcheck.cli.run_check", lambda config, run=failed: run)
        assert main([str(source)]) == 1
