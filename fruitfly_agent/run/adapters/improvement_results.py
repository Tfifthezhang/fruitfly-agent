"""Project method-owned measurements to experiment result sections."""
from fruitfly_agent.interactive.contracts.candidates import CandidateSection


def model_usage(report):
    uncertain = getattr(report, 'uncertain_model_allowance', 0)
    if uncertain:
        return (f'Model calls: unknown ({report.model_calls} confirmed)\n'
                f'Model quota charged: {report.model_calls + uncertain}/{report.model_limit}')
    return f'Model calls: {report.model_calls}/{report.model_limit}'


def result_sections(completion, records, *, error='', stop_reason=''):
    report = completion.report if completion is not None else None
    if completion is not None and completion.summary and report is not None:
        stop = stop_reason or report.stop_reason
        return stop, (
            CandidateSection('Result', completion.summary + '\nStop reason: ' + stop
                + ('\nError: ' + error if error else ''), initial=True),
            CandidateSection('Task output', completion.output or '(no completed output)'),
            CandidateSection('Verification', completion.assurance + '\nBehavioral selection does not establish correctness or a quality gain.'),
            CandidateSection('Usage', model_usage(report) + f'\nTask executions: {report.trial_calls}/{report.trial_limit}\nToken receipts: unavailable'),
            CandidateSection('Evidence', '\n'.join(f'{k}: {v}' for k, v in completion.evidence)),
        )
    if report is None and records and records[0].report is not None:
        from fruitfly_agent.improvement.evidence.reporting import SearchReport
        report = SearchReport(**records[0].report)
    evidence = dict(completion.evidence) if completion is not None else {}
    if records:
        evidence.update(dict(records[0].evidence))
    stop = stop_reason or (report.stop_reason if report is not None else 'completed' if not error else 'error')
    confirmation = evidence.get('Independent confirmation', 'Not provided')
    evaluation = 'Comparison unavailable'
    usage = 'Usage unavailable; token consumption unknown'
    if report is not None:
        conclusion = {'improved': 'Improved on the declared selection objective',
                      'tied': 'Tied; no measured improvement', 'worse': 'Worse than baseline',
                      'unavailable': 'No published candidate comparison'}[report.conclusion]
        evaluation = (f'{conclusion}\nMetric: {report.metric or "unknown"}\n'
                      f'Baseline selection: {report.baseline_validation_score}\n'
                      f'Candidate selection: {report.candidate_validation_score}')
        if records and records[0].role != 'H':
            evaluation = (f'Declared method objective: {report.metric}\n'
                          f'Baseline objective: {records[0].seed_score}\n'
                          f'Candidate objective: {records[0].validation_score}')
        tokens = report.tokens
        token_text = (f'{tokens.total_tokens} reported ({tokens.reported_calls}/{report.model_calls} calls); '
                      'missing receipts remain unknown' if tokens.reported_calls else 'Unknown')
        usage = (model_usage(report) + '\n'
                 f'Task trials: {report.trial_calls}/{report.trial_limit}\nTokens: {token_text}')
    evaluation += f'\nIndependent confirmation: {confirmation}'
    if evidence.get('Confirmation baseline score'):
        evaluation += ('\nConfirmation score: ' + evidence['Confirmation baseline score']
                       + ' → ' + evidence.get('Confirmation candidate score', 'unknown'))
    outcome = ('Candidate available for human review; not active' if records
               else 'No candidate published; the active runtime is unchanged')
    if report is not None and records:
        outcome += '\nComparison: ' + {'improved': 'Measured objective gain', 'tied': 'Tied; no measured improvement',
            'worse': 'Worse than baseline', 'unavailable': 'Unavailable'}[report.conclusion]
    outcome += f'\nIndependent confirmation: {confirmation}'
    return stop, (
        CandidateSection('Result', f'{outcome}\nStop reason: {stop}' + (f'\nError: {error}' if error else ''), initial=True),
        CandidateSection('Evaluation', evaluation), CandidateSection('Usage', usage),
        CandidateSection('Evidence', '\n'.join(f'{k}: {v}' for k, v in evidence.items()) or 'No search journal was produced'),
    )
