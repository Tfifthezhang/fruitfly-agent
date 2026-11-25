"""Offline comparison of upstream plans and owner-declared measurements."""
from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
from .pairing import pair_batches
from .metrics import summarize
from .statistics import paired_interval


def compare_batches(before, after, input_ids, *, settings=None, scope=None, read=None):
    from ...registration import normalize
    config = normalize({'settings': settings or {}})['settings']
    rows, excluded, issues = pair_batches(before, after, scope)
    metrics = summarize(rows, read)
    a, b = (metrics[s]['end_to_end_pass_rate']['value'] for s in ('before', 'after'))
    gain = b - a if a is not None and b is not None else None
    comparability = ('mismatch' if any(r['comparability'] == 'mismatch' for r in rows) else
                     'unknown' if not rows or any(r['comparability'] == 'unknown' for r in rows) else 'verified')
    interval = paired_interval(rows, config['bootstrap_resamples'], config['bootstrap_seed'])
    observation = 'undetermined' if gain is None else 'improved' if gain > 0 else 'regressed' if gain < 0 else 'tied'
    # A report describes observed gains; neither a positive point estimate nor
    # an identical ID grants independent verification or production activation.
    regression = metrics['success_regression']['value']
    minimum = config['minimum_gain'] if config['minimum_gain'] is not None else 0
    maximum = config['maximum_regression_rate']
    conclusion = 'insufficient'
    if comparability == 'verified' and gain is not None:
        if gain < 0 or maximum is not None and regression is not None and regression > maximum:
            conclusion = 'worse'
        elif gain == 0:
            conclusion = 'tied'
        elif interval and interval['lower'] > minimum:
            conclusion = 'better'
    return {'method': 'measured', 'inputs': list(input_ids),
        'policy_id': content_hash(canonical_json(config)), 'policy': config,
        'coverage': {'planned': len(rows), 'paired': sum(r['delivery_gain'] is not None for r in rows),
            'issues': issues, 'excluded': excluded},
        'data_status': 'complete' if rows and all(r['delivery_gain'] is not None for r in rows) else 'partial',
        'comparability': comparability, 'observed_effect': observation, 'conclusion': conclusion,
        'assurance': 'descriptive', 'recommendation': 'Independent verification is required before activation.',
        'metrics': metrics, 'mean_gain': gain, 'gain_pp': gain * 100 if gain is not None else None,
        'confidence_interval': interval, 'pairs': rows, 'usage': {'comparison_model_calls': 0},
        'limits': ['Selected-task results do not establish unseen-task generalization.',
                   'Unknown historical conditions are not reconstructed.',
                   'Known usage subtotals are not complete costs; research-role costs remain in producer reports.']}
