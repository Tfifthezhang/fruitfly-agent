"""Host-injected recursive improvement, independent of optimization policies."""

from .driver import CandidateAdopter, CandidateGenerator, CandidateVerifier, EvolutionDriver
from .models import (
    AgentVersion, Candidate, EvolutionAttempt, EvolutionBudget, EvolutionOutcome,
    EvolutionResult, Verification,
)

__all__ = [
    "AgentVersion", "Candidate", "Verification", "EvolutionBudget",
    "EvolutionOutcome", "EvolutionAttempt", "EvolutionResult", "EvolutionDriver", "PersistentEvolutionDriver",
    "CandidateGenerator", "CandidateVerifier", "CandidateAdopter",
]

from .persistent import PersistentEvolutionDriver
