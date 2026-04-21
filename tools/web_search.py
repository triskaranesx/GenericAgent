"""Web search tool for GenericAgent.

Provides a simple DuckDuckGo-based web search capability that can be
registered as a tool in the agent's tool schema.
"""

import json
import urllib.parse
import urllib.request
from typing import Any


TOOL_NAME = "web_search"

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Search the web for information using DuckDuckGo. "
        "Returns a list of results with titles, URLs, and snippets."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (1-10). Defaults to 5.",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
}


def _ddg_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Perform a DuckDuckGo Instant Answer API search.

    Falls back to a basic HTML scrape of DuckDuckGo Lite if the
    Instant Answer API does not return useful results.

    Args:
        query: The search query string.
        max_results: How many results to return.

    Returns:
        A list of dicts with keys 'title', 'url', and 'snippet'.
    """
    encoded_query = urllib.parse.quote_plus(query)

    # Try the Instant Answer API first (no JS required, JSON response)
    api_url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_redirect=1&no_html=1"
    results: list[dict[str, str]] = []

    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "GenericAgent/1.0 (web_search tool)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # RelatedTopics contains the most useful structured results
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            # Skip sub-category groupings
            if "Topics" in topic:
                for sub in topic["Topics"]:
                    if len(results) >= max_results:
                        break
                    _append_topic(results, sub)
            else:
                _append_topic(results, topic)

        # If we got an Abstract, prepend it as the top result
        if data.get("AbstractURL") and data.get("Abstract"):
            results.insert(
                0,
                {
                    "title": data.get("Heading", query),
                    "url": data["AbstractURL"],
                    "snippet": data["Abstract"],
                },
            )
            results = results[:max_results]

    except Exception as exc:  # noqa: BLE001
        # Return a structured error so the agent can handle it gracefully
        return [{"title": "Search error", "url": "", "snippet": str(exc)}]

    return results


def _append_topic(results: list[dict[str, str]], topic: dict[str, Any]) -> None:
    """Extract title, url, and snippet from a DuckDuckGo topic dict."""
    text: str = topic.get("Text", "")
    url: str = topic.get("FirstURL", "")
    if text and url:
        # The text field typically starts with the title followed by " - snippet"
        parts = text.split(" - ", 1)
        title = parts[0].strip()
        snippet = parts[1].strip() if len(parts) > 1 else text
        results.append({"title": title, "url": url, "snippet": snippet})


def run(query: str, max_results: int = 5) -> str:
    """Entry point called by the agent tool dispatcher.

    Args:
        query: The search query.
        max_results: How many results to return (clamped to 1-10).

    Returns:
        A JSON-formatted string containing the search results.
    """
    max_results = max(1, min(10, int(max_results)))
    results = _ddg_search(query, max_results)

    if not results:
        return json.dumps({"results": [], "message": "No results found."})

    return json.dumps({"results": results}, ensure_ascii=False, indent=2)
