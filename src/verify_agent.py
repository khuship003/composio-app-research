"""
Pass 2: the verification loop.

Two independent checks feed into this, on purpose -- an agent checking its
own answer tends to rationalize it, so the critic runs as a *fresh* prompt
with no memory of pass 1's reasoning, and is scored against pass 1 rather
than trusted blindly:

  1. Critic pass (this module, `run_critic_pass`) -- for a sample of apps
     (oversampled toward low-confidence / has_mcp=true rows, since MCP
     status is the fastest-moving, most training-data-staleness-prone
     field), re-run search + fetch from scratch and re-extract, without
     ever showing the critic pass 1's answer. Diff the two.

  2. Human spot-check (`apply_human_overrides`) -- a CSV/dict of
     (app_id, field, corrected_value, source_url) pairs a person filled in
     by hand after reading real docs. This always wins over both agent
     passes, and is logged as such in `source_pass_notes` so the report
     never blurs "the agent got this right" with "a human fixed this."

Both passes write to `output/verification_results.json` in the same
per-field-check shape so report.py can compute one accuracy number instead
of reconciling two formats.
"""

from __future__ import annotations
import json
from dataclasses import dataclass

from .schema import AppRecord, Evidence
from .search_provider import SearchProvider
from .research_agent import research_one
from anthropic import Anthropic


@dataclass
class FieldCheck:
    app_id: int
    app_name: str
    field: str
    pass1_value: str
    verified_value: str
    correct_in_pass1: bool
    evidence_url: str
    checked_by: str  # "critic_agent" | "human"


CHECKED_FIELDS = [
    "self_serve", "auth_methods", "has_mcp", "mcp_status",
    "buildability_verdict", "api_surface_breadth",
]


def run_critic_pass(
    pass1_records: list[AppRecord],
    sample_ids: list[int],
    provider: SearchProvider,
    client: Anthropic,
) -> list[FieldCheck]:
    checks: list[FieldCheck] = []
    by_id = {r.id: r for r in pass1_records}

    for app_id in sample_ids:
        p1 = by_id[app_id]
        seed = {"id": p1.id, "name": p1.name, "category": p1.category, "hint": p1.hint}
        # Fresh research call -- the critic never sees pass 1's answer,
        # so it can't just agree with it.
        fresh = research_one(seed, provider, client)

        for f in CHECKED_FIELDS:
            v1 = getattr(p1, f)
            v2 = getattr(fresh, f)
            correct = (v1 == v2)
            checks.append(FieldCheck(
                app_id=app_id,
                app_name=p1.name,
                field=f,
                pass1_value=json.dumps(v1) if not isinstance(v1, str) else v1,
                verified_value=json.dumps(v2) if not isinstance(v2, str) else v2,
                correct_in_pass1=correct,
                evidence_url=(fresh.evidence[0].url if fresh.evidence else ""),
                checked_by="critic_agent",
            ))
    return checks


def apply_human_overrides(
    records: list[AppRecord],
    overrides: list[dict],
) -> tuple[list[AppRecord], list[FieldCheck]]:
    """overrides: [{"app_id": int, "field": str, "value": Any, "evidence_url": str}, ...]
    Human overrides always win and are logged distinctly from agent checks."""
    by_id = {r.id: r for r in records}
    checks: list[FieldCheck] = []

    for o in overrides:
        rec = by_id[o["app_id"]]
        before = getattr(rec, o["field"])
        setattr(rec, o["field"], o["value"])
        rec.source_pass_notes += f" [human override: {o['field']}]"
        checks.append(FieldCheck(
            app_id=rec.id, app_name=rec.name, field=o["field"],
            pass1_value=json.dumps(before) if not isinstance(before, str) else before,
            verified_value=json.dumps(o["value"]) if not isinstance(o["value"], str) else o["value"],
            correct_in_pass1=(before == o["value"]),
            evidence_url=o.get("evidence_url", ""),
            checked_by="human",
        ))
    return list(by_id.values()), checks


def summarize(checks: list[FieldCheck], sample_ids: list[int]) -> dict:
    correct = sum(1 for c in checks if c.correct_in_pass1)
    apps_with_error = len({c.app_id for c in checks if not c.correct_in_pass1})
    apps_fully_confirmed = len(sample_ids) - apps_with_error
    return {
        "sample_size_apps": len(sample_ids),
        "sampled_app_ids": sample_ids,
        "field_level_checks_run": len(checks),
        "field_level_checks_correct_in_pass1": correct,
        "field_level_pass1_accuracy_on_sample": round(correct / len(checks), 3) if checks else None,
        "apps_with_at_least_one_pass1_error": apps_with_error,
        "apps_fully_confirmed": apps_fully_confirmed,
        "verification_method": (
            "Live web_search + web_fetch against each app's actual developer docs, "
            "run independently from the pass-1 answer (pass 1 was answered from "
            "training knowledge only, with no browsing)."
        ),
    }
