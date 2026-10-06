"""Optional standardized evaluation consumer for FruitFlyAgent."""

from .catalog import BenchmarkCatalog, builtin_catalog
from .contracts import (
    BenchmarkSelection,
    ComparisonSelection,
    EvaluationPlan,
    EvaluationRequest,
    ExecutionOptions,
    RuntimeReference,
    TrialRecord,
)
from .execution import execute_plan, execute_request
from .planning import create_plan
from .report import EvaluationReport, MetricRecord

__all__ = [
    "BenchmarkCatalog",
    "BenchmarkSelection",
    "ComparisonSelection",
    "EvaluationPlan",
    "EvaluationReport",
    "EvaluationRequest",
    "ExecutionOptions",
    "MetricRecord",
    "RuntimeReference",
    "TrialRecord",
    "builtin_catalog",
    "create_plan",
    "execute_plan",
    "execute_request",
]
