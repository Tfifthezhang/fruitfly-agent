"""Shared context assembly for restricted tool-using Agent roles."""
from dataclasses import replace
from fruitfly_agent.lab.catalog import AssemblyContext, assemble_role, bind_resource_reader, ResourceRegistry


def build_role_runtime(config, *, profile, catalog, session, workspace, tools,
                       provider_resolver, owned, page_characters, work_products=None, model_alias=None, artifacts=None):
    if model_alias is not None:
        profile = replace(profile, model_profile=model_alias, model_roles={**profile.model_roles, "executor": model_alias})
    if artifacts is not None:
        for reference, text in profile.artifact_contents.items():
            if artifacts.put_text(text).artifact_id != reference:
                raise ValueError('role artifact content identity differs')
    resources = ResourceRegistry(scope=str(session.path))
    owned.append(resources)
    tools = bind_resource_reader(tools, resources, page_characters=page_characters)
    config = replace(config, session=session, tools=tools)
    capabilities = frozenset({'resource-reader'}) if any(t.name == 'read' for t in tools) else frozenset()
    result, inventory = assemble_role(config, catalog=catalog, selections=profile.mechanisms,
        context=AssemblyContext(workspace=workspace, session=session, session_path=session.path,
            main_model=config.model, provider_resolver=provider_resolver,
            resources=resources, work_products=work_products, host_capabilities=capabilities, resource_sink=owned,
            artifact_bindings=profile.artifact_bindings,
            artifact_reader=artifacts.read_text if artifacts is not None else None,
            artifact_store=artifacts,
            component_settings=profile.component_settings, model_roles=profile.resolved_model_roles(profile.model_profile)))
    return result.config, result.context_pipeline, inventory
