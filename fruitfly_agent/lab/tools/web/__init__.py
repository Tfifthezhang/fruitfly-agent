"""Public web tools, service contracts, registry and explicitly owned HTTP resources."""
from .client import WebClient, WebConfig, WebError
from .contracts import FetchResponse, FetchService, SearchHit, SearchRequest, SearchResponse, SearchService
from fruitfly_agent.lab.tools.methods.web_fetch.algorithm import create_web_fetch_tool
from fruitfly_agent.lab.tools.methods.web_search.algorithm import create_web_search_tool
from .registry import WebServiceDefinition, WebServiceRegistry, default_service_registry, web_api_key_variable

__all__ = [
    "WebClient", "WebConfig", "WebError", "create_web_search_tool", "create_web_fetch_tool",
    "FetchResponse", "FetchService", "SearchHit", "SearchRequest", "SearchResponse", "SearchService",
    "WebServiceDefinition", "WebServiceRegistry", "default_service_registry", "web_api_key_variable",
]
