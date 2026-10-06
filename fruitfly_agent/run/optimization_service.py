"""Translate host candidates and Lab results into frontend-owned values."""
from dataclasses import replace
from fruitfly_agent.interactive.optimization import CandidateView, CandidateSection, OptimizationPreview, TaskPackView, OptimizationActivity
from fruitfly_agent.lab.optimization.text_optimizer import SearchReport, restore_search_report


def candidate_view(record):
    evidence = list(record.evidence)
    if record.validation_score is not None:
        evidence.append(('Validation score', str(record.validation_score)))
    if record.seed_score is not None:
        evidence.append(('Seed score', str(record.seed_score)))
    if record.cases_digest:
        evidence.append(('Cases identity', record.cases_digest))
    if record.metric_calls:
        evidence.append(('Metric calls', str(record.metric_calls)))
    return CandidateView(
        record.candidate_id, record.status, record.algorithm, record.target,
        record.artifact_id, record.direction, record.parent_manifest_digest, tuple(evidence),
    )


class RunOptimizationService:
    """Explicit injected adapter; Interactive does not inspect Run records."""
    def __init__(self, factory):
        self.factory = factory

    def optimization_preview(self, manifest, *, pack_id=None, direction=""):
        value = self.factory.optimization_preview(manifest, pack_id=pack_id, direction=direction)
        return OptimizationPreview(value.algorithm, value.label, value.cost_notice, value.details,
                                   value.target_id, value.preview_token)

    async def optimize(self, manifest, direction, *, preview_token=""):
        return tuple(candidate_view(r) for r in await self.factory.optimize(manifest, direction, preview_token=preview_token))

    def optimization_activity(self):
        value = self.factory.optimization_activity()
        if value is None:
            return None
        return OptimizationActivity(value.phase, value.completed, value.total,
            value.model_calls, value.model_limit, value.trial_calls, value.trial_limit, value.failed_trials,
            value.tokens.input_tokens, value.tokens.output_tokens, value.tokens.cache_read_tokens,
            value.tokens.cache_creation_tokens, value.tokens.reported_calls, value.tokens.missing_calls)

    def cancel_optimization(self):
        return self.factory.cancel_optimization()

    def candidates(self):
        return tuple(candidate_view(r) for r in self.factory.candidates())

    def candidate_notice(self):
        return self.factory.candidate_notice()

    def acknowledge_candidate_notice(self, ids):
        self.factory.acknowledge_candidate_notice(ids)

    def _report(self, record):
        if record.report is not None:
            return SearchReport(**record.report)
        evidence = dict(record.evidence)
        try:
            return restore_search_report(self.factory.cwd,
                history=evidence.get('Search history', ''),
                history_hash=evidence.get('Search history hash', ''),
                snapshot=evidence.get('Task snapshot', ''),
                snapshot_hash=evidence.get('Task snapshot hash', ''),
                candidate_id=record.artifact_id, baseline_id=record.parent_target_hash,
                parent_manifest=record.parent_manifest_digest, cases_digest=record.cases_digest)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def candidate_detail(self, candidate_id):
        record, diff = self.factory.candidate_detail(candidate_id)
        parent = self.factory.artifact_store.read_text(record.parent_target_reference)
        text = self.factory.artifact_store.read_text(record.artifact_id)
        view = candidate_view(record)
        report = self._report(record)
        evaluation = f'Selection: {record.seed_score} → {record.validation_score}'
        consumption = 'Search usage unavailable; token consumption unknown'
        if report is not None:
            conclusion = {'tied': 'Tied; no measured improvement', 'improved': 'Improved on selection cases',
                          'worse': 'Worse on selection cases', 'unavailable': 'Comparison unavailable'}[report.conclusion]
            def result(prefix, partition, count):
                score = getattr(report, f'{prefix}_{partition}_score')
                completed = getattr(report, f'{prefix}_{partition}_completed')
                return f'{score} ({completed}/{count})' if score is not None else f'not completed ({completed}/{count})'
            evaluation = (f'{conclusion}\nTraining: {result("baseline", "train", report.train_count)} → '
                          f'{result("candidate", "train", report.train_count)}\nSelection: '
                          f'{result("baseline", "validation", report.validation_count)} → '
                          f'{result("candidate", "validation", report.validation_count)}')
            stop = report.stop_reason or 'unknown'
            if stop == 'budget_exhausted':
                kind = {'trial': 'Trial evaluation', 'model': 'Model request'}.get(report.exhausted_kind, 'Search call')
                stop = f'{kind} limit reached; automatic search stopped. Chat and manual testing remain available.'
            tokens = report.tokens
            if tokens.reported_calls:
                usage = (f'Reported tokens: {tokens.total_tokens:,} (input {tokens.input_tokens:,}; output {tokens.output_tokens:,})'
                         f'\nCache counters: read {tokens.cache_read_tokens:,}; creation {tokens.cache_creation_tokens:,}'
                         f'\nUsage receipts: {tokens.reported_calls}/{report.model_calls} model calls')
                if tokens.missing_calls:
                    usage += f'; {tokens.missing_calls} missing — reported subtotal, actual total unknown'
            else:
                usage = 'Token consumption unknown: Provider usage not reported' if report.model_calls else 'Tokens: 0 (no model calls)'
            consumption = (f'Stop: {stop}\nTrial evaluations: {report.trial_calls}/{report.trial_limit}; '
                           f'model requests: {report.model_calls}/{report.model_limit}\n{usage}')
        evaluation += '\nIndependent verification: not provided by search'
        sections = (
            CandidateSection('Overview', f'Algorithm: {record.algorithm}\nTarget: {record.target}\nStatus: {record.status}\nDirection: {record.direction}',
                             summary=f'Task: {record.task_pack_name or record.task_pack_id or "not recorded"}\nDirection: {record.direction}'),
            CandidateSection('Evaluation', evaluation, summary=evaluation),
            CandidateSection('Search usage', consumption, summary=consumption),
            CandidateSection('Changes', diff, initial=True),
            CandidateSection('Original text', parent), CandidateSection('Candidate text', text),
            CandidateSection('Scope', f'Configuration: {record.config_path or self.factory.selection.config_path}\nProfile: {record.profile_id or self.factory.selection.profile.profile_id}\nBinding: {record.binding_kind} {record.binding_key}\nUse: a fresh session; save also sets the future default. Built-in source is unchanged.',
                             summary=f'{record.config_path or self.factory.selection.config_path} · {record.profile_id or self.factory.selection.profile.profile_id}\nFresh session; saving also sets future default'),
            CandidateSection('Evidence', f'Parent: {record.parent_target_hash}\nCandidate: {record.artifact_id}\n' + '\n'.join(f'{k}: {v}' for k, v in view.evidence)),
        )
        return replace(view, sections=sections), diff

    def candidate_action(self, manifest, candidate_id, action):
        return candidate_view(self.factory.candidate_action(manifest, candidate_id, action))

    async def prepare_candidate(self, manifest, candidate_id):
        return await self.factory.prepare_candidate(manifest, candidate_id)

    def _task_target(self):
        return self.factory.optimization_target_id()

    def task_packs(self):
        return tuple(self._pack_view(s) for s in self.factory.task_pack_catalog().summaries(self._task_target()))

    @staticmethod
    def _pack_view(s):
        return TaskPackView(s.pack_id, s.name, s.source_hash, s.train_count,
                           s.validation_count, s.holdout_count, s.writable, s.error,
                           s.default_direction, s.acceptance_example)

    def save_training_task(self, pack_id, input, expected, **options):
        saved = self.factory.task_pack_catalog().save_training(pack_id, input, expected,
            target_id=self._task_target(), **options)
        return next(self._pack_view(s) for s in self.factory.task_pack_catalog().summaries(self._task_target()) if s.pack_id == saved)

    def task_pack_holdout(self, pack_id):
        return tuple((c.input, c.expected) for c in self.factory.task_pack_catalog().holdout(pack_id))
