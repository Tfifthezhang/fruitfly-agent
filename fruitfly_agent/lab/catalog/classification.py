"""Owner-declared feature coordinates shared by menus and optimization discovery."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FeatureNode:
    id: str
    label: str
    order: int = 0

    def __post_init__(self):
        if not re.fullmatch(r'[a-z][a-z0-9-]*', self.id):
            raise ValueError('feature node needs a stable identifier')
        if not self.label.strip() or any(ord(c) < 32 for c in self.label):
            raise ValueError('feature node needs a single-line label')
        if type(self.order) is not int:
            raise TypeError('feature order must be an integer')


EXECUTION = FeatureNode('execution', 'Execution', 0)
ENVIRONMENT = FeatureNode('environment', 'Environment', 10)
AGENTS = FeatureNode('agents', 'Agent collaboration', 25)
TOOLS = FeatureNode('tools', 'Tools', 20)
CONTEXT = FeatureNode('context', 'Context', 30)
IMPROVEMENT = FeatureNode('improvement', 'Improvement', 40)
AUGMENTATION = FeatureNode('augmentation', 'Context augmentation', 0)
EXTERNALIZATION = FeatureNode('externalization', 'Context externalization', 10)
REDUCTION = FeatureNode('reduction', 'Context reduction', 20)
FILES = FeatureNode('files-and-shell', 'Files and shell', 0)
IPYTHON = FeatureNode('ipython', 'IPython', 10)
WEB = FeatureNode('web', 'Web', 20)
MCP = FeatureNode('mcp', 'MCP services', 30)
MEMORY = FeatureNode('memory', 'Memory', 0)
SKILLS = FeatureNode('skills', 'Skills', 10)
KNOWLEDGE = FeatureNode('local-knowledge', 'Local knowledge', 20)
HTTP = FeatureNode('live-http', 'Live HTTP information', 30)
RETRIEVAL = FeatureNode('information', 'Information selection', 40)


def validate_path(path):
    if (not isinstance(path, tuple) or not path
            or any(not isinstance(node, FeatureNode) for node in path)
            or len({node.id for node in path}) != len(path)):
        raise ValueError('owner must declare a distinct nonempty feature path')
    return path


def validate_tree(definitions):
    """Reject conflicting ancestry labels without maintaining another registry."""
    nodes: dict[tuple[str, ...], FeatureNode] = {}
    for definition in definitions:
        path = validate_path(definition.feature_path)
        for depth, node in enumerate(path):
            key = tuple(n.id for n in path[:depth + 1])
            if key in nodes and nodes[key] != node:
                raise ValueError('conflicting feature classification: ' + '.'.join(key))
            nodes[key] = node


@dataclass(frozen=True)
class OptimizationCoverage:
    """Protected infrastructure or an explicit shared execution policy."""
    kind: str
    reason: str
    components: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in {'protected', 'shared'} or not self.reason.strip():
            raise ValueError('optimization coverage needs a kind and reason')
        if (self.kind == 'shared') != bool(self.components):
            raise ValueError('shared optimization coverage must name its components')
        if len(set(self.components)) != len(self.components):
            raise ValueError('optimization coverage components must be distinct')
