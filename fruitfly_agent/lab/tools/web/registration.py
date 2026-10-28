"""Catalog definitions; credential lookup stays with the injecting host."""
from dataclasses import replace
import re
from functools import partial

from fruitfly_agent.core.mechanisms import MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition, MechanismSetup, SetupCredential
from fruitfly_agent.improvement.contracts.versions import EXPERIMENT_BLOCKERS_COMPONENT
from .client import WebClient, WebConfig
from .registry import WebServiceRegistry, default_service_registry
from .fetch import create_web_fetch_tool
from .search import create_web_search_tool


def definitions(registry: WebServiceRegistry | None = None):
    registry = registry or default_service_registry()
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
        ("search", "Search the web", "Search public source URLs and bounded snippets through a configured service.", 25),
        ("fetch", "Fetch web pages", "Read public source text through a configured service with line pagination.", 26),
    ):
        params: tuple[ParameterDescriptor, ...] = common
        params += (
            ParameterDescriptor("backend", "choice", "Search service" if kind == "search" else "Fetch service",
                "Web service; API requests may incur charges.",
                "brave" if kind == "search" else "direct",
                choices=registry.choices(kind)),
            ParameterDescriptor("api_key_env", "string", "API key variable", "Secret variable name; blank uses the selected service default. Credential-free services ignore it.", ""),
        )
        result.append(MechanismDefinition(
            MechanismDescriptor("web-" + kind + "-tool", label, description,
                contributions=(MechanismContribution("capability", "tools"),), parameters=params,
                install_order=order, effects=MechanismEffects(uses_network=True, tools=("web_" + kind,),
                    cost_notice="Queries are sent to the selected search service and may incur charges." if kind == "search" else "Source URLs are sent to the configured fetch service; API requests may incur charges.")),
            partial(_install, kind=kind, registry=registry),
            implementation_id="web-" + kind + "-v3", implementation_path="fruitfly_agent/lab/tools/web/" + kind + ".py",
            documentation_path="fruitfly_agent/lab/tools/web/README.md",
            input_parameters=("backend", "api_key_env"),
            validate_parameters=_validate,
            credential_variables=partial(_credentials, kind=kind, registry=registry),
            setup=MechanismSetup(fields=("backend", "api_key_env"),
                guidance="Choose a service and optional key variable. Blank uses the current value; /clear restores the service default variable. API key input is hidden and excluded from history. Save configuration to write credentials to the workspace secret file.",
                credential_resolver=partial(_setup_credentials, kind=kind, registry=registry)),
        ))
    return tuple(result)


def _validate(parameters):
    WebConfig(**{k: v for k, v in parameters.items() if k in WebConfig.__dataclass_fields__})
    name = parameters.get("api_key_env", "")
    if not isinstance(name, str) or name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("api_key_env must name an environment variable, not contain a key value")


def _credentials(parameters, *, kind, registry):
    variable = registry.get(kind, parameters["backend"]).credential_variable(parameters["api_key_env"])
    return (variable,) if variable else ()


def _setup_credentials(parameters, *, kind, registry):
    names = _credentials(parameters, kind=kind, registry=registry)
    return tuple(SetupCredential("api_key_env", "API key",
        "Enter your service's API key. Stored as " + name + "; value hidden.",
        variable=name, allow_whitespace=False) for name in names)


def _install(state, context, parameters, *, kind, registry):
    options = {k: v for k, v in parameters.items() if k in WebConfig.__dataclass_fields__}
    names = _credentials(parameters, kind=kind, registry=registry)
    key = context.secret_resolver(names[0]) if names else ""
    client = context.own(WebClient(WebConfig(**options)))
    if kind == "search":
        tool = create_web_search_tool(service=registry.create_search(parameters["backend"], client, key))
    else:
        tool = create_web_fetch_tool(service=registry.create_fetch(parameters["backend"], client, key))
    state = replace(state, config=replace(state.config, tools=(*state.config.tools, tool)))
    state = state.with_component("web-" + kind + "-client", client)
    return state.with_component(EXPERIMENT_BLOCKERS_COMPONENT,
        (*state.components.get(EXPERIMENT_BLOCKERS_COMPONENT, ()), "Live web " + kind + " has no frozen response snapshot"))


__all__ = ["definitions"]
