"""Present search execution and progress through the improvement contract."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from fruitfly_agent.interactive.contracts.candidates import CandidateSection
from fruitfly_agent.interactive.contracts.improvement import (ImprovementPreview, ImprovementActivity,
    ImprovementRunView)
from .candidates import candidate_view
from .improvement_results import result_sections


class RunImprovementService:
    def __init__(self, *, jobs, activity, cancel, runs=None, scope=lambda: ('', '')):
        self.jobs = jobs
        self.activity = activity
        self.cancel = cancel
        self.experiment_routes = {}
        self.running_host = None
        self.runs, self.scope = runs, scope
        self.previews = {}
        self.current_run_id = None
        self._history = {}
        self.submissions = {}

    def workflow_configuration(self):
        return self.jobs.workflow_configuration()

    def workflow_preview(self, request):
        value = self.jobs.preview(request)
        self.experiment_routes[value.preview_token] = self.jobs
        return self._remember_preview(value)

    def _remember_preview(self, preview):
        if preview.preview_token:
            if len(self.previews) >= 16:
                self.previews.pop(next(iter(self.previews)))
            self.previews[preview.preview_token] = preview
        return preview

    def improvement_history(self):
        rows = self.runs.list(self.scope()) if self.runs is not None else tuple(reversed(self._history.values()))
        return tuple(replace(row, status='interrupted', stop_reason='process_interrupted')
                     if row.status == 'running' and row.run_id != self.current_run_id else row for row in rows)

    def improvement_run_logs(self, run_id):
        if self.runs is None:
            return 'This host does not provide persisted search logs.'
        return self.runs.logs(run_id, self.scope())

    def _save_run(self, view, scope):
        if self.runs is not None:
            self.runs.save(view, scope)
        self._history[view.run_id] = view

    def improvement_submitted(self, manifest, direction, *, preview_token=''):
        """Record authorized intent before Application schedules its task."""
        if not preview_token:
            raise ValueError('a confirmed workflow preview is required')
        preview = self.previews.get(preview_token)
        view = ImprovementRunView(uuid4().hex, 'running',
            preview.algorithm if preview else '', preview.target if preview else '',
            preview.role if preview else 'H', direction, datetime.now(timezone.utc).isoformat())
        scope = self.scope()
        setup = CandidateSection('Setup', '\n'.join(f'{k}: {v}' for k, v in preview.details) if preview else 'Preview unavailable')
        self._save_run(replace(view, sections=(setup,)), scope)
        self.submissions[preview_token] = (view, scope, setup)
        self.current_run_id = view.run_id
        return preview_token

    def improvement_finished(self, preview_token, status, error=''):
        pending = self.submissions.pop(preview_token, None)
        if pending is None:
            return
        view, scope, setup = pending
        stop = 'cancelled_before_execution' if status == 'cancelled' else 'error'
        self._save_run(replace(view, status=status, finished_at=datetime.now(timezone.utc).isoformat(),
            stop_reason=stop, sections=(CandidateSection('Result',
                f'Stop reason: {stop}\nNo search work was started.\n{error}', initial=True), setup)), scope)
        self.current_run_id = None

    def register_benchmark(self, host, selection, executor, direction=""):
        value = host.preview_selection(selection, executor, direction=direction)
        if len(self.experiment_routes) >= 16:
            self.experiment_routes.pop(next(iter(self.experiment_routes)))
        self.experiment_routes[value.preview_token] = host
        return self._remember_preview(value)

    @property
    def running_improver(self):
        return self.running_host.running_improver if self.running_host is not None else None

    async def improve(self, manifest, direction, *, preview_token=""):
        if preview_token not in self.submissions:
            preview_token = self.improvement_submitted(manifest, direction, preview_token=preview_token)
        view, scope, setup = self.submissions.pop(preview_token)
        self.previews.pop(preview_token, None)
        host = self.experiment_routes.pop(preview_token, self.jobs)
        self.running_host = host
        now = lambda: datetime.now(timezone.utc).isoformat()
        self.current_run_id = view.run_id
        records: tuple = ()
        error, status = '', 'failed'
        try:
            records = await host.improve(manifest, direction, preview_token=preview_token)
            status = 'completed'
            return tuple(candidate_view(r) for r in records)
        except asyncio.CancelledError:
            status, error = 'cancelled', 'Cancellation requested; no candidate adopted'
            raise
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            try:
                query = getattr(host, 'completion', None)
                completion = query() if callable(query) else None
                stop, sections = result_sections(completion, records, error=error,
                    stop_reason='interrupted' if status == 'cancelled' else 'error' if status == 'failed' else '')
                self._save_run(replace(view, status=status, finished_at=now(), stop_reason=stop,
                    candidate_ids=tuple(r.candidate_id for r in records), sections=(*sections, setup),
                    evidence=completion.evidence if completion is not None else ()), scope)
            finally:
                self.running_host = None
                self.current_run_id = None

    def improvement_activity(self):
        value = self.activity()
        if value is None:
            return None
        return ImprovementActivity(value.phase, value.completed, value.total,
            value.model_calls, value.model_limit, value.trial_calls, value.trial_limit, value.failed_trials,
            value.tokens.input_tokens, value.tokens.output_tokens, value.tokens.cache_read_tokens,
            value.tokens.cache_creation_tokens, value.tokens.reported_calls, value.tokens.missing_calls)

    def cancel_improvement(self):
        return self.cancel()

