"""Fixed-depth editor experiments; persistence and activation remain host-owned."""
from .episodes import ComparisonEpisodeExecutor
from .runner import ImproverTaskRunner, TrialMeasurements
from .verification import ImproverVerification
from .registration import definition

__all__ = ['ComparisonEpisodeExecutor', 'ImproverTaskRunner', 'TrialMeasurements', 'ImproverVerification', 'definition']
