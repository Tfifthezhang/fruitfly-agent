"""Publish readable history projections without changing the next operation."""
import json
import os
import fcntl
from pathlib import Path

from fruitfly_agent.run.configuration.persistence import write_bytes


def record_result(context, result):
    document = context.document
    root = document.root
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.references-owner').open('a+') as owner:
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX)
        index_path = root / 'references.json'
        references = json.loads(index_path.read_text()) if index_path.exists() else {}
        bundle = result['bundle']
        row = {'bundle': os.path.relpath(bundle, root), 'stage': context.stage,
            'run': result['run_id'], 'branch': context.branch}
        if context.stage == 'propose':
            configs = list(Path(bundle).parent.glob('*/candidate/config.yaml'))
            for config in configs:
                entry = {**row, 'candidate_config': os.path.relpath(config, root)}
                references[context.branch + ':' + config.parent.parent.name] = entry
            if len(configs) == 1:
                row['candidate_config'] = os.path.relpath(configs[0], root)
        alias = context.settings.get('publish_as', result['run_id'])
        from fruitfly_agent.improvement.contracts.validation import identifier
        identifier(alias)
        key = context.branch + ':' + alias
        if key in references and references[key] != row:
            previous = json.loads((root / references[key]['bundle']).read_text())
            current = json.loads(Path(bundle).read_text())
            if previous['outputs'] != current['outputs']:
                return {'observed_updated': False, 'references': str(index_path),
                    'publication_warning': 'Output retained; alias already identifies another result: ' + alias}
            row = references[key]
        references[key] = row
        write_bytes(index_path, (json.dumps(references, indent=2, ensure_ascii=False) + '\n').encode())
    observed = {'branch': context.branch, 'recent': [], 'available': {}}
    for alias, item in references.items():
        if item['branch'] != context.branch:
            continue
        observed['available'][alias.split(':', 1)[1]] = item
    for report in sorted((root / 'runs').glob('*/report.json'), key=lambda p: p.stat().st_mtime_ns):
        value = json.loads(report.read_text())
        if value.get('branch', 'main') != context.branch:
            continue
        effective = report.parent / 'configuration/effective.json'
        configuration = json.loads(effective.read_text()) if effective.exists() else {}
        authored = configuration.get('authored', {})
        aliases = configuration.get('model_roles') or {
            **configuration.get('system', {}).get('models', {}).get('roles', {}),
            **configuration.get('experiment', {}).get('models', {})}
        observed['recent'].append({'run': value['id'], 'stage': value['action'],
            'status': value['status'], 'configuration': os.path.relpath(effective, root),
            'roles': aliases,
            'settings': authored.get('stages', {}).get(value['action'], {}),
            'origin': ({'historical_source': configuration.get('source'),
                **configuration.get('historical_configuration', {})} if value['action'] == 'import'
                else authored.get('stages', {}).get(value['action'], {}).get('inputs', {}).get('harness', authored.get('baseline'))),
            'outputs': value.get('outputs', []),
            'differences': os.path.relpath(report.parent / 'configuration/differences.json', root)})
    observed['last_invocation'] = {key: value for key, value in context.preview().items() if key != 'observed'}
    limit = 10
    observed['history_count'] = len(observed['recent'])
    observed['recent'] = observed['recent'][-limit:]
    observed['reference_count'] = len(observed['available'])
    observed['available'] = dict(list(observed['available'].items())[-limit:])
    observed['reference_index'] = 'references.json'
    table = ['# Last captured research configuration', '',
        'Captured stage: `' + context.stage + '`. Edit the main file and use show to inspect the next invocation.', '',
        '| Run | Stage | Status | Models | Configuration |',
        '|---|---|---|---|---|']
    for item in observed['recent']:
        table.append('| ' + ' | '.join(str(value).replace('|', '\\|').replace('\n', ' ')
            for value in (item['run'], item['stage'], item['status'],
                json.dumps(item['roles'], ensure_ascii=False), item['configuration'])) + ' |')
    table.extend(['', '## Captured invocation', '', '```json',
        json.dumps(observed['last_invocation'], ensure_ascii=False, indent=2), '```', ''])
    write_bytes(root / 'configuration/current.md', '\n'.join(table).encode())
    projection = root / 'configuration/observed.json'
    write_bytes(projection, (json.dumps(observed, ensure_ascii=False, indent=2) + '\n').encode())
    return {'observed_updated': True, 'observations': str(projection), 'references': str(index_path)}
