"""Append-only event journal with durable byte references and independent readers."""
from __future__ import annotations
import asyncio
from dataclasses import asdict
import json
import time

from fruitfly_agent.improvement.contracts.live import EvidencePosition, ExecutionEvent
from fruitfly_agent.improvement.contracts.versions import canonical_json


class EventJournal:
    def __init__(self, execution_id, version_id, artifacts, *, segment_id='initial', maximum=20000, record=None):
        self.execution_id, self.version_id, self.artifacts = execution_id, version_id, artifacts
        self.segment_id, self.maximum = segment_id, maximum
        if type(maximum) is not int or maximum < 2:
            raise ValueError('event journal requires a bounded positive capacity')
        self.references = []
        self.closed = False
        self.changed = asyncio.Event()
        self.record = record or (lambda *args, **kwargs: None)
        self.started = time.monotonic()

    @property
    def position(self):
        return EvidencePosition(self.execution_id, self.version_id, self.segment_id, len(self.references))

    def publish(self, kind, **payload):
        if self.closed or len(self.references) >= self.maximum:
            raise ValueError('event journal is closed or its allocation is exhausted')
        if len(self.references) >= self.maximum - 1 and kind not in {'finished', 'failed', 'cancelled'}:
            raise ValueError('event journal allocation exhausted; terminal slot reserved')
        payload.setdefault('elapsed_seconds', time.monotonic() - self.started)
        position = EvidencePosition(self.execution_id, self.version_id, self.segment_id, len(self.references) + 1)
        event = ExecutionEvent(position, kind, canonical_json(payload))
        ref = self.artifacts.put(canonical_json(asdict(event)).encode())
        self.references.append(ref)
        self.changed.set()
        self.record('execution-event', evidence=ref, **asdict(position), kind=kind)
        return event

    def close(self):
        self.closed = True
        self.changed.set()

    async def events(self):
        index = 0
        while True:
            while index < len(self.references):
                data = json.loads(self.artifacts.read(self.references[index]))
                event = ExecutionEvent(EvidencePosition(**data['position']), data['kind'], data['payload_json'])
                index += 1
                yield event
            if self.closed:
                return
            self.changed.clear()
            # No await occurs between checking the journal and subscribing.
            await self.changed.wait()
