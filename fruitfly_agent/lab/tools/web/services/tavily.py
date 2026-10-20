"""Tavily basic search request and response adaptation."""
from ..client import WebClient
from ..contracts import SearchRequest
from .common import search_response, validate_api_key


class TavilySearch:
    name = "tavily"
    max_query_chars = 500
    query_description = "Search query, at most 500 characters and 60 words."

    def __init__(self, client: WebClient, api_key: str):
        validate_api_key(api_key)
        self.client, self._api_key = client, api_key

    async def search(self, request: SearchRequest, *, signal=None):
        payload = {"query": request.query, "max_results": request.count, "search_depth": "basic",
                   "include_answer": False, "include_raw_content": False, "include_domains": list(request.domains)}
        if request.freshness != "any":
            payload["time_range"] = request.freshness
        response, cached = await self.client.request("POST", "https://api.tavily.com/search", payload=payload,
            headers={"Authorization": "Bearer " + self._api_key}, signal=signal)
        return search_response(self.client, response, cached, self._api_key, lambda data: data["results"], ("content",))
