"""Present and prepare candidates independently of search execution."""
from dataclasses import replace
from fruitfly_agent.interactive.contracts.candidates import CandidateView, CandidateSection
from fruitfly_agent.lab.improvement.api import SearchReport, restore_search_report


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
        role=record.role,
    )


class RunCandidateService:
    def __init__(self, *, workspace, candidates, artifacts, scope, prepare_candidate):
        self.workspace = workspace
        self.candidate_service = candidates
        self.artifacts = artifacts
        self.scope = scope
        self.prepare = prepare_candidate

    def candidates(self):
        return tuple(candidate_view(r) for r in self.candidate_service.candidates())

    def candidate_notice(self):
        return self.candidate_service.candidate_notice()

    def acknowledge_candidate_notice(self, ids):
        self.candidate_service.acknowledge_candidate_notice(ids)

    def _report(self, record):
        if record.report is not None:
            return SearchReport(**record.report)
        evidence = dict(record.evidence)
        try:
            return restore_search_report(self.workspace,
                history=evidence.get('Search history', ''),
                history_hash=evidence.get('Search history hash', ''),
                snapshot=evidence.get('Task snapshot', ''),
                snapshot_hash=evidence.get('Task snapshot hash', ''),
                candidate_id=record.artifact_id, baseline_id=record.parent_target_hash,
                parent_manifest=record.parent_manifest_digest, cases_digest=record.cases_digest)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def candidate_detail(self, candidate_id):
        record, diff = self.candidate_service.candidate_detail(candidate_id)
        parent = self.artifacts.read_text(record.parent_target_reference)
        text = self.artifacts.read_text(record.artifact_id)
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
            if record.role != 'H':
                conclusion = {'tied': 'Tied on declared objective', 'improved': 'Improved on declared objective',
                    'worse': 'Worse on declared objective', 'unavailable': 'Comparison unavailable'}[report.conclusion]
                evaluation = f'{conclusion}\nObjective ({report.metric}): {record.seed_score} → {record.validation_score}'
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
        evidence = dict(record.evidence)
        if evidence.get('Independent confirmation'):
            evaluation += ('\nIndependent confirmation: ' + evidence['Independent confirmation']
                           + '\nIndependent score: ' + evidence.get('Confirmation baseline score', 'unknown')
                           + ' → ' + evidence.get('Confirmation candidate score', 'unknown')
                           + '\nConfirmation repeats: ' + evidence.get('Confirmation repeats', 'unknown'))
        else:
            evaluation += '\nIndependent verification: not provided by search'
        sections = (
            CandidateSection('Overview', f'Algorithm: {record.algorithm}\nTarget: {record.target}\nStatus: {record.status}\nDirection: {record.direction}',
                             summary=f'Task: {record.task_pack_name or record.task_pack_id or "not recorded"}\nDirection: {record.direction}'),
            CandidateSection('Evaluation', evaluation, summary=evaluation),
            CandidateSection('Search usage', consumption, summary=consumption),
            CandidateSection('Changes', diff, initial=True),
            CandidateSection('Original text', parent), CandidateSection('Candidate text', text),
            CandidateSection('Scope', f'Configuration: {record.config_path or self.scope()[0]}\nProfile: {record.profile_id or self.scope()[1]}\nBinding: {record.binding_kind} {record.binding_key}\nUse: a fresh session; save also sets the future default. Built-in source is unchanged.',
                             summary=f'{record.config_path or self.scope()[0]} · {record.profile_id or self.scope()[1]}\nFresh session; saving also sets future default'),
            CandidateSection('Evidence', f'Parent: {record.parent_target_hash}\nCandidate: {record.artifact_id}\n' + '\n'.join(f'{k}: {v}' for k, v in view.evidence)),
        )
        return replace(view, sections=sections), diff

    def candidate_action(self, manifest, candidate_id, action):
        return candidate_view(self.candidate_service.candidate_action(manifest, candidate_id, action))

    async def prepare_candidate(self, manifest, candidate_id):
        return await self.prepare(manifest, candidate_id)

