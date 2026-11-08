"""Detached proposal dependencies; no runner, selector or search loop."""
from .validation import validate_candidate


class ProposalStage:
    def __init__(self, *, generators, components):
        self.generators = generators
        self.components = components

    def validate(self, candidate, *, plan, baseline, records):
        validate_candidate(candidate, components=self.components, plan=plan,
            baseline=baseline, records=records)
