from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
from rich.console import Console

from refcheck import __version__
from refcheck.models import RunConfig
from refcheck.service import run_check


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refcheck",
        description="Verify LaTeX bibliography entries against NASA ADS.",
    )
    parser.add_argument("input", type=Path, help="A .tex, .bbl, or .bib file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Artifact directory, default: current directory",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".refcheck-cache"),
        help="Persistent ADS cache directory, default: .refcheck-cache",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable constrained OpenRouter assistance after deterministic resolution",
    )
    parser.add_argument(
        "--author-year-keys",
        action="store_true",
        help=(
            "Use first-author surname plus year citation keys (e.g. Murphy2026) "
            "in corrected.bib; same-year duplicates get a, b, ... suffixes"
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console(stderr=True)
    load_dotenv()
    ads_token = os.getenv("ADS_TOKEN")
    if not ads_token:
        console.print("[red]error: ADS_TOKEN is required[/red]")
        return 2

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    openrouter_model = os.getenv("OPENROUTER_MODEL")
    if args.llm and (not openrouter_api_key or not openrouter_model):
        console.print(
            "[red]error: OPENROUTER_API_KEY and OPENROUTER_MODEL are required "
            "with --llm[/red]"
        )
        return 2

    config = RunConfig(
        input_path=args.input,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        ads_token=ads_token,
        use_llm=args.llm,
        author_year_keys=args.author_year_keys,
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
    )
    try:
        run = run_check(config)
    except Exception as exc:
        console.print(f"[red]error: {exc}[/red]")
        return 2
    for result in run.results:
        console.print(f"{result.source.key}: {result.verdict.value}")
    return 1 if run.has_unverified_entries else 0


def entrypoint() -> None:
    raise SystemExit(main())
