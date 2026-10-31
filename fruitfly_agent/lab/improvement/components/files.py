"""Owned component adapters and validation."""
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot


from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField


class FileComponentAdapter:
    """An explicitly installed source component with injected object validation.

    Registration alone grants no execution capability. The runner must install
    the declared component. Compile checks do not establish correctness.
    """
    def __init__(self, document, validate, *, optimization: OptimizationSpec, description=None):
        if not isinstance(optimization, OptimizationSpec) or optimization.role != document.role:
            raise ValueError('file owner needs a matching explicit optimization declaration')
        self.document, self.validator = document, validate
        self.description = description or ("Owned " + document.kind + " source files; preserve the registered schema and validate behavior through isolated execution.")
        self.optimization = optimization

    def snapshot(self):
        return self.document

    def describe_fields(self, document=None):
        current = document or self.document
        self.validate(current)
        files = {f.path: f.text for f in current.files}
        defaults = {f.path: f.text for f in self.document.files}
        return (OptimizationField("parameters.content.documents", "documents", self.description, files, defaults,
            constraints="Only component-owned files may change; the owner validator remains authoritative."),)

    def validate(self, document):
        self.validator(document)

