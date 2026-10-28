"""Composable search, execution and evolution stopping capabilities."""
from fruitfly_agent.lab.improvement.termination.policies import BoundedStopPolicy, IterationLimit, NoImprovement, FailureLimit, ResourceLimit, ScoreAtLeast, MetricThreshold
from fruitfly_agent.lab.improvement.termination.composition import AnyOf, AllOf, StopRegistry
from fruitfly_agent.improvement.contracts.stopping import SearchState, StopPolicy, StopDecision, stop_reason
