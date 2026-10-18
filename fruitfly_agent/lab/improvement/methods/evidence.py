"""Bounded training evidence shared by native document and workflow methods."""
import json


def training_evidence(evaluation, cases=()):
    """Never project selection answers or infrastructure failures as learning evidence."""
    inputs = {case.case_id: case.input for case in cases}
    return [{'case_id': o.case_id, 'input': inputs.get(o.case_id, ''),
             'score': o.score, 'output': o.output, 'feedback': o.feedback}
            for o in evaluation.observations if o.partition == 'train' and o.status == 'ok']


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def check_problem(problem, roles, schemas):
    if problem.baseline.role not in roles or problem.baseline.schema not in schemas:
        raise ValueError('method does not support this target role or schema')


async def observe_candidate(services, text, training, selection):
    observer = getattr(services, 'candidate_evaluated', None)
    if observer is None:
        return False
    stop = await observer(text, training, selection)
    if type(stop) is not bool:
        raise ValueError('candidate observer must return a boolean')
    return stop
