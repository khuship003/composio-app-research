# Composio 100-app research agent

Research pipeline + verification loop behind the [Composio 100-App Research
Atlas](https://claude.ai/artifact/56L6ZEVN3HfwQAL87tsHzD) case study.

**tl;dr on what's in this repo:** a pass-1 research agent (search → extract →
record, over Composio's SDK), a critic pass that independently re-checks a
sample of the pass-1 answers against live docs, a place for human spot-checks
to override both, and a report step that turns the merged dataset into the
pattern stats the case-study page shows. `output/` already contains this
submission's real run — you can read the results with no setup, or rerun
the pipeline yourself with your own API keys.

## What the agent actually did, and where a human was needed

- **Pass 1** answered all 100 apps from training-knowledge-driven search +
  extraction (no live browsing was required to produce a first draft — that's
  the point of measuring it separately from pass 2).
- **Pass 2 (critic)** re-ran live `web_search` + `web_fetch` against real
  developer docs for a 25-app sample, oversampled toward low-confidence rows
  and every row claiming an MCP server (the fastest-moving, most
  training-data-staleness-prone field in the schema), and re-extracted from
  scratch without ever seeing pass 1's answer.
- **Result:** pass 1 was correct on 83 of 108 sampled field-level checks
  (**76.9%**) before verification. Verification corrected the master dataset
  for every field it caught wrong — see `output/verification_results.json`
  for the full list of hits and misses, and `output/verification_summary.json`
  for the rollup.
- **Where a human was needed:** 6 apps (Pumble, fanbasis, Waterfall.io,
  Paygent Connect, iPayX, Consensus) never resolved to a confident answer
  even after the critic pass — either no public developer docs exist, or the
  docs are ambiguous about self-serve access. These are flagged
  `needs_human: true` in `output/master_dataset.json` and reported as an
  honest finding on the case-study page, not papered over.

## Repo layout

```
data/apps_seed.json        the 100 apps, as given in the assignment brief
src/schema.py               shared record schema (dataclass), used by every pass
src/search_provider.py      Composio-SDK-backed search/fetch, + an offline stub
src/research_agent.py       pass 1: search -> LLM extract -> AppRecord
src/verify_agent.py         critic pass (independent re-check) + human overrides
src/pipeline.py             orchestrates pass 1 -> critic -> human -> merge
src/report.py                master_dataset.json -> patterns.json (cluster stats)
gen_dataset.py               reproduces this submission's output/ with no network/API keys
output/                     pass1.json, verification_results.json,
                             verification_summary.json, master_dataset.json,
                             patterns.json — this submission's actual run
```

## Reproduce this submission (no API keys needed)

The numbers on the case-study page are derived from `output/master_dataset.json`
and `output/verification_results.json`, which are checked into this repo as
the record of the actual research + verification performed. To prove
`patterns.json` (the cluster stats) is computed from that data rather than
hand-typed:

```bash
python gen_dataset.py   # stdlib only — no pip install, no .env needed
```

This recomputes `output/patterns.json` from `output/master_dataset.json` from
scratch, diffs it against the checked-in version, sanity-checks that all 100
app IDs agree between the seed list and the master dataset, and prints the
verification accuracy and the list of apps that stayed unresolved.

## Run the full pipeline against live APIs

To rerun the actual research (pass 1 + critic pass) from scratch, e.g. against
a different or updated set of apps:

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in COMPOSIO_API_KEY and ANTHROPIC_API_KEY

python -m src.pipeline --provider composio --verify-sample-size 18
python -m src.report
```

`--verify-sample-size` controls how many apps get the critic-pass re-check;
18-25 is a reasonable sample for a 100-app run (this submission used 25).

To add human spot-check corrections, write them to
`output/human_overrides.json` before running `src.pipeline` (or re-run
`src.verify_agent.apply_human_overrides` directly against an existing
`output/master_dataset.json`):

```json
[
  {"app_id": 90, "field": "self_serve", "value": "gated",
   "evidence_url": "https://pitchbook.com/data-solutions/api"}
]
```

Human overrides always win over both agent passes and are logged distinctly
in `source_pass_notes` and in `verification_results.json` (`checked_by:
"human"`), so the report never blurs "the agent got this right" with "a
human fixed this."

## Why Composio's SDK, specifically

The research target here — does an app have self-serve API auth? does it
already have an MCP server? — overlaps with Composio's own toolkit catalog.
`search_provider.ComposioSearchProvider.has_existing_toolkit()` checks that
catalog before the agent trusts anything scraped from prose docs, which is a
free, first-party signal that's more reliable than an LLM's read of a docs
page for the specific question "would this be a Composio toolkit today."

## Design notes / limitations

- Pass 1 runs from training knowledge plus whatever the search calls surface
  — it is deliberately treated as a fast, disposable first draft, not a
  source of truth.
- The critic-pass sample (25 of 100 apps, 108 field-level checks) is not
  exhaustive; `field_level_pass1_accuracy_on_sample` is an estimate of
  dataset-wide accuracy, not a guarantee for any specific unsampled row.
- A few apps (e.g. Sherlock, Mermaid CLI) are CLI tools with no hosted API at
  all — the schema still records them with `buildability_verdict: "blocked"`
  and an explicit blocker rather than a null/`unknown`, since "not an API"
  is itself a useful, confident finding.
