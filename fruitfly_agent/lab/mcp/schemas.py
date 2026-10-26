"""Exact JSON Schema validation, independent of Core's coercing subset."""
import copy
import json
from typing import Any
from fruitfly_agent.core.errors import Result


def compile_schema(schema: dict[str, Any]):
    try:
        import jsonschema
    except ImportError:
        raise RuntimeError("MCP support requires: pip install 'fruitfly-agent[mcp]'") from None
    original = copy.deepcopy(schema)
    if original.get('type') != 'object':
        raise ValueError('MCP input schema must declare an object root')
    dialect = original.get('$schema')
    if dialect is not None and dialect not in {
        'https://json-schema.org/draft/2020-12/schema', 'https://json-schema.org/draft/2019-09/schema',
        'http://json-schema.org/draft-07/schema#', 'https://json-schema.org/draft-07/schema',
    }:
        raise ValueError('unsupported MCP JSON Schema dialect')
    def inspect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'$ref', '$dynamicRef'} and (not isinstance(child, str) or not child.startswith('#')):
                    raise ValueError('MCP schemas may reference only local definitions; remote retrieval is disabled')
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(original)
    validator_class = jsonschema.validators.validator_for(original)
    try:
        validator_class.check_schema(original)
    except jsonschema.SchemaError:
        raise ValueError('MCP input schema is invalid') from None
    validator = validator_class(original)

    def validate(arguments: dict[str, Any]) -> Result[dict[str, Any]]:
        try:
            json.dumps(arguments, allow_nan=False)
            error = next(validator.iter_errors(arguments), None)
            if error is not None:
                # Validation messages can repeat credential-bearing argument values.
                location = '/'.join(str(part) for part in error.absolute_path) or '<root>'
                return Result.failure(f'invalid MCP arguments at {location}: constraint {error.validator}')
            return Result.success(copy.deepcopy(arguments))
        except Exception:
            return Result.failure('MCP arguments could not be validated')
    return validate
