"""Explicit offline reprocessing of retained answers with the same strict validator."""
import json


def reprocess_response(artifacts, response_id, records, supplied_citations):
    """Do not normalize malformed JSON, move fields, request models or fabricate citations."""
    from .evaluator import ModelEvaluator
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError('duplicate evaluator result field: ' + key)
            values[key] = value
        return values
    data = json.loads(artifacts.read(response_id).decode('utf-8'), object_pairs_hook=unique)
    ModelEvaluator.validate(data, records, set(supplied_citations))
    return data
