from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from refcheck.models import RunResult, Verdict


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _report(run: RunResult) -> str:
    counts = Counter(result.verdict for result in run.results)
    lines = ["# refcheck report", "", "## Summary", ""]
    for verdict in Verdict:
        lines.append(f"- {verdict.value}: {counts[verdict]}")
    lines.extend(["", "## Entries", ""])
    for result in run.results:
        lines.append(f"### {result.source.key}: {result.verdict.value}")
        lines.append("")
        if result.record is not None:
            lines.append(f"ADS bibcode: `{result.record.bibcode}`")
            lines.append("")
        if result.stage is not None:
            lines.append(f"Resolution stage: `{result.stage.value}`")
            lines.append("")
        if result.candidates:
            lines.append("Candidates: " + ", ".join(f"`{item}`" for item in result.candidates))
            lines.append("")
        if result.differences:
            lines.append("Corrections:")
            lines.append("")
            for difference in result.differences:
                ours = difference.ours if difference.ours is not None else "missing"
                ads = difference.ads if difference.ads is not None else "missing"
                lines.append(f"- {difference.field}: {ours} -> {ads}")
                for detail in difference.details:
                    lines.append(f"  - {detail}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(run: RunResult, output_dir: Path) -> None:
    """Write stable result artifacts while preserving the request trace."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_payload = {
        "schema_version": run.schema_version,
        "results": [result.model_dump(mode="json") for result in run.results],
    }
    _atomic_write(output_dir / "report.md", _report(run))
    _atomic_write(
        output_dir / "results.json",
        json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write(output_dir / "corrected.bib", run.corrected_bib)
    (output_dir / "trace.jsonl").touch(exist_ok=True)
