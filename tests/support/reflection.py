"""Deterministic text renderer and parser for reflection tests."""
from fruitfly_agent.improvement.contracts.versions import canonical_json


class FixtureSignature:
    @staticmethod
    def prompt_renderer(inputs):
        return canonical_json(inputs)

    @staticmethod
    def output_extractor(response):
        return {'new_instruction': response}
