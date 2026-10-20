"""Shared JSON adapter mechanics; no vendor selection or tool formatting."""
import json
from typing import Callable

from ..client import WebClient, WebError, WebResponse
from ..contracts import SearchHit, SearchResponse


def validate_api_key(api_key: str) -> None:
    if not isinstance(api_key, str) or not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
        raise ValueError("web service requires a nonempty API key without whitespace or control characters")


def search_response(client: WebClient, response: WebResponse, cached: bool, api_key: str,
                    rows: Callable[[dict], list], snippet_fields: tuple[str, ...]) -> SearchResponse:
    try:
        data = json.loads(response.body)
        if not isinstance(data, dict) or "error" in data:
            raise ValueError
        items = rows(data)
        if not isinstance(items, list):
            raise ValueError
        results = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                raise ValueError
            title = item.get("title", "")
            snippet = next((item.get(field) for field in snippet_fields if item.get(field)), "")
            results.append(SearchHit(
                title.replace(api_key, "[redacted]") if isinstance(title, str) else "",
                item["url"].replace(api_key, "REDACTED"),
                snippet.replace(api_key, "[redacted]") if isinstance(snippet, str) else ""))
        return SearchResponse(tuple(results), response.retrieved_at, cached)
    except (ValueError, KeyError, TypeError, UnicodeError):
        client.discard(response)
        raise WebError("invalid_response", "The search service returned an invalid result structure.") from None


def require_text(text: str) -> None:
    if not text.strip():
        raise WebError("empty_content", "No readable text was found. The page may need JavaScript or authentication.")
