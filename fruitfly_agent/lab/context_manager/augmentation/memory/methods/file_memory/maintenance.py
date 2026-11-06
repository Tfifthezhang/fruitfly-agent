"""Generate explicit changes using bounded evidence; never write or activate S."""
from dataclasses import asdict
from datetime import datetime, timezone

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.lab.agents import AgentRunner
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.lab.catalog.adapters.collections import parse_documents
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.models import MemoryEvidence
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.validation import apply_changes, validate_memories


class ThresholdMaintenance:
    library_id = 'memory-library'

    def __init__(self, config, extraction, consolidation, resolve_provider):
        self.config = config
        self.extraction = extraction
        self.consolidation = consolidation
        self.resolve_provider = resolve_provider

    def request(self, checkpoint, documents):
        if any(v['status'] == 'pending' for v in checkpoint['pending'].values()):
            return None
        evidence = checkpoint['evidence']
        turns = sum(e['completed'] for e in evidence)
        chars = sum(e['chars'] for e in evidence[checkpoint['processed']:])
        entries = validate_memories(parse_documents(documents))
        if entries and turns - checkpoint['consolidated_turns'] >= self.config.consolidate_after_user_turns:
            operation = 'consolidate'
        elif chars >= self.config.extract_after_user_chars:
            operation = 'extract'
        elif turns - checkpoint['consolidated_turns'] >= self.config.consolidate_after_user_turns:
            operation = 'consolidate'
        else:
            return None
        material = {'operation': operation, 'documents': documents, 'parameters': asdict(self.config),
            'instructions': self.extraction if operation == 'extract' else self.consolidation}
        if operation == 'extract':
            material.update(processed=checkpoint['processed'], evidence=evidence)
        identity = content_hash(canonical_json(material))
        unchanged = operation == 'consolidate' and any(
            row['status'] == 'completed' and row['operation'] == operation and row['request_id'] == identity
            for row in checkpoint.get('operations', {}).values())
        return {'operation': operation, 'request_id': identity, 'turns': turns,
            'processed': checkpoint['processed'], 'entries': entries, 'unchanged': unchanged}

    async def generate(self, request, checkpoint, read_evidence, *, complete=None, on_call=None):
        operation = request['operation']
        # Consolidation has no reason to call a model when no content was retained.
        if operation == 'consolidate' and (not request['entries'] or request.get('unchanged')):
            return None, request['processed'], request['turns']
        original = request['entries']
        entries = original
        budget = self.config.max_input_chars
        end = request['processed']
        batches: list[tuple[list[dict] | None, list[MemoryEvidence]]] = []
        if operation == 'extract':
            # A page never changes source identity or advances past an uninspected
            # suffix. All pages publish as one atomic proposal.
            pages: list[list[MemoryEvidence]] = []
            page: list[MemoryEvidence] = []
            used = 0
            for row in checkpoint['evidence'][end:]:
                text = read_evidence(row)
                if page and used + len(text) > budget:
                    break
                for offset in range(0, max(1, len(text)), budget):
                    part = text[offset:offset + budget]
                    if page and used + len(part) > budget:
                        pages.append(page); page, used = [], 0
                    page.append(MemoryEvidence(row['session_id'], row['message_id'], part, row['completed']))
                    used += len(part)
                end += 1
                if used >= budget:
                    break
            if page:
                pages.append(page)
            batches = [(None, page) for page in pages]
        else:
            # Consolidation visits every retained note, including notes beyond
            # the first context window. Unseen notes cannot be withdrawn.
            groups: list[list[dict]] = []
            group: list[dict] = []
            used = 0
            for entry in original:
                size = len(canonical_json(entry))
                if group and used + size > budget:
                    groups.append(group); group, used = [], 0
                group.append(entry); used += size
            if group:
                groups.append(group)
            batches = []
            for group in groups:
                wanted = {(e['provenance']['session_id'], mid) for e in group
                    for mid in e['provenance']['message_ids']}
                evidence, used = [], 0
                for row in checkpoint['evidence']:
                    if (row['session_id'], row['message_id']) not in wanted or used >= budget:
                        continue
                    part = read_evidence(row)[:budget - used]
                    evidence.append(MemoryEvidence(row['session_id'], row['message_id'], part, row['completed']))
                    used += len(part)
                batches.append((group, evidence))
        instructions = self.extraction if operation == 'extract' else self.consolidation
        for visible_group, selected in batches:
            visible = entries if visible_group is None else visible_group
            prompt = canonical_json({'operation': operation, 'memories': visible,
                'evidence': [{'id': e.identity, 'text': e.text} for e in selected]})
            if len(prompt) > budget * 2 + 1024:
                raise ValueError('complete memory request exceeds its input budget')
            if on_call is not None:
                on_call()
            if complete is None:
                binding = self.resolve_provider()
                config = AgentLoopConfig(binding.provider, model=binding.model,
                    max_tokens=self.config.max_output_tokens, max_tool_calls_per_turn=0)
                result = await AgentRunner(config).run([UserMessage(prompt)], system_prompt=instructions)
                if result.is_error:
                    raise RuntimeError('memory generation did not complete')
                assistants = [m for m in result.messages if m.role == 'assistant']
                response = assistants[-1].text if assistants else ''
            else:
                response = await complete(instructions, prompt)
            changes = parse_documents(response)
            if visible_group is not None:
                known = {e['id'] for e in visible_group}
                for change in changes:
                    if not isinstance(change, dict):
                        raise ValueError('invalid memory change')
                    key = change.get('id') if change.get('operation') == 'withdraw' else (
                        change.get('entry', {}).get('id') if isinstance(change.get('entry', {}), dict) else None)
                    if change.get('operation') in {'update', 'withdraw'} and key not in known:
                        raise ValueError('consolidation changed unseen memory')
            entries = apply_changes(entries, changes, evidence=selected,
                observed_at=datetime.now(timezone.utc).isoformat())
        text = canonical_json(entries) if entries != original else None
        return text, end if operation == 'extract' else request['processed'], request['turns'] if operation == 'consolidate' else None
