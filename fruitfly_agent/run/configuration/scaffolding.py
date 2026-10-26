"""Shared installed system templates; no Providers or experiment dependency."""
from importlib.resources import files


def system_templates():
    result = {}
    def collect(directory, prefix=''):
        for entry in directory.iterdir():
            name = prefix + entry.name
            if entry.is_dir():
                collect(entry, name + '/')
            elif entry.name.endswith('.yaml'):
                result[name] = entry.read_text(encoding='utf-8')
    collect(files('fruitfly_agent.run.configuration').joinpath('templates'))
    return result
