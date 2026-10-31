"""Headless Application hosting; no terminal or benchmark-specific orchestration."""
import time

from fruitfly_agent.interactive import AgentApplication
from ..composition import application_factory
from . import observe


async def run(prepared, record, records, emit, *, factory=None):
    prepared.verify_sources()
    directory = records.directory(record['id'])
    runtime_path = prepared.stage_runtime(directory)
    factory = factory or application_factory(prepared, runtime_path)
    application = AgentApplication(factory)
    try:
        await application.start()
        preview = application.workflow_preview(prepared.request)
        emit({'type': 'preview', 'details': dict(preview.details)})
        await observe(application, application.improve(prepared.request.direction, preview_token=preview.preview_token), record, records, emit)
        history = application.improvement_history()[0]
        record['links']['improvement'] = history.run_id
        record['links'].update(dict(history.evidence))
        record['usage'] = dict(factory.improvement_usage())
        record['usage_kind'] = 'observed usage; missing outcomes remain unknown'
        record['stop_reason'] = history.stop_reason
        status = 'failed' if history.stop_reason == 'reference_unavailable' else history.status
        if status != 'completed':
            record['status'] = status
        return {'id': record['id'], 'status': status, 'stop_reason': history.stop_reason,
            'usage': dict(factory.improvement_usage()), 'links': record['links']}
    finally:
        record['usage'] = dict(factory.improvement_usage())
        history = application.improvement_history() if application.state.value not in {'new', 'closed', 'starting'} else ()
        if history:
            record['links']['improvement'] = history[0].run_id
            record['links'].update(dict(history[0].evidence))
        await application.close()
