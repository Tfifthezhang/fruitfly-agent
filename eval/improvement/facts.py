"""Translate structured Agent receipts; never inspect private verifier contents."""
from dataclasses import replace
import json
from pathlib import Path

from fruitfly_agent.core.data_model import LoopDiagnostics
from fruitfly_agent.lab.improvement.api import (
    ArtifactFact, BudgetFact, Resource, attach_facts, loop_fact_values, receipt_facts)


def attach_benchmark_facts(record, root, artifacts, *, model_limit, interrupted=False):
    sessions = list(Path(root).glob('artifacts/harbor/*/*/agent/session.jsonl'))
    evidence = list(record.artifacts)
    values = {}
    collected = []
    if (len(sessions) == 1 and sessions[0].is_file() and not sessions[0].is_symlink()
            and sessions[0].resolve().is_relative_to(Path(root).resolve())):
        session = sessions[0]
        diagnostics = None
        tool_results = 0
        with session.open(encoding='utf-8', errors='replace' if interrupted else 'strict') as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError('session entry must be an object')
                except ValueError:
                    if interrupted:
                        continue
                    raise
                message = item.get('message')
                if isinstance(message, dict) and message.get('role') == 'toolResult':
                    tool_results += 1
                if item.get('kind') == 'runRecord' and item.get('event') == 'end':
                    raw = item.get('data', {}).get('diagnostics')
                    try:
                        diagnostics = LoopDiagnostics(**raw) if isinstance(raw, dict) else None
                    except (TypeError, ValueError):
                        if not interrupted:
                            raise
                        diagnostics = None
        values = loop_fact_values(diagnostics)
        if interrupted and diagnostics is None:
            values.update(termination_reason='execution_interrupted', diagnosable=tool_results > 0)
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
            try:
                manifest_rows = json.loads(data)
                if not isinstance(manifest_rows, list) or any(not isinstance(item, dict) for item in manifest_rows):
                    raise ValueError('artifact collection manifest must contain object rows')
            except ValueError:
                if not interrupted:
                    raise
                manifest_rows = []
                collected.append(ArtifactFact('artifact collection', 'collection_failed', 'Interrupted collection manifest'))
            for item in manifest_rows:
                status = {'ok': 'collected', 'success': 'collected', 'collected': 'collected', 'empty': 'empty',
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
