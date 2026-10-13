"""Supported Eval bridge composition entry; Eval remains optional."""
from .adapters.evaluation import RunEvaluationController as EvaluationAdapter


class RunEvaluationController(EvaluationAdapter):
    def __init__(self, application, factory, *, python_executable=None):
        super().__init__(
            application, workspace=lambda: factory.cwd,
            environment=lambda: factory.environment,
            selection=lambda: factory.selection,
            python_executable=python_executable,
        )


__all__ = ["RunEvaluationController"]
