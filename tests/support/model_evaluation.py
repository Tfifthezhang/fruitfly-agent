"""Synthetic dimension judgments for offline assessment wiring tests."""
import json
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, UserMessage


def payload(view):
    return json.loads(next(m.content for m in view.messages if isinstance(m, UserMessage) and isinstance(m.content, str) and m.content.startswith('{')))


def judgment(view, *, choice=-1):
    data = payload(view)
    rows = data['executions']
    evidence = [row.get('facts_id', row['output_citation_id']) for row in rows]
    return AssistantMessage([TextBlock(json.dumps({
        'evaluations': [{'run_id': row['run_id'], 'dimensions': [{
            'dimension': 'completion', 'criterion': 'Supply the requested deliverable', 'judgment': 'partial',
            'reason': 'Synthetic observed contrast', 'uncertainty': 'Fake quality only',
            'evidence_ids': [row.get('facts_id', row['output_citation_id'])]}], 'findings':[]} for row in rows],
        'choice': rows[choice]['run_id'] if len(rows) > 1 else None,
        'reason': 'Synthetic evidence-based comparison', 'uncertainty': 'No real model-quality evidence',
        'evidence_ids': evidence}))], stop_reason='stop')


from tests.support.faux_provider import FauxProvider

class RoleProvider(FauxProvider):
    """A scripted executor with an explicit synthetic evaluator role."""
    def __call__(self,view,*,signal=None):
        if 'Evaluate granted evidence' in view.system_prompt:
            self.script.insert(0,lambda ctx,signal=None: self._judgment_stream(ctx))
        return super().__call__(view,signal=signal)

    def _judgment_stream(self,view):
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream
        return AssistantMessageEventStream(self._message_stream(judgment(view)))
