"""Store and validate facts through the existing diagnostic-resource contract."""
from dataclasses import asdict, replace
import json
import hashlib

from ..contracts.facts import ArtifactFact, BudgetFact, ExecutionFacts
from ..contracts.tasks import Resource

FACTS_PATH = 'execution-facts.json'


def matches(facts, record):
    return all(getattr(facts, name) == getattr(record, name) for name in
        ('run_id', 'task_id', 'material_id', 'harness_id', 'conditions_id', 'initial_state_id', 'status'))


def read_facts(record, artifacts):
    entries = [r for r in record.artifacts if r.path == FACTS_PATH]
    if not entries:
        return None
    if len(entries) != 1 or entries[0].kind != 'diagnostic':
        raise ValueError('an execution needs one diagnostic facts reference')
    facts = ExecutionFacts.from_dict(json.loads(artifacts.read(entries[0].artifact_id)))
    if not matches(facts, record):
        raise ValueError('execution facts identity differs from its receipt')
    granted = {r.artifact_id for r in record.artifacts if r.path != FACTS_PATH}
    if any(r.artifact_id not in granted for r in facts.evidence):
        raise ValueError('execution facts cite evidence outside the receipt grant')
    if facts.output_id and facts.output_id != 'sha256:' + hashlib.sha256(record.output.encode('utf-8')).hexdigest():
        raise ValueError('execution facts output differs from the recorded output')
    return facts


def attach_facts(record, facts, artifacts):
    if not matches(facts, record):
        raise ValueError('cannot attach facts from a different execution')
    if any(r.path == FACTS_PATH for r in record.artifacts):
        raise ValueError('execution facts already exist')
    reference = artifacts.put(facts.serialize())
    return replace(record, artifacts=(*record.artifacts,
        Resource(FACTS_PATH, reference, 'application/json', 'diagnostic')))


def receipt_facts(record, artifact_store, **values):
    """Unknown backends retain unknown termination and accounting, not guessed success."""
    return ExecutionFacts(**{name: getattr(record, name) for name in
        ('run_id', 'task_id', 'material_id', 'harness_id', 'conditions_id', 'initial_state_id', 'status')},
        evidence=record.artifacts, output_id=artifact_store.put(record.output.encode('utf-8')),
        **{'budgets': (BudgetFact('model_calls', 'execution', record.model_calls, source='execution receipt'),),
           'artifacts': tuple(ArtifactFact(r.path, 'collected', 'execution receipt', r.artifact_id)
                for r in record.artifacts if r.kind == 'deliverable'), **values})


def ensure_facts(record, artifacts):
    if read_facts(record, artifacts) is not None:
        return record
    return attach_facts(record, receipt_facts(record, artifacts), artifacts)


def loop_fact_values(diagnostics):
    if diagnostics is None:
        return {}
    data = asdict(diagnostics)
    counters = tuple((name, data[name]) for name in ('provider_attempts', 'provider_failures',
        'tool_requests', 'tool_attempts', 'tool_started', 'tool_errors', 'tool_denied',
        'tool_budget_skipped', 'tool_output_skipped'))
    return {'termination_reason': diagnostics.termination_reason, 'counters': counters,
        'complete': True, 'budgets': (
            BudgetFact('tool_calls', 'turn', diagnostics.last_turn_tool_attempts,
                       diagnostics.tool_limit_per_turn, 'Core loop diagnostics'),)}
