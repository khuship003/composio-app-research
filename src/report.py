"""
Turns output/master_dataset.json into output/patterns.json -- the cluster
stats the case-study page's "Patterns" and "Matrix" sections read directly
(the HTML embeds this file's output verbatim; see gen_dataset.py).

Usage:
    python -m src.report
"""

from __future__ import annotations
import json
import os
from collections import Counter, defaultdict

OUT_DIR = "output"


def build_patterns(records: list[dict]) -> dict:
    n = len(records)

    auth_counter = Counter()
    for r in records:
        for a in r["auth_methods"]:
            auth_counter[a] += 1

    self_serve_dist = Counter(r["self_serve"] for r in records)
    verdict_dist = Counter(r["buildability_verdict"] for r in records)

    self_serve_by_cat = defaultdict(Counter)
    verdict_by_cat = defaultdict(Counter)
    for r in records:
        self_serve_by_cat[r["category"]][r["self_serve"]] += 1
        verdict_by_cat[r["category"]][r["buildability_verdict"]] += 1

    mcp_official = sum(1 for r in records if r["mcp_status"] == "official")
    mcp_community = sum(1 for r in records if r["mcp_status"] == "community")
    mcp_none = n - mcp_official - mcp_community

    blockers = Counter(r["blocker"] for r in records if r["blocker"])

    return {
        "n_apps": n,
        "auth_method_mentions": dict(auth_counter.most_common()),
        "self_serve_distribution": dict(self_serve_dist),
        "buildability_distribution": dict(verdict_dist),
        "self_serve_by_category": {k: dict(v) for k, v in self_serve_by_cat.items()},
        "buildability_by_category": {k: dict(v) for k, v in verdict_by_cat.items()},
        "mcp_official": round(100 * mcp_official / n),
        "mcp_community_only": round(100 * mcp_community / n),
        "mcp_none": round(100 * mcp_none / n),
        "top_blockers": blockers.most_common(8),
    }


def main():
    records = json.load(open(os.path.join(OUT_DIR, "master_dataset.json")))
    patterns = build_patterns(records)
    json.dump(patterns, open(os.path.join(OUT_DIR, "patterns.json"), "w"), indent=2)
    print(f"wrote output/patterns.json from {len(records)} records")
    print(f"  self-serve: {patterns['self_serve_distribution']}")
    print(f"  buildability: {patterns['buildability_distribution']}")


if __name__ == "__main__":
    main()
