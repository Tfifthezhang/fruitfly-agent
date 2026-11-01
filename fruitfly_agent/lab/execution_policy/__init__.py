"""Fixed execution configuration; these settings are not Improvement targets."""
import json
from fruitfly_agent.runtime_spec import validate_execution


def configuration_surface():
    from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
    def normalize(value):
        if not isinstance(value, dict) or set(value) - {'settings'}:
            raise ValueError('execution policy requires settings')
        return validate_execution(value.get('settings', {}))
    return ConfigurationSurface('execution-policy', 'H', 'configuration', 'execution', normalize,
        encode=lambda values: json.dumps(values), decode=lambda text: {'settings': json.loads(text)})
