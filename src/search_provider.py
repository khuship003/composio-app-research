"""
Search/fetch provider used by the research agent.

Two implementations, same interface, so the rest of the pipeline never
knows which one it's talking to:

  ComposioSearchProvider  -- real runs. Uses Composio's own SDK to call a
                             web-search toolkit (and, where an app already
                             has a Composio-hosted MCP server, queries that
                             server directly for auth/scopes instead of
                             guessing from docs prose).
  StubSearchProvider      -- offline/CI runs and this submission's
                             gen_dataset.py. Returns nothing; the pipeline
                             falls back to whatever is already on disk.

Composio is the natural fit here specifically because the *target* of the
research (does this app have self-serve API auth? does it have an MCP
server already?) overlaps with Composio's own toolkit catalog -- so the
same SDK call that answers "can we search the web" can also answer
"does Composio already have a toolkit/MCP for this app," which is a
free, high-confidence signal the pipeline uses before trusting anything
scraped from docs.
"""

from __future__ import annotations
import os
from abc import ABC, abstractmethod


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Return [{title, url, snippet}, ...]."""

    @abstractmethod
    def fetch(self, url: str) -> str:
        """Return extracted page text for a single URL."""

    def has_existing_toolkit(self, app_name: str) -> dict | None:
        """Optional: check Composio's own toolkit directory for this app.
        Returns None if the provider doesn't support this lookup."""
        return None


class ComposioSearchProvider(SearchProvider):
    """
    Wraps Composio's SDK. Requires COMPOSIO_API_KEY and, for the LLM-driven
    extraction step in research_agent.py, ANTHROPIC_API_KEY.

    pip install composio-core anthropic
    """

    def __init__(self):
        from composio import Composio  # lazy import so the stub path has no hard dep

        api_key = os.environ["COMPOSIO_API_KEY"]
        self.client = Composio(api_key=api_key)
        # A user-scoped MCP/tool session gives the agent a real "web_search"
        # and "web_fetch" tool call, plus visibility into which toolkits
        # Composio already hosts.
        self.session = self.client.create(user_id="app-research-agent")

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        result = self.client.tools.execute(
            "COMPOSIO_SEARCH_SEARCH",
            arguments={"query": query, "num_results": max_results},
            user_id="app-research-agent",
        )
        return result.get("results", [])

    def fetch(self, url: str) -> str:
        result = self.client.tools.execute(
            "COMPOSIO_SEARCH_FETCH_URL",
            arguments={"url": url},
            user_id="app-research-agent",
        )
        return result.get("text", "")

    def has_existing_toolkit(self, app_name: str) -> dict | None:
        toolkits = self.client.toolkits.list(search=app_name)
        if not toolkits:
            return None
        top = toolkits[0]
        return {"slug": top.slug, "auth_schemes": top.auth_schemes, "name": top.name}


class StubSearchProvider(SearchProvider):
    """No network calls. Used by CI and by gen_dataset.py, which instead
    replays this submission's already-verified dataset from output/."""

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        return []

    def fetch(self, url: str) -> str:
        return ""


def get_provider(name: str = "composio") -> SearchProvider:
    if name == "composio":
        return ComposioSearchProvider()
    if name == "stub":
        return StubSearchProvider()
    raise ValueError(f"unknown provider: {name}")
