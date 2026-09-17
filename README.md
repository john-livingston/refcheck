# refcheck

`refcheck` verifies bibliography entries in LaTeX `.tex`, `.bbl`, and `.bib` files against NASA ADS.

ADS is the only source of bibliographic facts. Deterministic resolution is the default. Optional LLM assistance may propose ADS query strings and select among records already returned by ADS. It never supplies bibliographic field values.

## Install

Python 3.11 or later is required.

```sh
python -m pip install .
```

Copy `.env.example` to `.env` and set `ADS_TOKEN`. Get a token from the [ADS API account page](https://ui.adsabs.harvard.edu/user/settings/token).

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` only when using `--llm`.

## Use

```sh
refcheck references.bbl
refcheck references.bib --output-dir build/refcheck
refcheck references.tex --llm
```

Each run writes:

* `report.md`, the readable verdict and correction report
* `results.json`, structured and versioned results
* `corrected.bib`, first-author surname plus year citation keys (e.g. `oberg2011`, `molliere2022a`) instead of ADS bibcode keys
* `trace.jsonl`, credential-free request and response events

`--bibcode-keys` keeps the ADS bibcode-derived citation keys in `corrected.bib` instead.

The persistent `.refcheck-cache` avoids repeated ADS queries. Cached responses do not consume the current quota. The client stops new requests when ADS reports no remaining requests.

Exit 0 means every entry is `CONFIRMED` or `CORRECTED`. Exit 1 means at least one entry is `AMBIGUOUS`, `NOT_FOUND`, or `UNRESOLVED`. Configuration, input, network, and API errors exit 2.

## Test

```sh
pytest
```

The test suite uses recorded ADS response shapes and never uses the network. Live ADS and OpenRouter checks require your API keys.
