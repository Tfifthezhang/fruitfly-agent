"""Catalog definitions; credential lookup stays with the injecting host."""
from dataclasses import replace
import re

from fruitfly_agent.core.mechanisms import MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.improvement.contracts.versions import EXPERIMENT_BLOCKERS_COMPONENT
from .client import WebClient, WebConfig
from .fetch import create_web_fetch_tool
from .search import create_web_search_tool


def definitions():
    common = (
        ParameterDescriptor("timeout_seconds", "number", "Request deadline", "Total seconds including queue, DNS, retries and redirects.", 20, minimum=.01, maximum=120),
        ParameterDescriptor("max_retries", "integer", "Retries", "Additional attempts after transient HTTP/network failures.", 1, minimum=0, maximum=2),
        ParameterDescriptor("max_response_bytes", "integer", "Response bytes", "Maximum decoded response bytes.", 2_000_000, minimum=1, maximum=10_000_000),
        ParameterDescriptor("cache_ttl_seconds", "number", "Cache lifetime", "Seconds before a successful response expires; zero disables caching.", 300, minimum=0, maximum=3600),
        ParameterDescriptor("cache_entries", "integer", "Cache entries", "Maximum runtime-local responses; zero disables caching.", 32, minimum=0, maximum=128),
        ParameterDescriptor("max_redirects", "integer", "Redirect limit", "Maximum redirects for public page fetching; search redirects are always disabled.", 5, minimum=0, maximum=10),
    )
    result = []
    for kind, label, description, order in (
        ("search", "Search the web", "Search Brave or Tavily for public source URLs and bounded snippets.", 25),
        ("fetch", "Fetch web pages", "Read public HTML and text sources with links and line pagination.", 26),
    ):
        params: tuple[ParameterDescriptor, ...] = common
        if kind == "search":
            params += (
                ParameterDescriptor("backend", "choice", "Search service", "Search API service; requests may incur service charges.", "brave", choices=("brave", "tavily")),
                ParameterDescriptor("api_key_env", "string", "API key variable", "Secret environment variable name; blank uses BRAVE_SEARCH_API_KEY or TAVILY_API_KEY for the selected service.", ""),
            )
        result.append(MechanismDefinition(
            MechanismDescriptor("web-" + kind + "-tool", label, description,
                contributions=(MechanismContribution("capability", "tools"),), parameters=params,
                install_order=order, effects=MechanismEffects(uses_network=True, tools=("web_" + kind,),
                    cost_notice="Queries are sent to the selected search service and may incur charges." if kind == "search" else "Source URLs are fetched over the network.")),
            _install_search if kind == "search" else _install_fetch,
            implementation_id="web-" + kind + "-v1", implementation_path="fruitfly_agent/lab/tools/web/" + kind + ".py",
            documentation_path="fruitfly_agent/lab/tools/web/README.md",
            input_parameters=("backend", "api_key_env") if kind == "search" else (),
            validate_parameters=_validate,
        ))
    return tuple(result)


def _validate(parameters):
    WebConfig(**{k: v for k, v in parameters.items() if k in WebConfig.__dataclass_fields__})
    name = parameters.get("api_key_env", "")
    if not isinstance(name, str) or name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("api_key_env must name an environment variable, not contain a key value")


def _install(state, context, parameters, kind):
    options = {k: v for k, v in parameters.items() if k in WebConfig.__dataclass_fields__}
    key = ""
    if kind == "search":
        variable = parameters["api_key_env"] or {"brave": "BRAVE_SEARCH_API_KEY", "tavily": "TAVILY_API_KEY"}[parameters["backend"]]
        key = (context.secret_resolver(variable) or "") if context.secret_resolver is not None else ""
        if not key:
            raise ValueError(f"web search requires {variable} in the host secret environment; set it before enabling Search the web")
    client = context.own(WebClient(WebConfig(**options)))
    tool = create_web_search_tool(client, backend=parameters["backend"], api_key=key) if kind == "search" else create_web_fetch_tool(client)
    state = replace(state, config=replace(state.config, tools=(*state.config.tools, tool)))
    state = state.with_component("web-" + kind + "-client", client)
    return state.with_component(EXPERIMENT_BLOCKERS_COMPONENT,
        (*state.components.get(EXPERIMENT_BLOCKERS_COMPONENT, ()), "Live web " + kind + " has no frozen response snapshot"))


def _install_search(state, context, parameters):
    return _install(state, context, parameters, "search")


def _install_fetch(state, context, parameters):
    return _install(state, context, parameters, "fetch")


__all__ = ["definitions"]
