"""Optional single-configuration benchmark runner and reports."""
from .catalog import BenchmarkCatalog, builtin_catalog
from .contracts import BenchmarkSelection, EvaluationRequest, ExecutionOptions, RuntimeReference, TrialRecord
from .execution import execute_request
from .report import EvaluationReport, MetricRecord

__all__ = ["BenchmarkCatalog", "BenchmarkSelection", "EvaluationReport", "EvaluationRequest",
           "ExecutionOptions", "MetricRecord", "RuntimeReference", "TrialRecord", "builtin_catalog", "execute_request"]
