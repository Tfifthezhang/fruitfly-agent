"""Small text/JSON views; no task execution or configuration mutation."""
import json


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), flush=True)


def show_summary(summary):
    print('Workspace: ' + summary['workspace'])
    print('Operation: ' + summary['operation'])
    print('Agent configuration: ' + summary['runtime_source'])
    if 'execution' in summary:
        print('Baseline tool limit per turn: ' + str(summary['execution']['max_tool_calls_per_turn']))
    for role, model in summary['model_roles'].items():
        print(f'{role.capitalize()} model: {model}')
    if summary.get('harness'):
        print('Enabled mechanisms: ' + ', '.join(item['id'] for item in summary['harness']['mechanisms']))
        print('Configured tools: ' + (', '.join(summary['harness']['tools']) or '(none)'))
        print('Editable components:')
        for component in summary['harness']['editable_components']:
            state = 'selected' if component['selected'] else 'available' if component['available'] else 'unavailable'
            print(f"  {component['role']} {component['id']}: {state}" + (': ' + component['reason'] if component['reason'] else ''))
        for component in summary['harness'].get('configuration', ()):
            print(f"  Source {component['role']} {component['id']}: {component['source']}")
            if component.get('edit_options'):
                print('    Edit bounds/fields: ' + json.dumps(component['edit_options'], ensure_ascii=False))
    request = summary['request']
    print(f"Task: {request['execution_id']} / {request['task_pack_id'] or 'explicit inputs'}")
    if 'task_set' in summary:
        for collection in summary['task_set']['collections']:
            print(f"Collection {collection['id']}: {collection['tasks']} tasks; "
                f"{collection['development']} development; {collection['selection']} selection")
        parallel = summary['multi_task']['execution']
        print(f"Concurrency: {parallel['concurrency']} task executions; 1 candidate")
        print('Joint aggregation: ' + summary['multi_task']['evaluation']['aggregation'])
    if summary['operation'] != 'eval':
        print(f"Search: {request['strategy_id']}; rounds={request['depth']}")
        print('Evaluation: shared model evaluator; process dimensions are defined by instructions')
        print('Exploration: ' + summary.get('exploration', {}).get('policy', 'incumbent'))
        print('Independent stage times: ' + json.dumps(summary['improvement']['timeouts']))
        print('Improvement request, tool and token usage is observed without count quotas')
    print('Model connectivity: not checked')


def show_record(record):
    print(f"{record['id']}: {record['status']}")
    if record.get('stop_reason'):
        print('Stop reason: ' + record['stop_reason'])
    for name, value in record.get('links', {}).items():
        print(f'{name}: {value}')
    if record.get('error'):
        print('Error: ' + record['error'])
