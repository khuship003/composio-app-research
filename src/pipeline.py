"""
Orchestrates the full run:

  1. pass 1 over all 100 apps            -> output/pass1.json
  2. critic pass over a sampled subset   -> output/verification_results.json
  3. (manual step) human overrides       -> output/human_overrides.json
  4. merge + write master dataset        -> output/master_dataset.json
  5. compute patterns                    -> output/patterns.json  (src/report.py)

Usage:
    python -m src.pipeline --provider composio --verify-sample-size 18
"""

from __future__ import annotations
import argparse
import json
import os
import random

from .research_agent import run_pass1
from .verify_agent import run_critic_pass, apply_human_overrides, summarize
from .search_provider import get_provider
from anthropic import Anthropic

DATA_DIR = "data"
OUT_DIR = "output"


def choose_sample(records, sample_size: int) -> list[int]:
    """Oversample toward the riskiest rows: low pass-1 confidence, and any
    row that claims an official/community MCP server (MCP status is the
    field most likely to be stale relative to training data, since new MCP
    servers ship weekly). Fill the remainder randomly for an unbiased read
    on the rest of the dataset."""
    risky = [r.id for r in records if r.confidence < 0.6 or r.has_mcp]
    random.shuffle(risky)
    sample = risky[:sample_size]
    if len(sample) < sample_size:
        remaining = [r.id for r in records if r.id not in sample]
        random.shuffle(remaining)
        sample += remaining[: sample_size - len(sample)]
    return sorted(sample[:sample_size])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="composio", choices=["composio", "stub"])
    ap.add_argument("--verify-sample-size", type=int, default=18)
    ap.add_argument("--human-overrides", default=os.path.join(OUT_DIR, "human_overrides.json"))
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    provider = get_provider(args.provider)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print(f"[1/4] Pass 1 research over data/apps_seed.json ...")
    pass1 = run_pass1(
        seed_path=os.path.join(DATA_DIR, "apps_seed.json"),
        out_path=os.path.join(OUT_DIR, "pass1.json"),
        provider=provider,
    )
    print(f"      wrote {len(pass1)} records")

    print(f"[2/4] Critic pass over a sample of {args.verify_sample_size} apps ...")
    sample_ids = choose_sample(pass1, args.verify_sample_size)
    checks = run_critic_pass(pass1, sample_ids, provider, client)
    json.dump([c.__dict__ for c in checks], open(os.path.join(OUT_DIR, "verification_results.json"), "w"), indent=2)
    summary = summarize(checks, sample_ids)
    json.dump(summary, open(os.path.join(OUT_DIR, "verification_summary.json"), "w"), indent=2)
    print(f"      pass-1 field accuracy on sample: {summary['field_level_pass1_accuracy_on_sample']}")

    print(f"[3/4] Applying human overrides (if {args.human_overrides} exists) ...")
    records = pass1
    if os.path.exists(args.human_overrides):
        overrides = json.load(open(args.human_overrides))
        records, human_checks = apply_human_overrides(records, overrides)
        all_checks = json.load(open(os.path.join(OUT_DIR, "verification_results.json")))
        all_checks += [c.__dict__ for c in human_checks]
        json.dump(all_checks, open(os.path.join(OUT_DIR, "verification_results.json"), "w"), indent=2)
        print(f"      applied {len(overrides)} human overrides")
    else:
        print("      none found, skipping")

    print(f"[4/4] Writing master dataset ...")
    json.dump([r.to_dict() for r in records], open(os.path.join(OUT_DIR, "master_dataset.json"), "w"), indent=2)
    print("Done. Now run: python -m src.report")


if __name__ == "__main__":
    main()
