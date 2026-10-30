"""Owner-controlled parameter surfaces for executable candidate configuration."""
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters


FIELDS = {'bash-tool': {'retained_commands', 'max_active_commands', 'default_timeout_seconds', 'output_characters'}, 'web-search-tool': {'backend', 'max_response_bytes', 'max_retries', 'timeout_seconds', 'cache_entries', 'cache_ttl_seconds'}, 'web-fetch-tool': {'backend', 'max_response_bytes', 'max_retries', 'timeout_seconds', 'cache_entries', 'max_redirects', 'cache_ttl_seconds'}}


def expose(definition):
    fields = FIELDS.get(definition.descriptor.mechanism_id)
    return editable_parameters(definition, fields) if fields else definition
