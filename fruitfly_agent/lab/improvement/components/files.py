"""Owned component adapters and validation."""
from ..contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot


class FileComponentAdapter:
    """An explicitly installed source component with injected object validation.

    Registration alone grants no execution capability. The runner must install
    the declared component. Compile checks do not establish correctness.
    """
    def __init__(self, document, validate):
        self.document, self.validator = document, validate

    def snapshot(self):
        return self.document

    def validate(self, document):
        self.validator(document)

