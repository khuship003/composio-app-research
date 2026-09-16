"""
Pass 1: for each app, run four targeted searches, fetch the top pages,
and have an LLM extract the schema fields with a citation required for
every non-obvious claim.

This pass is intentionally allowed to be wrong. It is a fast first draft,
not the final answer -- verify_agent.py is what catches its mistakes, and
report.py is what shows the before/after. Treating pass 1 as disposable is
what makes the verification loop meaningful instead of decorative.
"""

from __future__ import annotations
import json
import os
from anthropic import Anthropic

from .schema import AppRecord, Evidence, blank
from .search_provider import SearchProvider

MODEL = "claude-sonnet-4-6"

QUERIES = [
    "{name} API developer documentation authentication",
    "{name} API self-serve free trial pricing access",
    "{name} REST API OR GraphQL API surface endpoints",
    "{name} MCP server OR Model Context Protocol",
]

EXTRACT_SYSTEM_PROMPT = """You are a careful API researcher. You will be given
search snippets and fetched page text about one software product. Extract a
JSON object matching this schema exactly:

{
  "one_liner": str,
  "auth_methods": [str],
  "self_serve": "self_serve" | "partial" | "gated" | "unknown",
  "self_serve_reasoning": str,
  "api_surface_type": str,
  "api_surface_breadth": "narrow" | "moderate" | "broad" | "very broad",
  "has_mcp": bool,
  "mcp_status": "official" | "community" | "none",
  "mcp_evidence": str,
  "buildability_verdict": "ready" | "partial" | "blocked" | "unknown",
  "blocker": str,
  "evidence": [{"url": str, "note": str}],
  "confidence": float
}

Rules:
- Only claim "self_serve" if a developer can get real credentials today,
  free or on a trial, with no sales conversation.
- "confidence" should be LOW (<0.5) if the provided text doesn't actually
  answer the question -- do not paper over missing evidence with a
  plausible-sounding guess.
- evidence[].url must be a URL that actually appeared in the provided text.
- Return ONLY the JSON object, nothing else.
"""


def research_one(seed: dict, provider: SearchProvider, client: Anthropic) -> AppRecord:
    record = blank(seed)

    # Composio-specific shortcut: if Composio already hosts a toolkit for
    # this app, that's a strong, first-party signal for auth + MCP status
    # that's worth surfacing before we trust anything scraped from docs.
    existing = provider.has_existing_toolkit(seed["name"])

    gathered_text = []
    for q_template in QUERIES:
        query = q_template.format(name=seed["name"])
        for r in provider.search(query, max_results=3):
            gathered_text.append(f"[{r.get('url')}] {r.get('title')}\n{r.get('snippet')}")
            page = provider.fetch(r.get("url", ""))
            if page:
                gathered_text.append(page[:3000])

    context = "\n\n---\n\n".join(gathered_text) or "(no search results returned)"
    if existing:
        context += f"\n\n[Composio toolkit catalog] Composio already hosts a toolkit " \
                   f"for '{existing['name']}' (slug: {existing['slug']}), auth schemes: " \
                   f"{existing['auth_schemes']}."

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=EXTRACT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"App: {seed['name']} ({seed['hint']})\n\n{context}"}],
    )
    raw = response.content[0].text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(raw)

    record.one_liner = parsed.get("one_liner", "")
    record.auth_methods = parsed.get("auth_methods", [])
    record.self_serve = parsed.get("self_serve", "unknown")
    record.self_serve_reasoning = parsed.get("self_serve_reasoning", "")
    record.api_surface_type = parsed.get("api_surface_type", "")
    record.api_surface_breadth = parsed.get("api_surface_breadth", "")
    record.has_mcp = parsed.get("has_mcp", False)
    record.mcp_status = parsed.get("mcp_status", "none")
    record.mcp_evidence = parsed.get("mcp_evidence", "")
    record.buildability_verdict = parsed.get("buildability_verdict", "unknown")
    record.blocker = parsed.get("blocker", "")
    record.evidence = [Evidence(**e) for e in parsed.get("evidence", [])]
    record.confidence = float(parsed.get("confidence", 0.0))
    record.pass_number = 1

    if record.confidence < 0.5 or not record.evidence:
        record.needs_human = True
        record.human_note = "Pass 1 had low confidence or no citable evidence — flag for a human/critic look."

    return record


def run_pass1(seed_path: str, out_path: str, provider: SearchProvider) -> list[AppRecord]:
    seeds = json.load(open(seed_path))
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    records = [research_one(s, provider, client) for s in seeds]
    json.dump([r.to_dict() for r in records], open(out_path, "w"), indent=2)
    return records
