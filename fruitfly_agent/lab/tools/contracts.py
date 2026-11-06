"""Fingerprint actual tool declarations without replacing model-facing descriptions."""
import hashlib
import json


def contract_fingerprints(tools):
    return tuple({'name': tool.name,
        'usage_sha256': 'sha256:' + hashlib.sha256(tool.description.encode()).hexdigest(),
        'schema_sha256': 'sha256:' + hashlib.sha256(json.dumps(tool.parameters,
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()}
        for tool in tools if not tool.hide_from_model)
