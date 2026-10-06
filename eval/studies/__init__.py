"""Built-in experiment modes."""

from .base import EvaluationStudy
from .current_setup import CurrentSetupStudy
from .mechanism_comparison import MechanismComparisonStudy


def builtin_studies() -> dict[str, EvaluationStudy]:
    studies: tuple[EvaluationStudy, ...] = (
        CurrentSetupStudy(),
        MechanismComparisonStudy(),
    )
    return {study.mode: study for study in studies}


__all__ = [
    "EvaluationStudy",
    "CurrentSetupStudy",
    "MechanismComparisonStudy",
    "builtin_studies",
]
