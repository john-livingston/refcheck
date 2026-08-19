from __future__ import annotations

from collections.abc import Iterable

from refcheck.ads import ADSClient
from refcheck.cache import DiskCache
from refcheck.llm import OpenRouterClient
from refcheck.models import RunConfig, RunResult, SourceEntry
from refcheck.outputs import write_outputs
from refcheck.parsers import parse_bibliography
from refcheck.resolver import ADSLike, Resolver
from refcheck.trace import TraceWriter


class ExportingADS(ADSLike):
    def export_bibtex(self, bibcodes: list[str]) -> str: ...


def check_entries(
    entries: Iterable[SourceEntry],
    resolver: Resolver,
    ads: ExportingADS,
    *,
    use_llm: bool = False,
) -> RunResult:
    """Resolve entries sequentially and export every unique matched ADS record."""

    results = [resolver.resolve(entry, use_llm=use_llm) for entry in entries]
    bibcodes: list[str] = []
    for result in results:
        if result.record is not None and result.record.bibcode not in bibcodes:
            bibcodes.append(result.record.bibcode)
    corrected_bib = ads.export_bibtex(bibcodes) if bibcodes else ""
    return RunResult(results=results, corrected_bib=corrected_bib)


def run_check(config: RunConfig) -> RunResult:
    """Run one configured check and write all output artifacts."""

    config.output_dir.mkdir(parents=True, exist_ok=True)
    trace = TraceWriter(config.output_dir / "trace.jsonl", reset=True)
    ads = ADSClient(
        token=config.ads_token.get_secret_value(),
        cache=DiskCache(config.cache_dir),
        trace=trace,
    )
    llm = None
    try:
        if config.use_llm:
            if config.openrouter_api_key is None or not config.openrouter_model:
                raise ValueError("OpenRouter configuration is required with LLM assistance")
            llm = OpenRouterClient(
                api_key=config.openrouter_api_key.get_secret_value(),
                model=config.openrouter_model,
                trace=trace,
            )
        entries = parse_bibliography(config.input_path)
        run = check_entries(
            entries,
            Resolver(ads, llm=llm),
            ads,
            use_llm=config.use_llm,
        )
        write_outputs(run, config.output_dir)
        return run
    finally:
        ads.close()
        if llm is not None:
            llm.close()
