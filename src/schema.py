"""
Shared record schema for the app-research pipeline.

Every app, in every pass, is coerced into this shape before it's written
to disk. Keeping one schema for pass-1, the critic pass, and the human
overlay means report.py never has to special-case where a field came from.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal

SelfServe = Literal["self_serve", "partial", "gated", "unknown"]
Verdict = Literal["ready", "partial", "blocked", "unknown"]
MCPStatus = Literal["official", "community", "none"]


@dataclass
class Evidence:
    url: str
    note: str = ""


@dataclass
class AppRecord:
    id: int
    name: str
    category: str
    hint: str

    one_liner: str = ""
    auth_methods: list[str] = field(default_factory=list)

    self_serve: SelfServe = "unknown"
    self_serve_reasoning: str = ""

    api_surface_type: str = ""
    api_surface_breadth: str = ""  # "narrow" | "moderate" | "broad" | "very broad"

    has_mcp: bool = False
    mcp_status: MCPStatus = "none"
    mcp_evidence: str = ""

    buildability_verdict: Verdict = "unknown"
    blocker: str = ""

    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0          # 0-1, agent's self-rated confidence
    pass_number: int = 1             # 1 = first pass, 2 = critic/verification pass
    source_pass_notes: str = ""      # what the critic pass changed, if anything

    needs_human: bool = False
    human_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def blank(seed: dict) -> AppRecord:
    """Start a record from a data/apps_seed.json row."""
    return AppRecord(id=seed["id"], name=seed["name"], category=seed["category"], hint=seed["hint"])
