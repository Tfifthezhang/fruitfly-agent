"""Bounded material production with explicit acceptance provenance."""
from dataclasses import dataclass
import asyncio


@dataclass(frozen=True)
class LearningObservation:
    source_id: str
    input: str
    output: str
    outcome: str
    manifest: str
    session: str


@dataclass(frozen=True)
class LearningMaterial:
    source_id: str
    input: str
    output: str
    status: str = 'pending'
    acceptance: str = ''
    evidence: str = ''

    def __post_init__(self):
        if self.status not in {'pending', 'verified', 'rejected'}:
            raise ValueError('invalid learning material status')
        if self.status == 'verified' and (not self.acceptance.strip() or not self.evidence.strip()):
            raise ValueError('verified material needs acceptance and evidence')


class RecordingProcessor:
    """Observation alone supplies no correctness label or reference answer."""
    async def process(self, observation):
        return LearningMaterial(observation.source_id, observation.input, observation.output)


class LearningEngine:
    def __init__(self, *, processor, save, trigger='task', batch_size=4, max_records=100, max_chars=16000):
        if trigger not in {'task', 'session', 'batch'}:
            raise ValueError('invalid learning trigger')
        if any(type(n) is not int or n < 1 for n in (batch_size, max_records, max_chars)):
            raise ValueError('learning limits must be positive integers')
        self.processor, self.save = processor, save
        self.trigger, self.batch_size = trigger, batch_size
        self.max_records, self.max_chars = max_records, max_chars
        self.pending, self.seen = [], set()
        self.prepared, self.interrupted = {}, set()
        self.lock = asyncio.Lock()

    async def observe(self, observation):
        if isinstance(observation, dict):
            observation = LearningObservation(**observation)
        if not isinstance(observation, LearningObservation) or not observation.source_id:
            raise ValueError('attributed task observation required')
        if len(observation.input) + len(observation.output) > self.max_chars:
            return False  # Do not silently turn a truncated task into learning data.
        async with self.lock:
            if observation.source_id in self.seen or len(self.seen) >= self.max_records:
                return False
            self.seen.add(observation.source_id)
            self.pending.append(observation)
            if self.trigger == 'task' or self.trigger == 'batch' and len(self.pending) >= self.batch_size:
                await self._flush()
            return True

    async def _flush(self):
        while self.pending:
            observation = self.pending[0]
            if observation.source_id in self.interrupted:
                return  # Unknown processor work is never automatically replayed.
            material = self.prepared.get(observation.source_id)
            if material is None:
                try:
                    material = await self.processor.process(observation)
                except BaseException:
                    self.interrupted.add(observation.source_id)
                    raise
                self.prepared[observation.source_id] = material
            if not isinstance(material, LearningMaterial) or material.source_id != observation.source_id:
                raise ValueError('learning material lost its source attribution')
            if len(material.input) + len(material.output) + len(material.acceptance) + len(material.evidence) > self.max_chars:
                raise ValueError('learning material exceeds its storage limit')
            await self.save(observation, material)
            self.pending.pop(0)
            self.prepared.pop(observation.source_id, None)

    async def close(self):
        async with self.lock:
            await self._flush()


def build_learning(policy, *, save, processor=None):
    """Public assembly helper; callers supply persistence and optional method."""
    return LearningEngine(processor=processor or RecordingProcessor(), save=save, **policy)
