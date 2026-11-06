"""Independent adoption policy for fixed-I editor and evaluator comparisons."""
from fruitfly_agent.lab.improvement.verification.episodes import PairedEpisodeVerification


class ImproverVerification(PairedEpisodeVerification):
    policy_id = 'improver-paired-v1'
