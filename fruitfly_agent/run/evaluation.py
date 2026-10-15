"""Supported Eval bridge composition entry; Eval remains optional."""
from .adapters.evaluation import RunEvaluationController as EvaluationAdapter


class RunEvaluationController(EvaluationAdapter):
    def __init__(self, application, factory, *, python_executable=None):
        super().__init__(
            application, workspace=lambda: factory.cwd,
            environment=lambda: factory.environment,
            python_executable=python_executable,
            improvement_available=lambda: getattr(factory, "benchmark_improvement_available", False),
            benchmark_preview=getattr(factory, "benchmark_task_preview", None),
        )


__all__ = ["RunEvaluationController"]
