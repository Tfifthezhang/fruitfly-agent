"""DeepSeek search and Markdown fetch adaptation with independently injected keys."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

from ..client import WebClient, WebError, normalize_url
from ..contracts import FetchResponse, SearchRequest
from .common import require_text, search_response, validate_api_key


class DeepSeekSearch:
    name = "deepseek"
    max_query_chars = 128
    query_description = "Search query, at most 60 words and 128 characters including domain/date filters."

    def __init__(self, client: WebClient, api_key: str):
        validate_api_key(api_key)
        self.client, self._api_key = client, api_key

    async def search(self, request: SearchRequest, *, signal=None):
        query = request.query
        if request.domains:
            query += " (" + " OR ".join("site:" + domain for domain in request.domains) + ")"
        if request.freshness != "any":
            days = {"day": 1, "week": 7, "month": 30, "year": 365}[request.freshness]
            query += " after:" + (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        if len(query) > self.max_query_chars:
            raise WebError("invalid_arguments", "DeepSeek query including domain/date filters exceeds 128 characters; shorten it.")
        response, cached = await self.client.request("POST", "https://api.deepseek.com/v1/tools/search",
            payload={"query": query, "count": request.count, "need_content": False},
            headers={"Authorization": "Bearer " + self._api_key}, signal=signal)
        return search_response(self.client, response, cached, self._api_key, lambda data: data["results"], ("summary", "snippet"))


class DeepSeekFetch:
    description = ("Fetch a known public HTTP(S) URL through DeepSeek as untrusted Markdown with numbered lines. "
                   "Use to read a specific page, inspect documentation and verify details or quotations against the source. "
                   "Use offset/limit to continue. The returned URL is the requested source; DeepSeek does not report the final redirect URL.")

    def __init__(self, client: WebClient, api_key: str):
        validate_api_key(api_key)
        self.client, self._api_key = client, api_key

    async def fetch(self, url: str, *, signal=None):
        url = normalize_url(url)
        response, cached = await self.client.request("POST", "https://api.deepseek.com/v1/tools/fetch",
            payload={"url": url}, headers={"Authorization": "Bearer " + self._api_key}, signal=signal)
        try:
            data = json.loads(response.body)
            if (not isinstance(data, dict) or "error" in data or not isinstance(data.get("content"), str)
                    or not isinstance(data.get("title", ""), str)):
                raise ValueError
            title = data.get("title", "").replace(self._api_key, "[redacted]")[:300]
            text = data["content"].replace(self._api_key, "[redacted]")
            require_text(text)
        except WebError:
            self.client.discard(response)
            raise
        except (ValueError, UnicodeError):
            self.client.discard(response)
            raise WebError("invalid_response", "DeepSeek fetch returned an invalid result structure.") from None
        return FetchResponse(title, text, url, None, hashlib.sha256(response.body).hexdigest(), response.retrieved_at, cached)
