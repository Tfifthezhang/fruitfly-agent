"""Local MCP configuration and artifact fixtures; contains no TestCases."""
from pathlib import Path
import sys
import yaml
from importlib.util import find_spec

HAS_MCP = find_spec('mcp') is not None and find_spec('jsonschema') is not None
PEER = Path(__file__).resolve().parents[1] / 'fixtures' / 'mcp_server.py'


def write_mcp_config(root, *, name='fixture', tools=('echo',), mode='normal', **options):
    data = {'enabled': True, 'transport': 'stdio', 'command': sys.executable,
        'args': [str(PEER), '--mode', mode], 'cwd': str(root), 'tools': list(tools), **options}
    path = root / '.fruitfly' / 'mcp.yaml'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({'servers': {name: data}}), encoding='utf-8')
    return path


class MemoryArtifacts:
    def __init__(self):
        self.values = {}
    def write(self, text):
        import hashlib
        reference = 'sha256:' + hashlib.sha256(text.encode()).hexdigest()
        self.values[reference] = text
        return reference
    def read(self, reference):
        return self.values[reference]
