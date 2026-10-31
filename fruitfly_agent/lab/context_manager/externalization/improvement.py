"""Owner-controlled parameter surfaces for executable candidate configuration."""
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters


FIELDS = {'rlm-ipython': {'offload_threshold_chars'}, 'ipython-tool': {'max_query_inline_result_chars', 'max_query_concurrent', 'max_artifact_bytes', 'max_query_input_chars', 'max_cell_output_chars', 'cell_timeout_seconds', 'query_timeout_seconds', 'max_query_output_tokens'}}


def expose(definition):
    fields = FIELDS.get(definition.descriptor.mechanism_id)
    return editable_parameters(definition, fields) if fields else definition
