"""Public web search/fetch factories and explicitly owned HTTP resources."""
from .client import WebClient, WebConfig, WebError
from .fetch import create_web_fetch_tool
from .search import create_web_search_tool

__all__ = ["WebClient", "WebConfig", "WebError", "create_web_search_tool", "create_web_fetch_tool"]
