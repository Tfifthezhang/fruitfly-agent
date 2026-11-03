"""Owner declarations govern model admission and request attribution offline."""
import unittest
from pathlib import Path
from dataclasses import replace

from fruitfly_agent.core.data_model import ProviderView
from fruitfly_agent.core.observation import ObservationContext, bind_observation, current_observation
from fruitfly_agent.lab.catalog.assembly import AssemblyContext, ProviderBinding
from fruitfly_agent.lab.catalog.model_roles import ModelRoleRequirement, required_profiles, role_alias
from tests.support.faux_provider import FauxProvider


class ModelRoleTests(unittest.IsolatedAsyncioTestCase):
    def test_conditional_required_alias_and_declared_fallback_share_one_declaration(self):
        summary = ModelRoleRequirement('summary', 'Summarize evidence.', required_when=lambda v: v['mode'] == 'hybrid', fallback_role=None)
        self.assertEqual((), required_profiles({'summary': summary}, {'mode': 'deterministic'}))
        with self.assertRaisesRegex(ValueError, 'models.roles.summary'):
            required_profiles({'summary': summary}, {'mode': 'hybrid'})
        self.assertEqual(('small',), required_profiles({'summary': summary}, {'mode': 'hybrid', 'summary': 'small'}))
        editor = ModelRoleRequirement('editor', 'Edit candidates.', fallback_role='executor', lazy=True)
        self.assertEqual('main', role_alias('editor', editor, {}, {'executor': 'main'}))
        with self.assertRaises(ValueError):
            role_alias('editor', editor, {}, {})

    async def test_bound_role_controls_actual_request_and_preserves_parent_context(self):
        seen, resolutions, events = [], [], []
        class Provider(FauxProvider):
            def __call__(self, view, *, signal=None):
                seen.append(current_observation())
                return super().__call__(view, signal=signal)
        provider = Provider(); provider.respond_text('answer')
        def resolve(alias, limit):
            resolutions.append((alias, limit, current_observation().model_role))
            return ProviderBinding(provider, 'memory-model', alias, identity='actual-spec')
        context = AssemblyContext(Path('.'), None, 'main-model', resolve,
            component_id='memory', model_roles={'executor': 'large'},
            model_parameters={'memory': 'small'},
            model_requirements={'working_memory': ModelRoleRequirement('memory', 'Maintain memory.')})
        with bind_observation(ObservationContext(sink=events.append, run_id='run', model_role='executor')):
            binding = context.provider_for_role('working_memory', 128)
            self.assertEqual('executor', current_observation().model_role)
            answer = await binding.provider(ProviderView('', [], [], binding.model, 128)).result()
            self.assertEqual('executor', current_observation().model_role)
        self.assertEqual('answer', answer.text)
        self.assertEqual([('small', 128, 'working_memory')], resolutions)
        self.assertEqual('actual-spec', binding.identity)
        self.assertEqual('working_memory', seen[0].model_role)
        self.assertEqual('memory', seen[0].component_id)
        self.assertTrue(seen[0].request_id)
        self.assertEqual('succeeded', events[-1].state)
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            context.provider_for_role('another')

    def test_default_role_requirement_inherits_executor_without_an_explicit_alias(self):
        requirement = ModelRoleRequirement('model', 'Use a model.')
        self.assertEqual('executor', requirement.fallback_role)
        self.assertEqual((), required_profiles({'memory': requirement}, {}))
        self.assertEqual('main', role_alias('memory', requirement, {}, {'executor': 'main'}))
        self.assertEqual('small', role_alias('memory', requirement, {'model': 'small'}, {'executor': 'main'}))

    def test_export_keeps_slots_for_every_owner_declared_executor_fallback(self):
        from fruitfly_agent.lab.catalog import builtin_catalog, component_profile
        from fruitfly_agent.runtime_spec import HarnessProfile
        catalog = builtin_catalog()
        base = catalog.get('working-memory-reduction')
        custom = replace(base, descriptor=replace(base.descriptor, mechanism_id='custom-memory'), default_resource=None,
            model_role_parameters={'custom_memory': ModelRoleRequirement('memory_model_profile', 'Custom memory.')})
        catalog = catalog.extended((custom,))
        profile = component_profile(HarnessProfile('default', model_profile='main'), catalog)
        bindings = profile.to_dict()['models']['roles']
        expected = {'editor', 'assessor', 'working_memory', 'context_query', 'context_summary', 'custom_memory'}
        self.assertEqual(expected, set(bindings) - {'executor'})
        self.assertTrue(all(bindings[role] == {'inherit': 'executor'} for role in expected))
        resolved = catalog.resolve_model_roles((), {'executor': 'main'})
        self.assertEqual({'executor', *expected}, set(resolved))
        self.assertEqual({'main'}, set(resolved.values()))
        self.assertEqual('small', catalog.resolve_model_roles((),
            {'executor': 'main', 'custom_memory': 'small'})['custom_memory'])
