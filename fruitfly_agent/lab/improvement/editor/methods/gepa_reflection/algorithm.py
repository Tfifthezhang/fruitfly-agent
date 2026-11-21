"""One reflective text proposal and one metadata completion on its fixed draft."""
import json
from dataclasses import asdict
from typing import Any
from uuid import uuid4

import yaml

from fruitfly_agent.core.data_model import ProviderView, UserMessage
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
from fruitfly_agent.runtime_spec.documents import parameter_default

from ...schema import SUBMISSION
from ...submission import submission
from ....evidence import EvidenceWorkspace
from ..workspace.algorithm import model_completion
from . import compat
from .dataset import dataset

_TARGET = 'base_prompt'
_FIELD = 'parameters.instructions.system'
_PATH = 'harness/base_prompt/parameters.yaml'


class GEPAReflectionEditor:
    implementation_id = 'gepa-reflection-v1'

    def __init__(self, config, artifacts, components, *, sessions=None):
        self.adapter = compat.signature()
        self.config, self.artifacts, self.components = config, artifacts, components
        self.template = parameter_default(__package__, 'defaults.yaml', 'instructions.template')
        self.attribution = parameter_default(__package__, 'defaults.yaml', 'instructions.attribution')
        self.identity = {'method': self.implementation_id, 'package': 'gepa==' + compat.PINNED_VERSION,
                         'template': content_hash(self.template), 'attribution': content_hash(self.attribution)}
        self.complete = model_completion(config)
        self.measurement = MeasurementService()
        self.sessions = sessions

    async def edit(self, stage, request, services):
        return await services.operation(self._edit(request, services), stage='editor')

    async def _edit(self, request, services):
        if self.sessions is None:
            return await self._propose(request, services, self.config.session)
        async with self.sessions(services=services) as transcript:
            return await self._propose(request, services, transcript)

    async def _propose(self, request, services, transcript):
        self.admit(request.plan)
        workspace = EvidenceWorkspace.build(request, self.artifacts, record=services.record)
        original = workspace.read(_PATH)
        document = yaml.safe_load(original)
        before = document['parameters']['instructions']['system']
        packet, examples, supplied = dataset(request, self.artifacts)
        prompt = compat.render(self.adapter, before, examples, self.template)
        response = await self._request('text', prompt, packet, services, transcript)
        revised = compat.parse(self.adapter, response)
        draft = self.artifacts.put(revised.encode())
        services.record('gepa-draft', artifact_id=draft, packet_id=packet.artifact_id)
        metadata: dict[str, Any]
        if revised == before:
            metadata = {'reasons': [], 'decision': {'kind': 'retain_baseline',
                'explanation': 'The proposed instruction matches the authorized baseline.',
                'baseline_applicability': 'Compared with the exact supplied instruction.'}}
        else:
            document['parameters']['instructions']['system'] = revised
            workspace.write(_PATH, yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
            self.components.validate(workspace.collect())
            attribution = canonical_json({'instruction_before': before, 'frozen_instruction': revised,
                                          'examples': examples, 'submission_schema': SUBMISSION})
            metadata = json.loads(await self._request('attribution', attribution, packet, services, transcript))
            if not isinstance(metadata, dict) or not isinstance(metadata.get('decision'), dict):
                raise ValueError('GEPA attribution requires an explicit proposal decision')
            if metadata['decision'].get('kind') != 'candidate':
                workspace.files[_PATH] = original
        for run_id, example in supplied.items():
            workspace.access.provided('context/executions/' + run_id + '/reflection-example.json', example)
        candidate = submission(metadata, workspace, request, self.components)
        services.retain_proposal_decision(workspace.proposal_decision)
        return candidate

    @staticmethod
    def admit(plan):
        options = plan.component_options.get(_TARGET, {})
        if (tuple(plan.component_ids) != (_TARGET,)
                or tuple(options.get('editable_fields', ())) != (_FIELD,)):
            raise ValueError('GEPA reflection requires exactly the authorized base_prompt system instruction')

    async def _request(self, phase, prompt, packet, services, transcript):
        services.check()
        system = self.attribution if phase == 'attribution' else 'Use the supplied reflection instructions.'
        message = UserMessage(content=prompt)
        view = ProviderView(system, [message], [], self.config.model, self.config.max_tokens)
        estimate = await self.measurement.measure(view, self.config.provider, signal=services.signal)
        if not estimate.fits(self.config.context_window):
            raise ValueError('gepa_packet_space: fixed packet and output reserve exceed the editor context')
        reference = self.artifacts.put(canonical_json({'system': system, 'prompt': prompt}).encode())
        attempt = uuid4().hex
        services.record('request', id=attempt, model=self.config.model, phase=phase,
                        packet_id=packet.artifact_id, artifact_id=reference, measurement=asdict(estimate))
        if transcript is not None:
            transcript.append('meta', {'kind': 'completion-request', 'request_id': attempt, 'phase': phase,
                                       'request_artifact_id': reference}, sync=True)
            transcript.append('message', {'message': message.to_dict()}, sync=True)
        services.observe('model')
        def retain(result):
            if transcript is not None:
                transcript.append('message', {'message': result.to_dict()}, sync=True)
            services.record('response', attempt_id=attempt, phase=phase,
                            artifact_id=self.artifacts.put(result.text.encode()),
                            status='completed' if result.stop_reason == 'stop' else 'interrupted',
                            usage=result.usage.to_dict() if result.usage else None)
        response = await self.complete(system, prompt, signal=services.signal, on_response=retain)
        services.check()
        return response
