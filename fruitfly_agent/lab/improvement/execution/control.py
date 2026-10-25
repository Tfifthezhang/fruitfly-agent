"""One control owner validates capabilities, freshness and idempotency."""
import asyncio
from ..contracts.live import ControlReceipt
from ..contracts.versions import canonical_json
from dataclasses import asdict


class ControlDispatcher:
    def __init__(self, position, handlers=None, *, record=None, active=None):
        self.position = position
        self.handlers = dict(handlers or {})
        self.record = record or (lambda *args, **kwargs: None)
        self.receipts = {}
        self.active = active or (lambda: True)
        self.lock = asyncio.Lock()

    async def apply(self, request):
        async with self.lock:
            identity = canonical_json(asdict(request))
            previous = self.receipts.get(request.request_id)
            if previous:
                if previous[0] != identity:
                    raise ValueError('control identity was reused with different contents')
                return previous[1]
            current, expected = self.position(), request.expected
            same = (current.execution_id, current.version_id, current.segment_id) == (
                expected.execution_id, expected.version_id, expected.segment_id)
            if request.action not in self.handlers:
                receipt = ControlReceipt(request.request_id, 'rejected', 'unsupported capability')
            elif not self.active():
                receipt = ControlReceipt(request.request_id, 'rejected', 'execution is already finished')
            elif not same or not 0 <= current.sequence - expected.sequence <= request.max_event_lag:
                receipt = ControlReceipt(request.request_id, 'rejected', 'stale or future evidence position')
            else:
                try:
                    await self.handlers[request.action](request)
                except BaseException:
                    receipt = ControlReceipt(request.request_id, 'unknown', 'control outcome is uncertain; not replayable')
                    self.receipts[request.request_id] = identity, receipt
                    self.record('execution-control', request=asdict(request), receipt=asdict(receipt))
                    raise
                receipt = ControlReceipt(request.request_id, 'applied', '')
            self.receipts[request.request_id] = identity, receipt
            self.record('execution-control', request=asdict(request), receipt=asdict(receipt))
            return receipt
