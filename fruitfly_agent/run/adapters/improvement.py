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
        self.running_host = None
        self.runs, self.scope = runs, scope
        self.previews = {}
        self.current_run_id = None
        self._history = {}
        self.submissions = {}

    def workflow_configuration(self):
        return self.jobs.workflow_configuration()


    def pending_experience(self):
        return self.jobs.pending_experience()

    def experience_action(self, job_id, action):
        return self.jobs.experience_action(job_id, action)

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



    @property
    def running_improver(self):
        return self.running_host.running_improver if self.running_host is not None else None


    def improvement_activity(self):
        value = self.activity()
        if value is None:
            return None
        return ImprovementActivity(value.phase, value.completed, value.total,
            value.model_calls, value.trial_calls, value.failed_trials,
            value.tokens.input_tokens, value.tokens.output_tokens, value.tokens.cache_read_tokens,
            value.tokens.cache_creation_tokens, value.tokens.reported_calls, value.tokens.missing_calls)

    def cancel_improvement(self):
        return self.cancel()

