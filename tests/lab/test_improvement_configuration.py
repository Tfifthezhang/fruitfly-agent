"""Configured I values reach bounded inner execution and exact evidence pages."""
from tests.support.configuration import component_parameters, with_component_parameters, with_component_text, parameter_payload
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.components import ComponentRegistry, TextComponentAdapter
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot, ComponentFile
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructionTarget
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.experiments import EpisodeRequest
from fruitfly_agent.lab.improvement.assessment.instructions import EvaluatorInstructionTarget, EvaluatorInstructions
from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace, MemoryArtifacts
from fruitfly_agent.lab.improvement.evidence.session import EvidenceSession
from tests.support.task_execution import TaskRunnerFixture
from tests.support.faux_provider import FauxProvider
from tests.support.stages import version


class ImprovementConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_receipt_records_actual_returned_interval(self):
        artifacts = MemoryArtifacts()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'), 'system-prompt'),))
        workspace = EvidenceWorkspace(baseline=components.snapshot(), files={'evidence.txt': b'01234567890123456789'}, writable_ids=())
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'evidence.txt'})
        provider.respond_text('done')
        services = StageServices(RunPlan('pages', version(), ('base_prompt',)))
        try:
            await EvidenceSession(AgentLoopConfig(provider=provider), artifacts, settings={'read': {'default_characters':7}}).session(
                'Inspect the evidence.', workspace, services)
            pages = [fields for event, fields in services.events if event == 'evidence-page']
            self.assertEqual(len(pages), 1)
            self.assertEqual((pages[0]['start'], pages[0]['end'], pages[0]['characters']), (0, 7, 20))
            self.assertEqual(pages[0]['next_offset'],7)
            result = provider.calls[-1]['messages'][-1]
            self.assertEqual(json.loads(result.content[0].text)['text'],'0123456')
        finally:
            await services.close()


    def test_evaluator_grants_allow_only_prompts_and_enforce_fixed_fields(self):
        target = EvaluatorInstructionTarget()
        value = json.loads(target.snapshot().text)
        value['instructions']['assess'] = 'Identify unsupported completion claims.'
        target.validate_change(json.dumps(value), {'editable_fields': ['parameters.instructions.assess']})
        with self.assertRaisesRegex(ValueError, 'fixed'):
            target.validate_change(json.dumps(value), {'editable_fields': ['parameters.instructions.compare']})
        value['max_model_calls'] = 100
        with self.assertRaises(ValueError): target.validate(json.dumps(value))
        with self.assertRaises(ValueError): target.validate_options({'editable_fields': ['max_model_calls']})


    def test_editor_rejects_removed_allowances(self):
        target=EditorInstructionTarget();value=json.loads(target.snapshot().text)
        value['max_tool_calls']=1
        with self.assertRaises(ValueError):target.validate(json.dumps(value))
        with self.assertRaises(ValueError):target.validate_options({'editable_fields':['max_turns']})

    def test_role_settings_are_strict_configurable_and_protected_from_candidate_edits(self):
        from fruitfly_agent.lab.improvement.editor.configuration import EditorSettings
        from fruitfly_agent.lab.improvement.assessment.configuration import EvaluatorSettings
        for target in (EditorInstructionTarget(), EvaluatorInstructionTarget()):
            value = json.loads(target.snapshot().text)
            key = 'target_page_entries' if isinstance(target, EditorInstructionTarget) else 'output_preview_characters'
            value['settings'][key] = 1
            with self.subTest(target=type(target).__name__), self.assertRaisesRegex(ValueError, 'protected'):
                target.validate_change(json.dumps(value), {})
        for kind, values in ((EditorSettings, {'target_page_entries': True}),
                             (EditorSettings, {'target_page_entries': 4, 'max_target_entries': 3}),
                             (EvaluatorSettings, {'output_preview_characters': 0}),
                             (EvaluatorSettings, {'unknown': 1})):
            with self.subTest(values=values), self.assertRaises(ValueError):
                kind.from_dict(values)
