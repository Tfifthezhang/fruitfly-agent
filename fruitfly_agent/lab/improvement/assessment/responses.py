"""Explicit offline reprocessing of retained answers with the same strict validator."""
import json


def reprocess_response(artifacts, response_id, records, supplied_citations):
    """Decode the declared no-choice sentinel; do not repair malformed fields or invent citations."""
    from .methods.model.algorithm import ModelEvaluator
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError('duplicate evaluator result field: ' + key)
            values[key] = value
        return values
    from .submission import normalize_no_choice
    data = normalize_no_choice(json.loads(artifacts.read(response_id).decode('utf-8'), object_pairs_hook=unique))
    ModelEvaluator.validate(data, records, set(supplied_citations))
    return data
