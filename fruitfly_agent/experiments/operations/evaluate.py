"""Single-version Eval; never invokes candidate search."""


def prepare(prepared, *, tasks_only=False, progress=None):
    from eval.api import prepare_evaluation
    benchmark = prepared.source.benchmark
    host_path = benchmark.stage_host()
    return prepare_evaluation(benchmark.request, host_config_path=host_path,
        tasks_only=tasks_only, progress=progress)


def run(prepared, record, records, emit):
    from eval.api import run_evaluation
    prepared.verify_sources()
    benchmark = prepared.source.benchmark
    def progress(event):
        if event.get('type') == 'started':
            record['links']['eval'] = event['evaluation_id']
            records.save(record)
        emit(event)
    report, store = run_evaluation(benchmark.request,
        output_root=prepared.config.workspace / '.fruitfly/eval',
        host_config_path=str(benchmark.require_host()), progress=progress)
    record['links'].update(eval=report.evaluation_id, report=str(store.path / 'report.json'))
    record['status'] = report.status
    return {'id': record['id'], 'status': report.status, 'report': str(store.path / 'report.json')}
