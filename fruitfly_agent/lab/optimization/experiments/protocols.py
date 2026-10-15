"""Explicit comparison capabilities; unsupported H/I/S protocols fail before work."""
from typing import Protocol
from fruitfly_agent.lab.algorithms.candidates import VersionCandidate
from fruitfly_agent.lab.algorithms.versions import SystemVersion


class ComparisonProtocol(Protocol):
    protocol_id: str
    roles: frozenset[str]
    async def compare(self, parent: SystemVersion, candidate: VersionCandidate, services): ...


class ComparisonRegistry:
    def __init__(self):
        self.protocols = {}

    def register(self, protocol):
        if protocol.protocol_id in self.protocols or not protocol.roles <= {"H", "I", "S"}:
            raise ValueError("invalid or duplicate comparison protocol")
        self.protocols[protocol.protocol_id] = protocol

    def resolve(self, protocol_id, candidate):
        protocol = self.protocols.get(protocol_id)
        if protocol is None or not {c.role for c in candidate.changes} <= protocol.roles:
            raise ValueError("comparison protocol cannot verify this modification scope")
        return protocol
