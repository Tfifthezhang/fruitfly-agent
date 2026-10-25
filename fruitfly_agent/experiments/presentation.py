"""Small text/JSON views; no task execution or configuration mutation."""
import json


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), flush=True)


def show_summary(summary):
    print('Workspace: ' + summary['workspace'])
    print('Operation: ' + summary['operation'])
    print('Agent configuration: ' + summary['runtime_source'])
    if 'execution' in summary:
        print('Tools per turn: ' + str(summary['execution']['max_tool_calls_per_turn']))
    for role, model in summary['model_roles'].items():
        print(f'{role.capitalize()} model: {model}')
    if summary.get('harness'):
        print('Enabled mechanisms: ' + ', '.join(item['id'] for item in summary['harness']['mechanisms']))
        print('Configured tools: ' + (', '.join(summary['harness']['tools']) or '(none)'))
        print('Editable components:')
        for component in summary['harness']['editable_components']:
            state = 'selected' if component['selected'] else 'available' if component['available'] else 'unavailable'
            print(f"  {component['role']} {component['id']}: {state}" + (': ' + component['reason'] if component['reason'] else ''))
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
        process = summary.get('process_assessment', {})
        print('Completed process assessment: ' + (', '.join(process.get('assessors', ())) or 'disabled'))
        print('Exploration: ' + summary.get('exploration', {}).get('policy', 'incumbent'))
        limits = summary['rsi'] if summary['operation'] == 'rsi' else summary['improvement']
        print(f"Total allowance: {limits['max_model_calls']} model calls; {limits['max_executions']} executions; {limits['timeout_seconds']} seconds")
    print('Model connectivity: not checked')


def show_record(record):
    print(f"{record['id']}: {record['status']}")
    if record.get('stop_reason'):
        print('Stop reason: ' + record['stop_reason'])
    for name, value in record.get('links', {}).items():
        print(f'{name}: {value}')
    if record.get('error'):
        print('Error: ' + record['error'])
