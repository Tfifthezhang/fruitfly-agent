"""One offline comparison of configured components, backend support and edit scope."""
from pathlib import Path
import tempfile

from fruitfly_agent.lab.catalog import builtin_catalog, resolve_harness, configuration_inventory
from fruitfly_agent.lab.improvement.execution import builtin_executions


def validate_harness(config, profile, source, *, operation, environment, catalog=None):
    catalog = catalog or builtin_catalog()
    inventory = resolve_harness(profile, catalog)
    if source.task_set is not None:
        bindings = source.task_set.bindings
        capabilities = frozenset.intersection(*(b.capabilities for b in bindings))
        roles = frozenset.intersection(*(b.roles for b in bindings))
    elif source.benchmark is not None:
        from fruitfly_eval.improvement import benchmark_execution
        definition = benchmark_execution(source.benchmark.source_request, source.benchmark.generated_host,
            runtime_override=source.benchmark.request.runtime)
        capabilities, roles = definition.capabilities_for(inventory.tools), definition.roles
    else:
        definition = builtin_executions().get(source.execution_id)
        capabilities, roles = definition.capabilities_for(inventory.tools), definition.roles
    if operation != 'eval':
        inventory.select(config.improvement.components, capabilities, roles)
        for name, options in config.improvement.component_options.items():
            # Options are owned by the registered component, not interpreted by the CLI.
            spec = next(c for c in inventory.components if c.component_id == name)
            owner = catalog.get(dict(inventory.owners)[name])
            if owner.component_validator is None:
                raise ValueError('component has no option validator: ' + name)
            owner.component_validator(name, options, inventory)
    consumed = {slot for item in catalog.resolve(profile.mechanisms) for slot in item.definition.artifact_slots}
    consumed |= {c.component_id for c in inventory.components}
    if set(profile.artifact_bindings) - consumed:
        raise ValueError('artifact binding has no active consumer: ' + ', '.join(sorted(set(profile.artifact_bindings) - consumed)))
    # Exercise the actual Eval staging path, including bound artifact integrity.
    benchmarks = ([source.benchmark] if source.benchmark is not None else [])
    if source.task_set is not None:
        from fruitfly_eval.improvement.configuration import resolve_benchmark
        from dataclasses import replace
        benchmarks = [resolve_benchmark(replace(config, task={key: value for key, value in row.items()
            if key in {'source', 'request', 'host', 'model_calls'}}))
            for row in source.task_set.specifications if row['source'] == 'eval']
    for benchmark in benchmarks:
        from fruitfly_eval.runtime import prepare_runtime
        with tempfile.TemporaryDirectory(prefix='fruitfly-runtime-check-') as directory:
            prepare_runtime(runtime=benchmark.request.to_dict()['runtime'], output_dir=Path(directory), environment=environment)
    selected = set(config.improvement.components) if operation != 'eval' else set()
    rows = []
    for component in inventory.components:
        try:
            inventory.select((component.component_id,), capabilities, roles)
            reason = ''
        except ValueError as exc:
            reason = str(exc)
        rows.append({'id': component.component_id, 'role': component.role, 'owner': dict(inventory.owners)[component.component_id],
            'available': not reason, 'selected': component.component_id in selected, 'reason': reason})
    configuration = configuration_inventory(profile, catalog,
        artifact_reader=lambda reference: (Path(config.workspace) / '.fruitfly/artifacts' / reference[7:]).read_text(encoding='utf-8'))
    for component in configuration:
        component['authorized'] = component['id'] in selected
        component['edit_options'] = config.improvement.component_options.get(component['id'], {}) if operation != 'eval' else {}
    return {**inventory.to_dict(), 'identity': inventory.identity, 'editable_components': rows,
            'configuration': configuration,
            'component_options': config.improvement.component_options,
            'backend_capabilities': sorted(capabilities), 'backend_roles': sorted(roles)}
