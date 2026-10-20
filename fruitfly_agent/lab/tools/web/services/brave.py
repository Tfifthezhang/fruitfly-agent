"""Brave search request and response adaptation."""
from urllib.parse import urlencode

from ..client import WebClient, WebError
from ..contracts import SearchRequest
from .common import search_response, validate_api_key


def _rows(data):
    web = data.get("web", {})
    if not isinstance(web, dict) or "web" not in data and not isinstance(data.get("query"), dict):
        raise ValueError
    return web.get("results", [])


class BraveSearch:
    name = "brave"
    max_query_chars = 500
    query_description = "Search query, at most 500 characters and 60 words."

    def __init__(self, client: WebClient, api_key: str):
        validate_api_key(api_key)
        self.client, self._api_key = client, api_key

    async def search(self, request: SearchRequest, *, signal=None):
        query = request.query
        if request.domains:
            query += " (" + " OR ".join("site:" + domain for domain in request.domains) + ")"
        if len(query) > 600 or len(query.split()) > 75:
            raise WebError("invalid_arguments", "Query and domain filters exceed Brave's query limit; shorten them.")
        params = {"q": query, "count": request.count}
        if request.freshness != "any":
            params["freshness"] = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}[request.freshness]
        response, cached = await self.client.request("GET", "https://api.search.brave.com/res/v1/web/search?" + urlencode(params),
            headers={"X-Subscription-Token": self._api_key, "Accept": "application/json"}, signal=signal)
        return search_response(self.client, response, cached, self._api_key, _rows, ("description",))
