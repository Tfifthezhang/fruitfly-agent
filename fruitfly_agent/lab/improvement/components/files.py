"""Owned component adapters and validation."""
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot


from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec


class FileComponentAdapter:
    """An explicitly installed source component with injected object validation.

    Registration alone grants no execution capability. The runner must install
    the declared component. Compile checks do not establish correctness.
    """
    def __init__(self, document, validate, *, optimization: OptimizationSpec):
        if not isinstance(optimization, OptimizationSpec) or optimization.role != document.role:
            raise ValueError('file owner needs a matching explicit optimization declaration')
        self.document, self.validator = document, validate
        self.optimization = optimization

    def snapshot(self):
        return self.document

    def validate(self, document):
        self.validator(document)

