"""Translate structured Agent receipts; never inspect private verifier contents."""
from dataclasses import replace
import json
from pathlib import Path

from fruitfly_agent.core.data_model import LoopDiagnostics
from fruitfly_agent.lab.improvement.api import (
    ArtifactFact, BudgetFact, Resource, attach_facts, loop_fact_values, receipt_facts)


def attach_benchmark_facts(record, root, artifacts, *, model_limit):
    sessions = list(Path(root).glob('artifacts/harbor/*/*/agent/session.jsonl'))
    evidence = list(record.artifacts)
    values = {}
    collected = []
    if len(sessions) == 1 and sessions[0].is_file() and not sessions[0].is_symlink():
        session = sessions[0]
        diagnostics = None
        with session.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    continue
                item = json.loads(line)
                if item.get('kind') == 'runRecord' and item.get('event') == 'end':
                    raw = item.get('data', {}).get('diagnostics')
                    diagnostics = LoopDiagnostics(**raw) if isinstance(raw, dict) else None
        values = loop_fact_values(diagnostics)
        agent = session.parent
        for name in ('model-budget.json',):
            path = agent / name
            if path.is_file() and not path.is_symlink():
                evidence.append(Resource('agent/0/' + name, artifacts.put(path.read_bytes()),
                    'application/json', 'diagnostic'))
        manifest = agent.parent / 'artifacts/manifest.json'
        if manifest.is_file() and not manifest.is_symlink():
            data = manifest.read_bytes()
            evidence.append(Resource('artifact-collection.json', artifacts.put(data), 'application/json', 'diagnostic'))
            for item in json.loads(data):
                status = {'success': 'collected', 'collected': 'collected', 'empty': 'empty',
                          'failed': 'collection_failed', 'missing': 'absent'}.get(item.get('status'), 'unknown')
                collected.append(ArtifactFact(str(item.get('source') or item.get('destination') or 'unknown'),
                    status, 'Harbor artifact collection manifest'))
    values['budgets'] = (*values.get('budgets', ()), BudgetFact('model_calls', 'execution', record.model_calls,
        model_limit, 'Agent model-budget receipt; includes main and auxiliary Providers'))
    if collected:
        values['artifacts'] = tuple(collected)
    # Keep the same granted evidence in the record and facts. No verifier files enter either.
    record = replace(record, artifacts=tuple(evidence))
    facts = receipt_facts(record, artifacts, **values)
    return attach_facts(record, facts, artifacts)
