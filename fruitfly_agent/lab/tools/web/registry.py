"""Explicit service factories and credential metadata; construction is offline."""
from dataclasses import dataclass
import re
from typing import Callable, cast

from .client import WebClient
from .contracts import FetchService, SearchService
from .services.brave import BraveSearch
from .services.deepseek import DeepSeekFetch, DeepSeekSearch
from .services.direct import DirectFetch
from .services.tavily import TavilySearch


@dataclass(frozen=True)
class WebServiceDefinition:
    name: str
    factory: Callable[[WebClient, str], SearchService | FetchService]
    api_key_env: str = ""

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", self.name):
            raise ValueError("web service name must be a stable identifier")
        if not callable(self.factory):
            raise TypeError("web service factory must be callable")
        if not isinstance(self.api_key_env, str) or self.api_key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.api_key_env):
            raise ValueError("api_key_env must name an environment variable")

    def credential_variable(self, override: str = "") -> str:
        if not isinstance(override, str) or override and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", override):
            raise ValueError("api_key_env must name an environment variable, not contain a key value")
        return (override or self.api_key_env) if self.api_key_env else ""


class WebServiceRegistry:
    def __init__(self, *, search=(), fetch=()):
        self._definitions: dict[tuple[str, str], WebServiceDefinition] = {}
        for kind, definitions in (("search", search), ("fetch", fetch)):
            for definition in definitions:
                key = kind, definition.name
                if key in self._definitions:
                    raise ValueError(f"duplicate web service: {key}")
                self._definitions[key] = definition

    def choices(self, kind: str) -> tuple[str, ...]:
        return tuple(name for operation, name in self._definitions if operation == kind)

    def get(self, kind: str, name: str) -> WebServiceDefinition:
        try:
            return self._definitions[kind, name]
        except KeyError:
            raise ValueError(f"unknown web {kind} service: {name!r}") from None

    def create_search(self, name: str, client: WebClient, api_key: str) -> SearchService:
        return cast(SearchService, self.get("search", name).factory(client, api_key))

    def create_fetch(self, name: str, client: WebClient, api_key: str = "") -> FetchService:
        return cast(FetchService, self.get("fetch", name).factory(client, api_key))


def default_service_registry() -> WebServiceRegistry:
    return WebServiceRegistry(search=(
        WebServiceDefinition("brave", BraveSearch, "BRAVE_SEARCH_API_KEY"),
        WebServiceDefinition("tavily", TavilySearch, "TAVILY_API_KEY"),
        WebServiceDefinition("deepseek", DeepSeekSearch, "DEEPSEEK_SEARCH_API_KEY"),
    ), fetch=(
        WebServiceDefinition("direct", DirectFetch),
        WebServiceDefinition("deepseek", DeepSeekFetch, "DEEPSEEK_FETCH_API_KEY"),
    ))


def web_api_key_variable(kind: str, backend: str, override: str = "") -> str:
    """Resolve a built-in service's credential name without reading its value."""
    return default_service_registry().get(kind, backend).credential_variable(override)
