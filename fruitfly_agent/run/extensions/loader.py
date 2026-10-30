"""Load selected Python files or installed entry points into staged registrars."""
from importlib import metadata, util
import hashlib
import inspect
from pathlib import Path
import sys

from fruitfly_agent.extensions import ExtensionAPI, ExtensionSet


def discover_extensions(directory):
    return tuple(sorted(str(path.resolve()) for path in Path(directory).glob('*.py') if path.is_file()))


def load_extensions(sources, *, workspace):
    registrations, identities, checks = [], [], []
    seen = set()
    for source in sources:
        if source.startswith('entrypoint:'):
            name = source.removeprefix('entrypoint:')
            entries = tuple(metadata.entry_points(group='fruitfly_agent.extensions', name=name))
            if len(entries) != 1:
                raise ValueError('extension entry point must resolve uniquely: ' + name)
            entry = entries[0]
            identity = 'entrypoint:' + name
            implementation = entry.dist.name + ':' + entry.dist.version + ':' + entry.value
            if identity in seen:
                raise ValueError('duplicate extension source: ' + identity)
            factory = entry.load()
        else:
            path = Path(source).expanduser()
            path = (path if path.is_absolute() else Path(workspace) / path).resolve()
            if path.suffix != '.py':
                raise ValueError('local extension must be an explicit Python file')
            if str(path) in seen:
                raise ValueError('duplicate extension source: ' + str(path))
            body = path.read_bytes()
            digest = hashlib.sha256(body).hexdigest()
            identity, implementation = str(path), digest
            def check(path=path, digest=digest):
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('extension source changed; reload before execution: ' + str(path))
            checks.append(check)
            module_name = '_fruitfly_extension_' + digest
            spec = util.spec_from_file_location(module_name, path)
            module = util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                exec(compile(body, str(path), 'exec'), module.__dict__)
                factory = getattr(module, 'register', None)
                if not callable(factory):
                    raise TypeError('extension must export a callable register(api): ' + str(path))
            finally:
                sys.modules.pop(module_name, None)
        if identity in seen:
            raise ValueError('duplicate extension source: ' + identity)
        seen.add(identity)
        api = ExtensionAPI(identity)
        value = factory(api)
        if value is not None:
            if inspect.iscoroutine(value):
                value.close()
            raise TypeError('extension register must be synchronous and return None')
        registrations.append(api)
        identities.append({'source': identity, 'implementation': implementation})
    def validate():
        for check in checks:
            check()
    return ExtensionSet(registrations, identities=identities, validate=validate)


def configured_extensions(path, *, profile_id=None):
    from fruitfly_agent.runtime_spec import load_harness_config
    path = Path(path)
    if not path.is_file():
        return ExtensionSet()
    profile = load_harness_config(path).select(profile_id)
    return load_extensions(profile.extensions, workspace=path.parent)
