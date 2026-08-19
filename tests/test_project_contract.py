from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_secret_and_license_files_are_safe():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert ".env" in gitignore
    assert ".refcheck-cache/" in gitignore
    assert "ADS_TOKEN=" in example
    assert "OPENROUTER_API_KEY=" in example
    assert "OPENROUTER_MODEL=" in example
    assert "ads-super-secret" not in example
    assert "MIT License" in license_text


def test_readme_documents_boundary_outputs_and_live_gate():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "never supplies bibliographic field values" in readme
    assert all(name in readme for name in [
        "report.md",
        "results.json",
        "corrected.bib",
        "trace.jsonl",
    ])
    assert "ADS_TOKEN" in readme
    assert "OPENROUTER_API_KEY" in readme
