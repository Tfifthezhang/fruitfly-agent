"""Outer composition root. Optional Eval is imported only for its task source."""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
from typing import Any
import yaml

from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection, materialize_system, configuration_resources
from fruitfly_agent.lab.improvement.api import (WorkflowBindings, builtin_executions,
    builtin_completed_assessors, builtin_explorations, validate_process_configuration)
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.providers.workspace import WorkspacePaths
from fruitfly_agent.run.configuration import load_harness_config
from fruitfly_agent.run.configuration.resolution import model_catalog_path
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest

from .sources import resolve_source
from .policies import stop_policy


class PreparationUnavailable(RuntimeError):
    """Inputs are valid but the required external preparation is unavailable."""


@dataclass
class PreparedExperiment:
    config: Any
    operation: str
    source: Any
    profile: Any
    config_path: Path
    model_path: Path
    config_bytes: bytes
    model_bytes: bytes
    model_roles: dict
    environment: dict
    request: WorkflowRequest
    policy_id: str
    harness: dict | None = None
    resources: tuple = ()

    def summary(self):
        snapshot = self.config.snapshot()
        snapshot.update({'operation': self.operation, 'runtime_source': str(self.config_path),
            'profile': self.profile.profile_id, 'model_catalog': str(self.model_path),
            'model_roles': self.model_roles, 'request': asdict(self.request), 'policy_id': self.policy_id,
            'available': True, 'model_connectivity': 'not checked'})
        from fruitfly_agent.runtime_spec import execution_values
        snapshot['execution'] = execution_values(self.profile.execution)
        snapshot['harness'] = self.harness
        snapshot['runtime_hashes'] = {'config': hashlib.sha256(self.config_bytes).hexdigest(),
            'models': hashlib.sha256(self.model_bytes).hexdigest()}
        snapshot['configuration_sources'] = [{'path': source.path, 'sha256': source.digest}
            for source in (*self.profile.source_files, *self.config.source_files)]
        snapshot['configuration_resources'] = [{'path': entry.path, 'content_hash': entry.digest}
                                               for entry in self.resources]
        snapshot['sources'] = {**snapshot['sources'],
            **{'models.' + role: ('experiment override' if role in self.config.models else str(self.config_path))
                for role in self.model_roles}}
        snapshot['material_identity'] = self.source.source_identity
        if self.source.task_set is not None:
            material = self.source.task_set.snapshot
            snapshot['task_set'] = {'identity': material.snapshot_id,
                'collections': [{
                    'id': name, 'tasks': sum(e.collection_id == name for e in material.entries),
                    'development': sum(e.collection_id == name and e.partition == 'development' for e in material.entries),
                    'selection': sum(e.collection_id == name for e in material.selection_entries())}
                    for name in sorted({e.collection_id for e in material.entries})],
                'minimum_budget': self.source.minimum_budget,
                'tasks': [{'key': e.key, 'collection_id': e.collection_id, 'origin_id': e.origin_id,
                           'partition': e.partition, 'model_limit': e.model_limit} for e in material.entries],
                'candidate_concurrency': 1, 'executor_usage': 'provider calls; SDK retries and external grader calls are separate'}
        return json.loads(json.dumps(snapshot, ensure_ascii=False, allow_nan=False))

    def stage_runtime(self, directory):
        root = Path(directory) / 'runtime'
        root.mkdir(parents=True, exist_ok=False)
        def read(reference):
            if reference in self.profile.artifact_contents:
                return self.profile.artifact_contents[reference]
            return (self.config.workspace / '.fruitfly/artifacts' / reference[7:]).read_text(encoding='utf-8')
        return materialize_system(self.profile, root / 'config.yaml', artifact_reader=read,
            model_source=self.model_path, resources=self.resources)

    def verify_sources(self):
        for source in (*self.profile.source_files, *self.config.source_files):
            source.check()
        if self.config_path.read_bytes() != self.config_bytes or self.model_path.read_bytes() != self.model_bytes:
            raise ValueError('runtime configuration or model catalog changed after checking')
        if configuration_resources(self.profile, builtin_catalog(), self.config.workspace) != self.resources:
            raise ValueError('registered configuration resources changed after checking')
        if resolve_source(self.config, default_source='eval' if self.operation == 'eval' else 'files').source_identity != self.source.source_identity:
            raise ValueError('task material changed after checking')


def prepare_experiment(config, operation, *, require_prepared=True, environment=None, require_credentials=True):
    validate_process_configuration(config.process_assessment, config.exploration,
        builtin_completed_assessors(), builtin_explorations())
    source = resolve_source(config, default_source='eval' if operation == 'eval' else 'files')
    from fruitfly_agent.lab.improvement.api import MultiTaskSettings
    if source.task_set is None and config.multi_task != MultiTaskSettings():
        raise ValueError('nondefault multi_task settings require task.source: task-set')
    if source.task_set is not None and 'executor' in config.models and any(
            row['source'] == 'eval' for row in source.task_set.specifications):
        raise ValueError('select the shared executor in the Agent configuration; benchmark collections cannot use models.executor')
    if operation == 'eval' and source.benchmark is None:
        raise ValueError('Eval needs task.source: eval; use improvement for native tasks')
    if source.benchmark is not None and operation != 'eval':
        execution = source.benchmark.request.execution
        if execution.attempts != 1 or execution.concurrency != 1:
            raise ValueError('benchmark improvement requires one attempt and concurrency one')
    if source.benchmark is not None:
        if 'executor' in config.models:
            raise ValueError('select the benchmark executor in its Agent configuration; models.executor is for native tasks')
        config_path = Path(source.config_path or '.fruitfly/default-config.yaml')
        if not config_path.is_absolute():
            config_path = config.workspace / config_path
        profile_id = source.profile
    else:
        config_path = source.config_path or (config.resolve(config.runtime['config']) if 'config' in config.runtime else config.workspace / '.fruitfly/default-config.yaml')
        profile_id = source.profile or config.runtime.get('profile')
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise ValueError('Agent configuration missing: ' + str(config_path) +
            '; copy the default configuration/model examples or select an explicit configuration')
    harness = load_harness_config(config_path)
    profile = harness.select(profile_id)
    model_path = model_catalog_path(profile, config_path)
    specs = load_model_specs(model_path)
    executor = config.models.get('executor', profile.model_profile)
    if executor is None:
        if len(specs) != 1:
            raise ValueError('select the default Agent model explicitly')
        executor = next(iter(specs))
    profile = replace(profile, model_profile=executor)
    selected = list(profile.mechanisms)
    existing = next((s for s in selected if s.mechanism_id == 'component-improvement'), None)
    parameters = dict(existing.parameters) if existing is not None else {}
    for role in ('editor', 'assessor'):
        if role in profile.model_roles:
            parameters[role + '_profile'] = profile.model_roles[role]
    for role in ('editor', 'assessor') if operation != 'eval' else ():
        if role in config.models:
            parameters[role + '_profile'] = config.models[role]
    if operation != 'eval':
        selected = [s for s in selected if s.mechanism_id != 'component-improvement']
        selected.append(MechanismSelection('component-improvement', True, parameters))
    profile = replace(profile, mechanisms=tuple(selected))
    roles = {'executor': executor, **{role: parameters.get(role + '_profile') or executor for role in ('editor', 'assessor') if operation != 'eval'}}
    process_env = {**load_env(WorkspacePaths(config.workspace).secret_file()), **(os.environ if environment is None else environment)}
    catalog = builtin_catalog()
    required = {*roles.values(), *catalog.required_model_profiles(profile.mechanisms)}
    for name in required:
        if name not in specs:
            raise ValueError('unknown model catalog profile: ' + str(name))
        specs[name].require(streaming=True)
        if require_credentials and not process_env.get(specs[name].provider.api_key_env):
            raise ValueError('missing model credential variable: ' + specs[name].provider.api_key_env)
    catalog.resolve(profile.mechanisms)
    options = config.improvement
    if source.defaults:
        values = {name: value for name, value in source.defaults.items() if 'improvement.' + name not in config.sources}
        options = replace(options, **values)
        config = replace(config, improvement=options)
    persistent = operation != 'eval' and (operation == 'rsi' or options.scope == 'persistent')
    policy_id = config.rsi.policy
    if persistent:
        if not source.persistent_policy:
            raise ValueError(source.adoption_notice)
        if policy_id == 'auto':
            policy_id = source.persistent_policy
        elif policy_id != source.persistent_policy:
            raise ValueError('the selected execution does not provide that independent policy')
    else:
        policy_id = ''
    if operation != 'eval':
        if options.generator != 'agent-editor-v1':
            raise ValueError('the CLI provides agent-editor-v1; custom generators require registered composition')
        minimum = source.minimum_budget if persistent or source.task_set is not None else {'model': 8, 'execution': 2}
        for kind, limit in (('model', options.max_model_calls), ('execution', options.max_executions)):
            if minimum.get(kind, 0) > limit:
                raise ValueError(f'root {kind} budget is too small; need at least {minimum[kind]}')
        if source.required_components and options.components != source.required_components:
            raise ValueError('the execution requires components: ' + ', '.join(source.required_components))
        if set(options.components) & set(source.forbidden_components):
            raise ValueError('I changes require task.source: editor and downstream comparisons')
    feedback = ('scored' if source.measured else 'behavior') if options.feedback == 'auto' else options.feedback
    request = WorkflowRequest(source.instruction, source.input_paths, options.components,
        generator_id=options.generator, mode=options.mode, width=options.width, depth=options.rounds,
        verification=feedback, scope='persistent' if persistent else 'task', max_model_calls=options.max_model_calls,
        max_executions=options.max_executions, operation_timeout=options.operation_timeout, direction=options.direction,
        task_pack_id=source.material_id, execution_id=source.execution_id, execution_parameters=source.parameters,
        strategy_id=options.strategy, retain_experience=options.retain_experience)
    stop_policy(config.stop.get('improvement'))
    stop_policy(config.stop.get('rsi'))
    if source.benchmark is not None:
        if operation != 'eval' and (options.max_model_calls < 2 * source.benchmark.model_calls + 8 or options.max_executions < 2):
            raise ValueError('budget cannot fund a baseline, candidate and final comparison')
        if require_prepared:
            source.benchmark.require_host()
            from eval.api import check_evaluation
            result = check_evaluation(source.benchmark.request, host_config_path=source.benchmark.generated_host)
            if not result['available']:
                details = '; '.join(c['detail'] for c in result.get('checks', ()) if c.get('status') == 'failed')
                raise PreparationUnavailable('benchmark preparation is unavailable; run fruitfly-agent-lab eval prepare. ' + details)
            if operation != 'eval' and result.get('task_count') != 1:
                raise ValueError('benchmark improvement requires exactly one prepared task')
    if operation == 'rsi' and (config.rsi.max_model_calls < options.max_model_calls or config.rsi.max_executions < options.max_executions):
        raise ValueError('RSI total allowance must fund at least one declared search')
    from .validation import validate_harness
    inventory = validate_harness(config, profile, source, operation=operation,
        environment=process_env if require_credentials else None)
    return PreparedExperiment(config, operation, source, profile, config_path, model_path,
        config_path.read_bytes(), model_path.read_bytes(), roles, process_env, request, policy_id, inventory,
        configuration_resources(profile, catalog, config.workspace))


def application_factory(prepared, runtime_path, *, provider_registry=None):
    from fruitfly_agent.run import RunApplicationFactory
    executions = builtin_executions()
    if prepared.source.task_set is not None:
        executions.register(prepared.source.task_set.definition())
    if prepared.source.benchmark is not None:
        from eval.improvement import benchmark_execution
        benchmark = prepared.source.benchmark
        executions.register(benchmark_execution(benchmark.source_request, benchmark.require_host(),
            model_calls=benchmark.model_calls, runtime_override=benchmark.request.runtime))
    bindings = WorkflowBindings(executions=executions,
        stop_policy=stop_policy(prepared.config.stop.get('improvement')),
        process_assessment=prepared.config.process_assessment, exploration=prepared.config.exploration,
        component_options=prepared.config.improvement.component_options)
    return RunApplicationFactory(cwd=prepared.config.workspace, environment=prepared.environment,
        config_path=str(runtime_path), profile_id=prepared.profile.profile_id,
        provider_registry=provider_registry, improvement_bindings=bindings)
