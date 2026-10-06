"""Shared search receipts: measurements, limits and Provider-reported token usage.

This module owns the native journal schema. Consumers receive a report rather
than parse strategy events. Missing usage is never estimated from text length.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    reported_calls: int = 0
    missing_calls: int = 0

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in asdict(self).values()):
            raise ValueError('token usage must contain nonnegative integer counters')

    @property
    def total_tokens(self):
        # Follow Core Usage: cache counters are separate, never added twice.
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class SearchReport:
    train_count: int = 0
    validation_count: int = 0
    baseline_train_score: float | None = None
    candidate_train_score: float | None = None
    baseline_validation_score: float | None = None
    candidate_validation_score: float | None = None
    baseline_train_completed: int = 0
    candidate_train_completed: int = 0
    baseline_validation_completed: int = 0
    candidate_validation_completed: int = 0
    conclusion: str = 'unavailable'
    metric: str = ''
    direction: str = ''
    stop_reason: str = ''
    exhausted_kind: str = ''
    trial_calls: int = 0
    trial_limit: int = 0
    model_calls: int = 0
    model_limit: int = 0
    tokens: TokenUsage = TokenUsage()

    def __post_init__(self):
        if isinstance(self.tokens, dict):
            object.__setattr__(self, 'tokens', TokenUsage(**self.tokens))
        if not isinstance(self.tokens, TokenUsage):
            raise ValueError('invalid token usage report')
        for name, value in asdict(self).items():
            if name.endswith(('_count', '_completed', '_calls', '_limit')):
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError('invalid report counter')
            if name.endswith('_score') and value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError('invalid report score')
        if self.conclusion not in {'improved', 'tied', 'worse', 'unavailable'}:
            raise ValueError('invalid comparison conclusion')
        if self.direction not in {'', 'max', 'min'}:
            raise ValueError('invalid report objective direction')


def token_usage(rows, model_calls):
    """Count each actual request receipt at most once, including retries."""
    requests = {row['id'] for row in rows if row.get('kind') == 'request'}
    reported, totals = set(), dict(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0)
    for row in rows:
        attempt, usage = row.get('attempt_id'), row.get('usage')
        if row.get('kind') != 'response' or attempt not in requests or attempt in reported or not isinstance(usage, dict):
            continue
        values = {name: usage.get(name, 0) for name in totals}
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values.values()):
            continue
        if not any(values.values()):
            continue  # Default all-zero Usage is not evidence of a free request.
        reported.add(attempt)
        for name, value in values.items():
            totals[name] += value
    return TokenUsage(**totals, reported_calls=len(reported), missing_calls=max(0, model_calls-len(reported)))


def build_report(rows, *, baseline_id, candidate_id, train_count, validation_count,
                 seed_score=None, candidate_score=None, metric='', direction='',
                 stop_reason='', exhausted_kind='', model_calls=0, model_limit=0,
                 trial_calls=0, trial_limit=0):
    values = {}
    for prefix, identity in (('baseline', baseline_id), ('candidate', candidate_id)):
        for partition, count in (('train', train_count), ('validation', validation_count)):
            evaluations = [r for r in rows if r.get('kind') == 'evaluation'
                           and r.get('candidate_id') == identity and r.get('partition') == partition]
            row = evaluations[-1] if evaluations else {}
            completed = len(row.get('observation_ids', ()))
            values[f'{prefix}_{partition}_completed'] = completed
            values[f'{prefix}_{partition}_score'] = row.get('score') if completed == count and count > 0 else None
    conclusion = 'unavailable'
    if seed_score is not None and candidate_score is not None:
        if seed_score == candidate_score:
            conclusion = 'tied'
        elif direction in {'min', 'max'}:
            better = candidate_score > seed_score if direction == 'max' else candidate_score < seed_score
            conclusion = 'improved' if better else 'worse'
    return SearchReport(train_count=train_count, validation_count=validation_count, **values,
        conclusion=conclusion, metric=metric, direction=direction,
        stop_reason=stop_reason, exhausted_kind=exhausted_kind,
        model_calls=model_calls, model_limit=model_limit, trial_calls=trial_calls, trial_limit=trial_limit,
        tokens=token_usage(rows, model_calls))


def restore_search_report(workspace, *, history, history_hash, candidate_id, baseline_id,
                          parent_manifest, cases_digest, snapshot='', snapshot_hash=''):
    """Recover old receipts after checking identity and immutable evidence hashes.

    Unknown legacy objective direction stays unknown; ties are direction-neutral.
    Missing/corrupt evidence is handled by the caller as unavailable reporting.
    """
    root = Path(workspace).resolve()
    def read(reference, digest, directory):
        raw = root / reference
        path = raw.resolve()
        if raw.is_symlink() or path.parent != root / '.fruitfly' / 'optimization' / directory:
            raise ValueError('report evidence must stay in its workspace directory')
        encoded = path.read_bytes()
        if 'sha256:' + hashlib.sha256(encoded).hexdigest() != digest:
            raise ValueError('report evidence hash mismatch')
        return encoded.decode('utf-8')
    rows = [json.loads(line) for line in read(history, history_hash, 'searches').splitlines() if line.strip()]
    if not rows or any(not isinstance(r, dict) for r in rows):
        raise ValueError('invalid report journal rows')
    if any(r.get('parent_manifest') != parent_manifest or r.get('cases_digest') != cases_digest
                       or r.get('search_id') != rows[0].get('search_id') for r in rows):
        raise ValueError('report search identity mismatch')
    problem = next((r for r in rows if r.get('kind') == 'problem'), {})
    context = next((r for r in rows if r.get('kind') == 'report-context'), {})
    problem = {**problem, **context}
    result = next((r for r in reversed(rows) if r.get('kind') == 'search-result'), {})
    if problem.get('baseline_hash') != baseline_id or candidate_id not in result.get('candidates', ()):
        raise ValueError('report candidate identity mismatch')
    task = {}
    if snapshot and snapshot_hash:
        frozen = json.loads(read(snapshot, snapshot_hash, 'task-snapshots'))
        if not isinstance(frozen, dict) or not isinstance(frozen.get('task'), dict):
            raise ValueError('invalid report task snapshot')
        if frozen.get('target_hash') != baseline_id or frozen.get('task', {}).get('cases_digest') != cases_digest:
            raise ValueError('report task snapshot identity mismatch')
        task = frozen['task']
    def score(identity):
        matches = [r.get('score') for r in rows if r.get('kind') == 'evaluation'
                   and r.get('candidate_id') == identity and r.get('partition') == 'validation']
        return matches[-1] if matches else None
    params, usage = problem.get('parameters', {}), result.get('usage', {})
    if not isinstance(params, dict) or not isinstance(usage, dict):
        raise ValueError('invalid report budget receipt')
    trials, models = usage.get('trial', 0), usage.get('model', 0)
    trial_limit, model_limit = params.get('max_metric_calls', 0), params.get('max_model_calls', 0)
    # Old journals do not state which reserve failed; do not guess when ambiguous.
    exhausted = result.get('exhausted_kind', '')
    if not exhausted and result.get('status') == 'budget_exhausted':
        if trial_limit and trials == trial_limit and models < model_limit:
            exhausted = 'trial'
        elif model_limit and models == model_limit and trials < trial_limit:
            exhausted = 'model'
    return build_report(rows, baseline_id=baseline_id, candidate_id=candidate_id,
        train_count=problem.get('train_count', len(task.get('train', ()))),
        validation_count=problem.get('validation_count', len(task.get('validation', ()))),
        seed_score=score(baseline_id), candidate_score=score(candidate_id),
        metric=problem.get('metric', ''), direction=problem.get('objective_direction', ''),
        stop_reason=result.get('status', ''), exhausted_kind=exhausted,
        trial_calls=trials, trial_limit=trial_limit, model_calls=models, model_limit=model_limit)
