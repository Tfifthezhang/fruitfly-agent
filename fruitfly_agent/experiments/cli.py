"""Fixed Eval and independent research stages with file-based defaults."""
import argparse
import asyncio
import json
import subprocess
from pathlib import Path
import sys

from .configuration import load_configuration
from .composition import prepare_experiment, PreparationUnavailable
from .presentation import print_json, show_summary, show_record
from .records import RunRecords


def _options(parser, *, suppress=False):
    default = argparse.SUPPRESS if suppress else None
    parser.add_argument('--cwd', default=default, help='experiment workspace (default: current directory)')
    parser.add_argument('--config', default=default, help='experiment YAML (default: .fruitfly/experiment.yaml)')
    parser.add_argument('--request', default=default, help='use an Eval request JSON as the task source')
    parser.add_argument('--events', choices=('jsonl',), default=default, help='emit structured progress')
    parser.add_argument('--json', action='store_true', default=argparse.SUPPRESS if suppress else False)


def parser():
    root = argparse.ArgumentParser(prog='fruitfly-agent-lab',
        description='Independent fixed-version evaluation, candidate search and recursive improvement')
    _options(root)
    operations = root.add_subparsers(dest='operation')
    initialize = operations.add_parser('init', help='create editable workspace templates without running tasks')
    initialize.add_argument('--cwd', default=argparse.SUPPRESS)
    initialize.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
    initialize.add_argument('--source', choices=('task-set',), default=None)
    initialize.add_argument('--benchmark', help='registered benchmark ID; required for task-set')
    initialize.add_argument('--variant', choices=('smoke', 'no_gpu', 'full'), default='smoke')
    for operation in ('eval', 'improvement'):
        group = operations.add_parser(operation)
        _options(group, suppress=True)
        actions = group.add_subparsers(dest='command', required=True)
        names = ['check', 'report', 'list'] if operation == 'improvement' else ['check', 'run', 'report', 'stop', 'list']
        if operation == 'improvement':
            names += ['show', 'step', 'defaults', 'import', 'organize', 'assess', 'propose', 'execute', 'compare', 'inspect', 'resume', 'fork']
        if operation == 'eval':
            names += ['prepare', 'catalog']
        if operation == 'rsi':
            names += ['resume']
        for name in names:
            action = actions.add_parser(name)
            _options(action, suppress=True)
            if operation == 'improvement' and name in {'import', 'organize', 'assess', 'propose', 'execute', 'compare', 'inspect', 'resume', 'fork'}:
                action.add_argument('--study')
                action.add_argument('--output-root', help='portable study output directory')
                action.add_argument('--apply-to-current', action='store_true', help='derive a candidate on current configuration when executing')
                action.add_argument('--fresh', action='store_true')
                action.add_argument('--retry-unresolved', action='store_true',
                    help='explicitly authorize another attempt after an unresolved intent')
                if name == 'import':
                    action.add_argument('--source', choices=('eval', 'batch'))
                    action.add_argument('path', nargs='?')
                    action.add_argument('--related-records', help='associated report export directory')
                elif name == 'fork':
                    action.add_argument('target')
                elif name in {'organize', 'assess', 'propose', 'execute', 'compare'}:
                    action.add_argument('inputs', nargs='*', help='explicit input artifact IDs or bundle paths')
            elif name in {'report', 'stop', 'resume'}:
                action.add_argument('run_id')
            if name == 'prepare':
                action.add_argument('--tasks-only', action='store_true')
    return root


def dispatch(args):
    workspace = Path(args.cwd).resolve() if args.cwd else Path.cwd().resolve()
    if args.operation == 'init':
        if args.config or args.request or args.events:
            raise ValueError('init uses --cwd, --source, --benchmark and --variant; it does not load a configuration')
        from .scaffolding import initialize_workspace
        result = initialize_workspace(workspace, source=args.source,
            benchmark=args.benchmark, variant=args.variant)
        if args.json:
            print_json(result)
        else:
            for path in result['created']:
                print('Created: ' + path)
            for path in result['preserved']:
                print('Preserved: ' + path)
            for step in result['next_steps']:
                print(step)
        return 0
    if ((args.operation == 'improvement' and args.command in {'show', 'step', 'check', 'import', 'organize', 'assess', 'propose', 'execute', 'compare', 'inspect', 'resume', 'list', 'report'})
            or (args.operation == 'eval' and args.command == 'run')):
        from fruitfly_agent.runtime_spec.documents import DocumentReader
        target = Path(args.config).expanduser() if args.config else workspace / '.fruitfly/experiment.yaml'
        if not target.is_absolute():
            target = workspace / target
        is_research = target.is_file() and 'research' in DocumentReader().read(target)
        if is_research or args.command in {'show', 'step'}:
            from .operations.step import dispatch as step
            if args.operation == 'eval':
                from copy import copy
                args = copy(args)
                args.command = 'eval'
            result = asyncio.run(step(args, workspace))
            print_json(result)
            return 3 if args.command == 'check' and result.get('available') is False else 0
    if args.operation == 'improvement' and args.command == 'defaults':
        from .operations.research import defaults
        print_json(defaults(args, workspace))
        return 0
    if args.operation == 'improvement' and args.command in {'import', 'organize', 'assess', 'propose', 'execute', 'compare', 'inspect', 'resume', 'fork'}:
        from .operations.research import dispatch as research
        print_json(asyncio.run(research(args, workspace)))
        return 0
    records = RunRecords(workspace)
    operation, command = args.operation, args.command
    if command == 'catalog':
        from fruitfly_eval.catalog import builtin_catalog
        print_json(builtin_catalog().to_dict())
        return 0
    if command == 'list':
        rows = records.list(operation)
        if args.json:
            print_json(rows)
        else:
            for row in rows:
                show_record(row)
        return 0
    if command in {'report', 'stop', 'resume'}:
        record = records.read(args.run_id)
        if record['operation'] != operation:
            raise ValueError('run ID belongs to a different operation')
        if command == 'report':
            print_json(record) if args.json else show_record(record)
            return 0
        if command == 'stop':
            result = records.stop(args.run_id)
            print_json(result)
            return 1 if result['state'] in {'stop_requested', 'interrupted'} else 0
    overrides = {}
    if args.request:
        overrides['task'] = {'source': 'eval', 'request': str((workspace / args.request).resolve())}
    config = load_configuration(workspace, args.config, overrides=overrides,
        material_only=command == 'prepare' and args.tasks_only)
    if command == 'prepare' and config.task.get('source') == 'task-set':
        from .task_sets import prepare_collections
        print_json(prepare_collections(config, tasks_only=args.tasks_only,
            progress=(lambda event: print(json.dumps(event), flush=True)) if args.events else None))
        return 0
    if command == 'prepare' and args.tasks_only:
        from types import SimpleNamespace
        from .sources import resolve_source
        from .operations.evaluate import prepare
        source = resolve_source(config, default_source='eval')
        if source.benchmark is None:
            raise ValueError('Eval preparation requires task.source: eval')
        print_json(prepare(SimpleNamespace(source=source), tasks_only=True))
        return 0
    prepared = prepare_experiment(config, operation, require_prepared=command != 'prepare',
        require_credentials=command != 'prepare')
    summary = prepared.summary()
    if command == 'resume' and summary != record['configuration']:
        raise ValueError('experiment conditions changed; cannot resume this run')
    if command == 'check':
        print_json(summary) if args.json else show_summary(summary)
        return 0 if summary['available'] else 3
    if not summary['available']:
        raise PreparationUnavailable(summary['unavailable_reason'])
    def emit(event):
        if args.events:
            print(json.dumps(event, ensure_ascii=False, separators=(',', ':')), flush=True)
    if command == 'prepare':
        from .operations.evaluate import prepare
        print_json(prepare(prepared, tasks_only=args.tasks_only, progress=emit))
        return 0
    if command != 'resume':
        record = records.create(operation, summary)
    # Frozen input remains available even when execution/cleanup fails.
    if not args.json and not args.events:
        show_summary(summary)
        print('Run: ' + record['id'], flush=True)
    with records.owner(record):
        emit({'type': 'started', 'id': record['id'], 'operation': operation})
        if operation == 'eval':
            from .operations.evaluate import run as evaluate
            result = evaluate(prepared, record, records, emit)
        record['result'] = result
    emit({'type': 'finished', **result})
    if not args.events:
        print_json(record) if args.json else show_record(record)
    return 0 if result['status'] in {'completed', 'complete', 'rejected'} else 3 if result['status'] == 'blocked' else 1


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.operation is None:
            if not sys.stdin.isatty():
                root.print_help()
                return 0
            from .menu import select_operation
            selected = select_operation()
            if selected is None:
                return 0
            args.operation, args.command = selected
        return dispatch(args)
    except (KeyboardInterrupt, EOFError):
        print('Experiment interrupted.', file=sys.stderr)
        return 130
    except PreparationUnavailable as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 3
    except (OSError, ValueError, TypeError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 2
