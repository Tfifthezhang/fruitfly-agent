"""Composable search, execution and evolution stopping capabilities."""
from .policies import (BoundedStopPolicy, IterationLimit, NoImprovement, FailureLimit,
    ResourceLimit, ScoreAtLeast, MetricThreshold)
from .composition import AnyOf, AllOf, StopRegistry
from ..contracts.stopping import SearchState, StopPolicy, StopDecision, stop_reason
