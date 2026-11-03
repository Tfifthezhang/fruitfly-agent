"""Incremental task memory with durable, code-owned evidence coverage."""
from __future__ import annotations

from dataclasses import asdict, replace
import asyncio
from fruitfly_agent.core.data_model import ContextDecision, CustomMessage, UserMessage, CUSTOM_KIND_COMPACTION, ProviderView
from fruitfly_agent.core.context.validation import valid_tool_links
from ....resources import SessionHistory, public_message
from ....measurement.budget import MeasurementService, MeasurementConfig
from ...inference import AuxiliaryText
from .config import WorkingMemoryConfig
from ...identity import digest
from .state import load_checkpoint, save_checkpoint
from .maintenance import maintain


class WorkingMemoryReducer:
    estimate_source = 'heuristic_cjk'
    mechanism_id = 'working-memory'

    def __init__(self, config, provider, *, memory_model=None, memory_context_window=None,
                 memory_output_limit=None, history=None, meter=None, memory_identity=None):
        self.config = config
        self.history = history or SessionHistory()
        self.auxiliary = AuxiliaryText(provider, model=memory_model, context_window=memory_context_window,
            output_limit=memory_output_limit, meter=meter)
        self.meter = MeasurementService(MeasurementConfig(margin_tokens=0, margin_ratio=0))
        self.policy = digest({'config': asdict(config), 'model': memory_identity or {'model': memory_model,
            'context_window': memory_context_window, 'output_limit': memory_output_limit}})

    def estimate(self, snapshot):
        return self.meter.estimate(ProviderView(snapshot.system_prompt, list(snapshot.messages), list(snapshot.tools),
            snapshot.model, snapshot.max_tokens))

    def _sources(self, items):
        return ['[' + item.id + '] ' + public_message(item.message) + '\n' for item in items]

    def _load(self, state, items):
        return load_checkpoint(state, items, self._sources(items), self.policy, self.history,
            self.config.memory_tokens, self.meter.text_tokens)

    async def check_budget(self, snapshot):
        return await self._prepare(snapshot, force=False)

    async def react_to_overflow(self, snapshot, error):
        return await self._prepare(snapshot, force=True)

    async def _prepare(self, snapshot, *, force):
        items = snapshot.canonical_items
        self.history.bind(items)
        if not items or not valid_tool_links(list(snapshot.messages)):
            return None
        previous = snapshot.context_state.get(self.mechanism_id)
        checkpoint = self._load(previous, items)
        measured = snapshot.measurement
        allowance = snapshot.context_window - (measured.output_reserve if measured else snapshot.max_tokens) - (measured.margin if measured else 0)
        if snapshot.signal is not None and snapshot.signal.is_set():
            raise asyncio.CancelledError
        if allowance <= 0:
            return None
        occupancy = max(self.estimate(snapshot), measured.input_tokens or 0 if measured else 0) / allowance
        switch = force or occupancy >= self.config.switch_ratio
        catching_up = checkpoint.covered < checkpoint.target_count
        if not switch and (occupancy < self.config.maintenance_ratio or
                previous is not None and not catching_up
                and len(items) - checkpoint.covered < self.config.update_every_messages):
            return None
        sources = self._sources(items)
        checkpoint, updated = await maintain(snapshot, checkpoint, sources, self.config,
            self.auxiliary, self.meter.text_tokens, self.policy)
        if not updated:
            return None
        if snapshot.signal is not None and snapshot.signal.is_set():
            raise asyncio.CancelledError
        state = save_checkpoint(checkpoint, items, sources, self.policy, self.history)
        memory, covered, offset = checkpoint.memory, checkpoint.covered, checkpoint.offset
        reference = state['artifact']
        candidate = None
        # Unprocessed evidence never disappears, even when the update's page allowance is exhausted.
        if switch and snapshot.rebase_allowed and covered == len(items) and not offset:
            task = next((item.message for item in items if isinstance(item.message, UserMessage)), None)
            anchors = (task,) if task is not None else ()
            candidate = (CustomMessage(CUSTOM_KIND_COMPACTION, memory + '\n[Context artifact ' + reference + ']' + ('\n' + self.config.readback_instructions + '\nHistory index: ' + self.history.resource_prefix + 'index' if getattr(self.history, 'resource_prefix', '') else '')), *anchors)
            after = self.estimate(replace(snapshot, messages=candidate))
            if after >= self.estimate(snapshot) or after > allowance:
                candidate = None
        return ContextDecision(messages=candidate, state=state, retry=force and candidate is not None,
            mechanism_id=self.mechanism_id, base_revision=snapshot.revision,
            estimated_tokens_before=self.estimate(snapshot), metadata={'covered': covered, 'offset': offset})

    def execution_artifacts(self):
        """Public, immutable diagnostic material owned by this memory method."""
        return self.history.execution_artifacts()

    def validate_recovery(self, messages):
        self.history.validate_recovery(messages)
        if self.history.session is not None:
            state = self.history.checkpoint(self.mechanism_id)
            self._load(state, tuple(self.history.session.context_items()))
