from collections.abc import Mapping
from typing import Any

class InstructionProposalSignature:
    @classmethod
    def prompt_renderer(cls, input_dict: Mapping[str, Any]) -> str | list[dict[str, Any]]: ...
    @classmethod
    def output_extractor(cls, lm_out: str) -> dict[str, str]: ...
