"""Public registration entry for the current progressive Skill loader."""
from .methods.indexed_documents.registration import definition


def definitions():
    return (definition(),)
